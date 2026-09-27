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


def pdf_url(rec: dict) -> str:
    """记录里第一个可下载的官方 PDF 原文链接;没有返回空串。"""
    for s in rec.get("sources") or []:
        url = s.get("url") or ""
        host = (urlsplit(url).hostname or "").lower()
        if s.get("role") == "official" and host.endswith(".go.th") and url.lower().split("?")[0].endswith(".pdf"):
            return url
    return ""


def normalize(text: str) -> str:
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


def good_enough(text: str) -> bool:
    return len(text) >= MIN_CHARS and thai_ratio(text) >= MIN_THAI_RATIO


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


def ocr_pdf(data: bytes, max_pages: int = 3) -> str:
    """扫描件:渲染前几页为图片,用 tesseract 泰文 + 英文模型识别。"""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        pdf.write_bytes(data)
        try:
            subprocess.run(["pdftoppm", "-r", "200", "-l", str(max_pages), "-png", str(pdf),
                            str(Path(tmp) / "p")], check=True, capture_output=True, timeout=120)
            texts = []
            for img in sorted(Path(tmp).glob("p-*.png")):
                r = subprocess.run(["tesseract", str(img), "stdout", "-l", "tha+eng"],
                                   capture_output=True, text=True, timeout=120)
                texts.append(r.stdout)
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("OCR 失败:%s", exc)
            return ""
    return normalize("\n".join(texts))


def download(url: str, client: httpx.Client) -> bytes | None:
    _throttle.wait()
    try:
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                log.info("下载原文 %s → HTTP %s", url, r.status_code)
                return None
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    log.info("原文超过 %d MB,放弃:%s", MAX_BYTES // 2**20, url)
                    return None
    except httpx.HTTPError as exc:
        log.info("下载原文失败 %s:%s", url, exc)
        return None
    return bytes(buf) if buf[:5] == b"%PDF-" else None


_ocr: bool | None = None


def fetch_fulltext(rec: dict, client: httpx.Client) -> tuple[str, str]:
    """返回 (正文, 方式)。方式:text = 文字层,ocr = 识别,"" = 没拿到。"""
    global _ocr
    url = pdf_url(rec)
    if not url:
        return "", ""
    data = download(url, client)
    if not data:
        return "", ""
    text = extract_pdf_text(data)
    if good_enough(text):
        return text[:MAX_CHARS], "text"
    if _ocr is None:
        _ocr = ocr_available()
    if _ocr:
        text = ocr_pdf(data)
        if good_enough(text):
            return text[:MAX_CHARS], "ocr"
    log.info("正文质量不足(%d 字,泰文占比 %.2f),退回只看标题:%s", len(text), thai_ratio(text), rec.get("uid"))
    return "", ""
