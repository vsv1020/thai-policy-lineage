# -*- coding: utf-8 -*-
"""公报正文:下载官方 PDF → 抽取泰文正文,供 app.enrich 写出有实质内容的摘要与要点。

为什么:只凭标题写出的摘要(「据标题……具体条款待原文核对」)内容单薄,搜索引擎不给排名,
AI 助手也不会引用。正文里才有谁受影响、要做什么、何时生效。

做法:
1. 只下载官方原文:host 以 .go.th 结尾且是 PDF。经 THAI_EGRESS_PROXY(与采集同一出口),
   单站 ≥1 秒/请求,单个文件上限 15 MB。
2. 先用 pypdf 抽文字层。部分公报用老式泰文字体,声调符号落在私用区(U+F700–F71A),
   这里按通行映射还原成标准 Unicode。
3. 文字层质量太差(扫描件、字体没有 Unicode 映射)且机器上有 pdftoppm + tesseract(tha)时,
   对前几页做 OCR。GitHub Actions 的采集工作流会装好这两个工具;服务器上没有就跳过。
4. 都不行就返回空,enrich 退回只看标题 —— 与原来的行为一致,不会更差。

正文只在内存里用一次,不写进事实层(太大,且以官方原文为准)。
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config import settings

log = logging.getLogger("policy.fulltext")

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 6                  # 公报公告多为 1–4 页;长文件只看开头,摘要够用
MAX_CHARS = 6000               # 给模型的正文上限(约 3–5k tokens)
MIN_CHARS = 150
MIN_THAI_RATIO = 0.35

# 老式泰文字体的私用区字形 → 标准 Unicode(Windows/Mac 通行的 Thai PUA 映射)
PUA = {0xF700: 0x0E10, 0xF701: 0x0E34, 0xF702: 0x0E35, 0xF703: 0x0E36, 0xF704: 0x0E37,
       0xF705: 0x0E48, 0xF706: 0x0E49, 0xF707: 0x0E4A, 0xF708: 0x0E4B, 0xF709: 0x0E4C,
       0xF70A: 0x0E48, 0xF70B: 0x0E49, 0xF70C: 0x0E4A, 0xF70D: 0x0E4B, 0xF70E: 0x0E4C,
       0xF70F: 0x0E0D, 0xF710: 0x0E31, 0xF711: 0x0E4D, 0xF712: 0x0E47, 0xF713: 0x0E48,
       0xF714: 0x0E49, 0xF715: 0x0E4A, 0xF716: 0x0E4B, 0xF717: 0x0E4C, 0xF718: 0x0E38,
       0xF719: 0x0E39, 0xF71A: 0x0E3A}


class _Throttle:
    """线程安全的礼貌限速:同一时刻起算,两次请求间隔 ≥ min_interval 秒。"""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self.min_interval
        if slot > now:
            time.sleep(slot - now)


_throttle = _Throttle(settings.min_request_interval)

# 本轮没拿到正文的原因统计 {原因: [次数, 示例链接]},写进采集运行摘要,便于针对性改进
_misses: dict[str, list] = {}
_misses_lock = threading.Lock()


def _miss(reason: str, url: str = "") -> None:
    with _misses_lock:
        m = _misses.setdefault(reason, [0, url])
        m[0] += 1


def reset_misses() -> None:
    with _misses_lock:
        _misses.clear()


def misses() -> dict[str, dict]:
    with _misses_lock:
        return {k: {"n": v[0], "example": v[1]} for k, v in sorted(_misses.items(), key=lambda kv: -kv[1][0])}


def pdf_url(rec: dict) -> str:
    """记录里第一个可下载的官方 PDF 原文链接;没有返回空串。"""
    for s in rec.get("sources") or []:
        url = s.get("url") or ""
        host = (urlsplit(url).hostname or "").lower()
        if s.get("role") == "official" and host.endswith(".go.th") and url.lower().split("?")[0].endswith(".pdf"):
            return url
    return ""


def fix_tis620_mojibake(text: str) -> str:
    """老式泰文字体把 TIS-620 字节当 Latin-1 输出(「¡ÒÃ」这类乱码):按 TIS-620 的固定偏移还原。
    只有在 Latin-1 补充区字符明显多、泰文几乎没有时才转换,避免误伤正常文本。"""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return text
    latin1 = sum(1 for c in chars if "\u00a1" <= c <= "\u00fb")
    # 真正的 TIS-620 乱码几乎全是这一区的字符;西文里偶尔的 é ï 远达不到一半
    if latin1 / len(chars) < 0.5 or thai_ratio(text) > 0.1:
        return text
    return "".join(chr(ord(c) - 0xA1 + 0x0E01) if "\u00a1" <= c <= "\u00fb" else c for c in text)


def normalize(text: str) -> str:
    text = fix_tis620_mojibake(text)
    text = text.translate(PUA)
    text = text.replace("ํา", "ำ")          # ํ + า → ำ(抽取时 SARA AM 常被拆开)
    text = re.sub(r"[​﻿\x00]", "", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def thai_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if "฀" <= c <= "๿") / len(chars)


def english_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    # 夹着 Latin-1 补充区字符(Ã Â ¸ 之类)的是乱码,不算英文
    if sum(1 for c in chars if "\u00a0" <= c <= "\u00ff") / len(chars) > 0.02:
        return 0.0
    return sum(1 for c in chars if c.isascii() and c.isalpha()) / len(chars)


def good_enough(text: str) -> bool:
    """够长,且是可读的泰文;或是可读的英文(海事公约修正案等部分公报就是英文原文)。"""
    if len(text) < MIN_CHARS:
        return False
    return thai_ratio(text) >= MIN_THAI_RATIO or english_ratio(text) >= 0.6


def describe(text: str) -> str:
    """一段抽取结果的简况,写进「没读到正文」的示例里便于排查。"""
    if not text:
        return "为空"
    return f"{len(text)} 字/泰文 {thai_ratio(text):.0%}"


def extract_pdftotext(data: bytes, max_pages: int = MAX_PAGES) -> str:
    """poppler 的 pdftotext:对嵌入字体的编码处理比 pypdf 稳,pypdf 读出乱码时再试它。"""
    if not shutil.which("pdftotext"):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        pdf.write_bytes(data)
        try:
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-l", str(max_pages), str(pdf), "-"],
                               capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("pdftotext 失败:%s", exc)
            return ""
    return normalize(r.stdout.decode("utf-8", "replace"))


def extract_pdf_text(data: bytes, max_pages: int = MAX_PAGES) -> str:
    try:
        from pypdf import PdfReader
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 —— 没装,或系统 cryptography 坏了(pyo3 panic 不是 Exception)
        log.warning("pypdf 不可用,无法抽取正文:%s", type(exc).__name__)
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:max_pages]
        return normalize("\n".join((p.extract_text() or "") for p in pages))
    except Exception as exc:  # noqa: BLE001 —— 坏文件、加密文件都当作抽不出来
        log.info("pypdf 抽取失败:%s", exc)
        return ""


def ocr_available() -> bool:
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return False
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=20)
        return "tha" in out.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False


_ocr_err = threading.local()


def ocr_pdf(data: bytes, max_pages: int = 3) -> str:
    """扫描件:渲染前几页为图片,用 tesseract 泰文 + 英文模型识别。
    OMP_THREAD_LIMIT=1:翻译是 6 路并发,tesseract 默认多线程会互相抢 CPU、拖到超时。"""
    _ocr_err.value = ""
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        pdf.write_bytes(data)
        try:
            subprocess.run(["pdftoppm", "-r", "200", "-l", str(max_pages), "-png", str(pdf),
                            str(Path(tmp) / "p")], check=True, capture_output=True, timeout=180)
            texts = []
            for img in sorted(Path(tmp).glob("p-*.png")):
                r = subprocess.run(["tesseract", str(img), "stdout", "-l", "tha+eng"],
                                   capture_output=True, text=True, timeout=240, env=env)
                texts.append(r.stdout)
        except subprocess.TimeoutExpired:
            _ocr_err.value = "超时"
            log.info("OCR 超时")
            return ""
        except (OSError, subprocess.SubprocessError) as exc:
            _ocr_err.value = type(exc).__name__
            log.info("OCR 失败:%s", exc)
            return ""
    return normalize("\n".join(texts))


def download(url: str, client: httpx.Client) -> bytes | None:
    _throttle.wait()
    try:
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                log.info("下载原文 %s → HTTP %s", url, r.status_code)
                _miss(f"HTTP {r.status_code}", url)
                return None
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    log.info("原文超过 %d MB,放弃:%s", MAX_BYTES // 2**20, url)
                    _miss("文件过大", url)
                    return None
    except httpx.HTTPError as exc:
        log.info("下载原文失败 %s:%s", url, exc)
        _miss(f"网络错误 {type(exc).__name__}", url)
        return None
    if buf[:5] != b"%PDF-":
        _miss("返回的不是 PDF", url)
        return None
    return bytes(buf)


_ocr: bool | None = None


def fetch_fulltext(rec: dict, client: httpx.Client) -> tuple[str, str]:
    """返回 (正文, 方式)。方式:text = 文字层,ocr = 识别,"" = 没拿到。"""
    global _ocr
    url = pdf_url(rec)
    if not url:
        _miss("没有官方 PDF 链接", next((s.get("url", "") for s in rec.get("sources") or []), ""))
        return "", ""
    data = download(url, client)
    if not data:
        return "", ""
    text = extract_pdf_text(data)
    if good_enough(text):
        return text[:MAX_CHARS], "text"
    alt = extract_pdftotext(data)
    if good_enough(alt):
        return alt[:MAX_CHARS], "text"
    if _ocr is None:
        _ocr = ocr_available()
    ocr_text = ""
    if _ocr:
        ocr_text = ocr_pdf(data)
        if good_enough(ocr_text):
            return ocr_text[:MAX_CHARS], "ocr"
    # 原因按阶段归类(便于统计),具体数字放在示例里
    layer = "文字层为空" if not (text or alt) else "文字层不可读"
    ocr = ("无 OCR" if not _ocr else f"OCR {getattr(_ocr_err, 'value', '') or '质量不足'}")
    detail = f"{url}(pypdf {describe(text)};pdftotext {describe(alt)};OCR {describe(ocr_text)})"
    log.info("读不出正文,退回只看标题:%s %s", rec.get("uid"), detail)
    _miss(f"{layer},{ocr}", detail)
    return "", ""
