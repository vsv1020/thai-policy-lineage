# -*- coding: utf-8 -*-
"""每日采集:官方开放数据 → 规范化 → 入库 → 导出静态 JSON。

    python3 -m app.collect                 # 跑一轮
    python3 -m app.collect --dry-run       # 只探测源可达性,不写库

数据源优先级:
  1. data.go.th 公报月度 JSON 索引(dataset_02_04)—— 官方、结构化、无需爬
  2. data.go.th 内阁决议年度 JSON(dataset_02_03)—— 政策上游,比公报早数周
  3. (人工/LLM 环节)公开检索发现的线索 —— 本模块**不做**,见下方说明

为什么这里不做公开检索:自动写入必须可复现、可审计。检索摘要要变成一条带文号、
带机关、带日期的记录,中间有一步判断,那一步应该由 LLM 流程(.claude/skills/autoresearch)
在人可以复核的地方做,并写进 JSONL 留下 git 记录。本模块只做**确定性**的部分:
官方接口取回什么就写什么,取不到就诚实记为 error。

三条编辑红线在 normalize() 里机械执行:王室相关标题跳过、人名前缀跳过、
拿不到机关或日期就跳过。
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from .config import BKK, POLICIES_DIR, settings
from .db import init_db, session_scope
from .ingest import load_documents, read_jsonl
from .models import CollectRun, Document, SourceHealth

log = logging.getLogger("policy.collect")

CKAN_BASE = "https://data.go.th"
UA = ("ThaiPolicyLineage/0.3 (+https://github.com/vsv1020/thai-policy-lineage; "
      "research prototype; contact: via GitHub issues)")

SOURCES = [
    {"id": "gazette_json", "name": "皇家公报官方月度 JSON 索引",
     "dataset": "dataset_02_04", "url": f"{CKAN_BASE}/dataset/dataset_02_04"},
    {"id": "cabinet_json", "name": "内阁决议年度 JSON",
     "dataset": "dataset_02_03", "url": f"{CKAN_BASE}/dataset/dataset_02_03"},
]

# 红线一:王室相关一律不自动入库
ROYAL_TERMS = ("พระบรมราชโองการ", "สมเด็จพระ", "พระบาทสมเด็จ", "ราชวงศ์", "เครื่องราชอิสริยาภรณ์")
# 红线二:人名前缀出现即跳过(叙勋、归化名单等)
PERSON_PREFIX = re.compile(r"(นาย|นาง|นางสาว)\s*\S")

# 公报系列 → 领域的粗分类。只用于给候选打初值,不确定就留给人工。
SERIES_KEEP = {"ก", "ง"}   # ก 法律法规、ง 一般公告;ข 皇家任命、ค 商业登记不收


@dataclass
class SourceResult:
    id: str
    name: str
    url: str
    status: str = "unattempted"
    detail: str = ""
    records: list[dict] = field(default_factory=list)


class Throttle:
    """礼貌限速:单站 ≥1 请求/秒(《计算机犯罪法》第 10 条的合规边界)。"""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        gap = self.min_interval - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


PROXY_SCHEMES = ("http://", "https://", "socks5://", "socks5h://")


def egress_label() -> str:
    """用于日志与运行记录的出口描述:只给协议,不暴露代理地址和密码(运行记录会提交进公开仓库)。"""
    p = settings.egress_proxy
    return f"泰国出口代理({p.split('://', 1)[0]})" if p else "直连"


def source_client(headers: dict) -> httpx.Client:
    """访问泰国政府数据源专用的客户端:配置了 THAI_EGRESS_PROXY 就经它出去。"""
    proxy = settings.egress_proxy or None
    if proxy and not proxy.startswith(PROXY_SCHEMES):
        raise RuntimeError("THAI_EGRESS_PROXY 协议不支持,应以 http:// https:// socks5:// socks5h:// 开头")
    return httpx.Client(timeout=settings.http_timeout, headers=headers,
                        follow_redirects=True, proxy=proxy)


def direct_client(headers: dict) -> httpx.Client:
    """不经泰国出口的客户端:代理反复失败时下载 resource 的兜底(文件可能放在不限地域的域名上)。"""
    return httpx.Client(timeout=settings.http_timeout, headers=headers, follow_redirects=True)


RETRY_WAITS = (3, 8)        # 连接层失败时的退避(秒);HTTP 4xx/5xx 不重试
# 重试也不会好的连接错误:域名解析不到、代理明确回复连不上目标
PERMANENT_ERRORS = ("name resolution", "Name or service not known", "nodename nor servname",
                    "could not connect", "No address associated")
DATASTORE_PAGE = 5000
DATASTORE_MAX = 40000       # 单个 resource 最多取这么多行(公报一个月约 3500 行)
MAX_BACKFILL_RESOURCES = 36
THAI_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม",
               "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:160]


def get_json(client: httpx.Client, url: str, throttle: Throttle, params: dict | None = None,
             retry: bool = True) -> Any:
    """GET 并解析 JSON。连接层错误(代理握手失败、超时、断连)退避重试;
    HTTP 状态错误、域名解析失败、代理明确回复连不上 —— 重试也没用,直接抛出。"""
    waits = RETRY_WAITS if retry else ()
    for attempt in range(len(waits) + 1):
        throttle.wait()
        try:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:           # socksio 的握手错误不是 httpx 异常,一并按连接层处理
            if attempt == len(waits) or any(h in str(exc) for h in PERMANENT_ERRORS):
                raise
            log.warning("请求失败(第 %d 次),%ds 后重试 %s:%s", attempt + 1,
                        RETRY_WAITS[attempt], urlsplit(url).hostname, _err(exc))
            time.sleep(RETRY_WAITS[attempt])


def fetch_ckan(dataset: str, throttle: Throttle, client: httpx.Client) -> list[dict]:
    """取 CKAN 数据集的 resource 列表。失败抛异常,由调用方记 error。"""
    payload = get_json(client, f"{CKAN_BASE}/api/3/action/package_show", throttle, {"id": dataset})
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show 返回 success=false: {dataset}")
    return payload["result"].get("resources", [])


def fetch_resource(url: str, throttle: Throttle, client: httpx.Client) -> tuple[Any, str]:
    """下载 resource,返回 (内容, 途径)。先走与 package_show 相同的客户端(复用已建立的连接);
    配了泰国出口且连接层反复失败时,再直连试一次。两条路都失败时,异常信息里带上目标域名与各自的错误。"""
    host = urlsplit(url).hostname or "?"
    try:
        return get_json(client, url, throttle), ("经泰国出口" if settings.egress_proxy else "直连")
    except httpx.HTTPStatusError:
        raise
    except Exception as exc:
        if not settings.egress_proxy:
            raise RuntimeError(f"{host}:{_err(exc)}") from exc
        first = exc
    try:
        with direct_client({"User-Agent": UA}) as c:
            return get_json(c, url, throttle, retry=False), "直连兜底(经泰国出口失败)"
    except Exception as exc:
        raise RuntimeError(f"{host}:经泰国出口 {_err(first)};直连 {_err(exc)}") from exc


def fetch_datastore(resource_id: str, throttle: Throttle, client: httpx.Client) -> list[dict]:
    """CKAN datastore:数据直接存在 data.go.th 上,不依赖 resource 原始文件地址。
    公报数据集的原始文件放在 soc.gdcatalog.go.th,该域名公网解析不到,只能走这条路。"""
    rows: list[dict] = []
    while len(rows) < DATASTORE_MAX:
        payload = get_json(client, f"{CKAN_BASE}/api/3/action/datastore_search", throttle,
                           {"resource_id": resource_id, "limit": DATASTORE_PAGE, "offset": len(rows)})
        if not payload.get("success"):
            raise RuntimeError("datastore_search 返回 success=false")
        page = payload["result"].get("records", [])
        rows += page
        if len(page) < DATASTORE_PAGE or len(rows) >= (payload["result"].get("total") or 0):
            break
    return rows


def resource_period(r: dict) -> tuple[int, int]:
    """从 resource 名称解析 (公元年, 月):「ราชกิจจานุเบกษาเดือนมีนาคม 2569」→ (2026, 3);
    「มติคณะรัฐมนตรี ปี 2568」→ (2025, 12)。解析不出来就用 last_modified。"""
    name = r.get("name") or ""
    m = re.search(r"(25\d\d|20\d\d)", name)
    if m:
        year = be_to_ce(int(m.group(1)))
        month = next((i + 1 for i, t in enumerate(THAI_MONTHS) if t in name), 12)
        return year, month
    stamp = r.get("last_modified") or r.get("created") or ""
    m = re.match(r"(\d{4})-(\d{2})", stamp)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def sync_targets(resources: list[dict], cutoff: date, backfill: bool) -> list[dict]:
    """要下载的 resource:能解析的(JSON 或有 datastore),按月份从新到旧。
    日常同步取最近 SYNC_RESOURCES 个 —— 已入库记录在官方源有改动时随之更新;
    回填取回溯期内的全部月份。"""
    usable = [r for r in resources
              if r.get("datastore_active") or (r.get("format") or "").lower() == "json"]
    usable.sort(key=resource_period, reverse=True)
    if not backfill:
        return usable[:max(1, settings.sync_resources)]
    out = [r for r in usable if resource_period(r) >= (cutoff.year, cutoff.month)
           or resource_period(r) == (0, 0)]
    return out[:MAX_BACKFILL_RESOURCES]


def describe_resource(r: dict) -> str:
    """resource 的一行摘要,写进运行记录 —— 数据源结构变了时,看这一行就知道该怎么改。"""
    host = urlsplit(r.get("url") or "").hostname or "无url"
    return (f"{r.get('name') or r.get('id', '?')}[{(r.get('format') or '?').lower()}·{host}"
            f"·datastore={'是' if r.get('datastore_active') else '否'}]")


def download(r: dict, throttle: Throttle, client: httpx.Client) -> tuple[Any, str]:
    """下载一个 resource:先试 data.go.th 的 datastore(不依赖原始文件地址),再试原始文件。"""
    errors = []
    if r.get("datastore_active") and r.get("id"):
        try:
            return fetch_datastore(r["id"], throttle, client), "data.go.th datastore"
        except Exception as exc:
            errors.append(f"datastore:{str(exc)[:150]}")
    if r.get("url"):
        try:
            return fetch_resource(r["url"], throttle, client)
        except Exception as exc:
            errors.append(f"file:{str(exc)[:200]}")
    raise RuntimeError(";".join(errors) or "没有可用的下载途径")


def iter_records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("data", "records", "result", "items"):
            if isinstance(payload.get(k), list):
                return [x for x in payload[k] if isinstance(x, dict)]
        return [payload]
    return []


def pick(rec: dict, keys: list[str]) -> str:
    for k in keys:
        for rk, rv in rec.items():
            if rk.strip().lower() == k.lower() and rv not in (None, ""):
                return str(rv)
    return ""


def be_to_ce(year: int) -> int:
    return year - 543 if year > 2400 else year


def normalize_date(value: str) -> str | None:
    value = (value or "").strip()
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", value)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        try:
            return date(be_to_ce(y), mo, d).isoformat()
        except ValueError:
            return None
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(be_to_ce(y), mo, d).isoformat()
        except ValueError:
            return None
    return None


def slug(text: str, limit: int = 5) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    if words:
        return "-".join(w.upper() for w in words[:limit])[:48]
    # 泰文标题没有拉丁词可用,退回稳定哈希 —— 保证 uid 可复现
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10].upper()


def passes_red_lines(title: str) -> tuple[bool, str]:
    for t in ROYAL_TERMS:
        if t in title:
            return False, f"王室相关({t})"
    if PERSON_PREFIX.search(title):
        return False, "含自然人姓名前缀"
    return True, ""


def normalize_gazette(rec: dict, run_at: str) -> tuple[dict | None, str]:
    """公报索引记录 → documents.jsonl 形状。返回 (记录, 跳过原因)。"""
    title = pick(rec, ["title", "ชื่อเรื่อง", "เรื่อง", "name", "subject"]).strip()
    if not title:
        return None, "无标题"
    ok, why = passes_red_lines(title)
    if not ok:
        return None, why

    published = normalize_date(pick(rec, ["date", "วันที่", "วันที่ประกาศ", "publish_date"]))
    if not published:
        return None, "无可解析日期"      # 红线三:没有日期不入库

    series = pick(rec, ["series", "ประเภท", "type", "category"]).strip()[:16]
    # 「ง พิเศษ」「ก ฉบับพิเศษ」是同一系列的特刊 —— 大量法规就刊在特刊上,按基础系列判断
    if series and series.split()[0] not in SERIES_KEEP:
        return None, f"系列 {series} 不在收录范围"

    volume = pick(rec, ["volume", "เล่ม", "book"])
    part = pick(rec, ["part", "ตอน", "ตอนที่"])
    pdf = pick(rec, ["pdf_url", "url", "link", "file", "ไฟล์"])

    uid = f"TH-GAZ-{published.replace('-', '')}-{slug(title)}"
    return {
        "uid": uid,
        "issue_id": None,
        "titles": {"zh": "", "th": title, "en": ""},
        "summary_zh": "",
        "instrument_ids": [],
        "goal_ids": [],
        "implementation_stage": None,
        "subjects": [],
        "agency_ids": ["cabinet"],          # 公报索引不含发文机关,先挂内阁秘书处口径
        "domain_ids": ["biz"],              # 待翻译分类环节改写
        "legal_form_id": "prakat",
        "status_id": "gazetted",
        "direction": {"value": "neutral", "confidence": "none", "method": "none"},
        "doc_no": f"{series} {volume}/{part}".strip() if (volume or part) else "",
        "gazette": {"series": series, "volume": int(volume) if volume.isdigit() else None,
                    "part": part, "page": None},
        "dates": {"resolved_at": None, "published_at": published, "effective_from": None,
                  "effective_to": None, "comment_deadline": None},
        "affected_parties": [],
        "relations": [],
        "sources": ([{"role": "official", "url": pdf, "note": "公报 PDF"}]
                    if pdf.startswith("http") else []),
        "provenance": {"pipeline": "gazette_json", "run_at": run_at,
                       "verified": False, "verified_at": None},
        "confidence": {"dates": "high", "doc_no": "high" if (volume or part) else "none"},
        "flags": {"has_detail_page": False},
        "note": "自官方公报索引自动入库;中文标题与摘要待翻译环节补全",
    }, ""


def normalize_cabinet(rec: dict, run_at: str) -> tuple[dict | None, str]:
    title = pick(rec, ["title", "เรื่อง", "ชื่อเรื่อง", "subject", "name", "หัวข้อ", "ชื่อมติ",
                       "title_th", "topic", "เรื่องที่เสนอ"]).strip()
    if not title:
        return None, "无标题"
    ok, why = passes_red_lines(title)
    if not ok:
        return None, why
    resolved = normalize_date(pick(rec, ["date", "วันที่มีมติ", "วันที่", "resolution_date",
                                         "วันที่ประชุม", "วันประชุม", "meeting_date"]))
    if not resolved:
        return None, "无可解析日期"
    url = pick(rec, ["url", "link", "detail_url"])
    uid = f"TH-CABX-{resolved.replace('-', '')}-{slug(title)}"
    return {
        "uid": uid,
        "issue_id": None,
        "titles": {"zh": "", "th": title, "en": ""},
        "summary_zh": "",
        "instrument_ids": [],
        "goal_ids": [],
        "implementation_stage": "cabinet_resolution",
        "subjects": [],
        "agency_ids": ["cabinet"],
        "domain_ids": ["biz"],
        "legal_form_id": "resolution",
        "status_id": "pending_gazette",
        "direction": {"value": "neutral", "confidence": "none", "method": "none"},
        "doc_no": "",
        "gazette": None,
        "dates": {"resolved_at": resolved, "published_at": None, "effective_from": None,
                  "effective_to": None, "comment_deadline": None},
        "affected_parties": [],
        "relations": [],
        "sources": [{"role": "official", "url": url, "note": "决议详情"}]
                   if url.startswith("http") else [],
        "provenance": {"pipeline": "cabinet_json", "run_at": run_at,
                       "verified": False, "verified_at": None},
        "confidence": {"dates": "high", "doc_no": "none"},
        "flags": {"has_detail_page": False},
        "note": "自官方决议库自动入库;中文标题与摘要待翻译环节补全",
    }, ""


def collect_source(src: dict, throttle: Throttle, run_at: str, cutoff: date,
                   dry_run: bool, backfill: bool = False) -> SourceResult:
    res = SourceResult(id=src["id"], name=src["name"], url=src["url"])
    # 同一个客户端贯穿 package_show 与 resource 下载:同域名时复用已建立的代理连接,少一次握手
    with source_client({"User-Agent": UA, "Accept": "application/json"}) as client:
        return _collect_with(src, res, client, throttle, run_at, cutoff, dry_run, backfill)


def _collect_with(src: dict, res: SourceResult, client: httpx.Client, throttle: Throttle,
                  run_at: str, cutoff: date, dry_run: bool, backfill: bool = False) -> SourceResult:
    try:
        resources = fetch_ckan(src["dataset"], throttle, client)
    except Exception as exc:
        res.status = "error"
        res.detail = f"{type(exc).__name__}: {exc}"[:400]
        return res

    targets = sync_targets(resources, cutoff, backfill)
    if not targets:
        res.status = "error"
        res.detail = ("数据集里没有可解析的 resource | 数据集内 resource:"
                      + ", ".join(describe_resource(r) for r in resources[:6]))[:1200]
        return res
    if dry_run:
        res.status = "ok"
        res.detail = f"可达,{len(resources)} 个 resource,将同步 {len(targets)} 个(dry-run 未下载)"
        return res

    normalize = normalize_gazette if src["id"] == "gazette_json" else normalize_cabinet
    skipped: dict[str, int] = {}
    done: list[str] = []
    failed: list[str] = []
    fields = ""
    seen: set[str] = set()
    for r in targets:
        name = r.get("name") or r.get("id", "?")
        try:
            payload, via = download(r, throttle, client)
        except Exception as exc:
            failed.append(f"{name}:{str(exc)[:200]}")
            continue
        rows = iter_records(payload)
        if rows and not fields:
            # 字段样本写进运行记录:字段名对不上(例如全部「无标题」)时,看这一行就知道该怎么改
            fields = ",".join(k for k in list(rows[0])[:14] if not k.startswith("_"))
        got = 0
        for rec in rows:
            norm, why = normalize(rec, run_at)
            if norm is None:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            d = norm["dates"]
            stamp = d.get("published_at") or d.get("resolved_at")
            if stamp and date.fromisoformat(stamp) < cutoff:
                skipped["早于回溯期"] = skipped.get("早于回溯期", 0) + 1
                continue
            if norm["uid"] in seen:
                continue
            seen.add(norm["uid"])
            res.records.append(norm)
            got += 1
        done.append(f"{name}({urlsplit(r.get('url') or '').hostname},{via}) {got} 条")

    if not done:
        res.status = "error"
        res.detail = ("resource 均不可用:" + ";".join(failed)
                      + " | 数据集内 resource:" + ", ".join(describe_resource(r) for r in resources[:6]))[:1200]
        return res
    res.status = "ok"
    parts = [f"同步 {len(done)} 个文件,收 {len(res.records)} 条:" + ";".join(done)]
    if skipped:
        parts.append(f"跳过 {sum(skipped.values())} 条(" +
                     ", ".join(f"{k}×{v}" for k, v in sorted(skipped.items())) + ")")
    if failed:
        parts.append(f"{len(failed)} 个文件失败:" + ";".join(failed))
    if fields and (not res.records or skipped.get("无标题") or skipped.get("无可解析日期")):
        parts.append(f"字段样本:{fields}")
    res.detail = " | ".join(parts)[:1500]
    return res


AUTO_PIPELINES = {"gazette_json", "cabinet_json"}
# 同步时以官方源为准覆盖的字段;中文标题、摘要、分类是翻译环节的产物,不在其中
RAW_FIELDS = ("doc_no", "gazette", "dates", "sources", "status_id")


def merge_update(old: dict, new: dict) -> dict:
    """官方源里已入库记录的更新:原始字段以官方为准;泰文标题变了则清空中文结果,交给翻译环节重做。"""
    merged = json.loads(json.dumps(old))
    for k in RAW_FIELDS:
        if k in new:
            merged[k] = new[k]
    th_old = (old.get("titles") or {}).get("th", "")
    th_new = (new.get("titles") or {}).get("th", "")
    if th_new and th_new != th_old:
        merged.setdefault("titles", {})["th"] = th_new
        merged["titles"]["zh"] = ""
        merged["summary_zh"] = ""
        merged.setdefault("flags", {}).pop("skip", None)
    return merged


def upsert_jsonl(records: list[dict], run_at: str) -> tuple[list[dict], int, int]:
    """新记录追加、已有记录按官方源更新,原位改写 documents.jsonl(保持顺序,diff 只出现改动的行)。
    人工整理的条目(pipeline 不是官方接口)永远不被覆盖。返回 (新增或变动的记录, 新增数, 更新数)。"""
    if not records:
        return [], 0, 0
    path = POLICIES_DIR / "documents.jsonl"
    rows = read_jsonl(path)
    index = {r["uid"]: i for i, r in enumerate(rows)}
    touched: list[dict] = []
    added = updated = 0
    for rec in records:
        i = index.get(rec["uid"])
        if i is None:
            index[rec["uid"]] = len(rows)
            rows.append(rec)
            touched.append(rec)
            added += 1
            continue
        old = rows[i]
        if (old.get("provenance") or {}).get("pipeline") not in AUTO_PIPELINES:
            continue
        merged = merge_update(old, rec)
        if merged != old:
            merged.setdefault("provenance", {})["updated_at"] = run_at
            rows[i] = merged
            touched.append(merged)
            updated += 1
    if touched:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8")
    return touched, added, updated


def append_run(entry: dict) -> None:
    with (POLICIES_DIR / "runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_source_health(results: list[SourceResult], run_at: datetime) -> None:
    """同时写库和写 data/policies/sources.json,两边不漂移。"""
    with session_scope() as s:
        for r in results:
            obj = s.get(SourceHealth, r.id) or SourceHealth(id=r.id, name=r.name)
            obj.name, obj.url = r.name, r.url
            obj.status, obj.detail = r.status, r.detail
            obj.last_attempt_at = run_at
            if r.status == "ok":
                obj.last_ok_at = run_at
            s.add(obj)
        rows = s.scalars(select(SourceHealth)).all()
        payload = {"last_run_at": run_at.replace(microsecond=0).isoformat(),
                   "sources": [{"id": x.id, "name": x.name, "url": x.url, "status": x.status,
                                "last_ok": x.last_ok_at.replace(microsecond=0).isoformat()
                                if x.last_ok_at else None,
                                "detail": x.detail} for x in rows]}
    (POLICIES_DIR / "sources.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run_collection(trigger: str = "manual", dry_run: bool = False, backfill: bool = False) -> dict:
    init_db()
    started = datetime.now(BKK)
    t0 = time.monotonic()
    cutoff_date = date.fromordinal(started.date().toordinal() - settings.lookback_days)
    run_at_iso = started.replace(microsecond=0).isoformat()
    throttle = Throttle(settings.min_request_interval)

    run_id = None
    if not dry_run:
        with session_scope() as s:
            run = CollectRun(started_at=started, status="running", trigger=trigger)
            s.add(run)
            s.flush()
            run_id = run.id

    results = [collect_source(src, throttle, run_at_iso, cutoff_date, dry_run, backfill)
               for src in SOURCES]
    all_records = [r for res in results for r in res.records]
    ok_count = sum(1 for r in results if r.status == "ok")

    added = updated = appended = 0
    if not dry_run:
        # 新记录追加,已入库记录按官方源更新;只把有变动的记录写库
        touched, appended, updated = upsert_jsonl(all_records, run_at_iso)
        with session_scope() as s:
            added, _ = load_documents(s, touched, now=started)

    if not dry_run:
        write_source_health(results, started)

    status = "ok" if ok_count == len(results) else ("partial" if ok_count else "failed")
    detail = " | ".join(f"{r.id}={r.status}: {r.detail}" for r in results)
    duration = time.monotonic() - t0

    if not dry_run:
        finished = datetime.now(BKK)
        with session_scope() as s:
            run = s.get(CollectRun, run_id)
            run.finished_at = finished
            run.status = status
            run.added, run.updated = appended, updated
            run.skipped = len(all_records) - added - updated
            run.duration_s = duration
            run.detail = detail[:4000]
        # 运行记录也落到事实层:数据库重建(CI、换机器)后运行历史不丢,
        # 且「管道每天有没有在跑」本身就是需要审计的事实
        append_run({"started_at": started.replace(microsecond=0).isoformat(),
                    "finished_at": finished.replace(microsecond=0).isoformat(),
                    "status": status, "trigger": trigger,
                    "added": appended, "updated": updated, "backfill": backfill,
                    "duration_s": round(duration, 1), "detail": detail[:1000]})

    enrich_result = None
    if not dry_run and settings.enrich_after_collect:
        # 翻译分类:把刚采进来的泰文条目补成可呈现的记录。没有 API key 时自动跳过
        from .enrich import run_enrichment
        try:
            enrich_result = run_enrichment()
        except Exception:                      # 翻译失败不应让采集结果丢失
            log.exception("翻译分类失败,采集结果已保存,待下轮重试")
            enrich_result = {"status": "error"}

    if not dry_run and settings.export_after_collect:
        from .export import export_all
        export_all()

    log.info("采集完成 status=%s 新增=%d 更新=%d 源=%d/%d 耗时=%.1fs",
             status, added, updated, ok_count, len(results), duration)
    return {"run_id": run_id, "status": status, "added": appended, "updated": updated,
            "backfill": backfill, "lookback_since": cutoff_date.isoformat(),
            "appended_to_jsonl": appended, "sources_ok": ok_count, "enrich": enrich_result,
            "sources_total": len(results), "duration_s": round(duration, 1), "egress": egress_label(),
            "sources": [{"id": r.id, "status": r.status, "detail": r.detail} for r in results]}


def main() -> None:
    ap = argparse.ArgumentParser(description="每日政策数据采集")
    ap.add_argument("--dry-run", action="store_true", help="只探测源可达性,不写库不写文件")
    ap.add_argument("--trigger", default="manual")
    ap.add_argument("--backfill", action="store_true",
                    help=f"回填:下载回溯期(LOOKBACK_DAYS,当前 {settings.lookback_days} 天)内的全部月份")
    ap.add_argument("--strict", action="store_true",
                    help="所有源都失败时以退出码 2 结束 —— 给 CI 用,让失败变红、触发通知")
    args = ap.parse_args()
    out = run_collection(trigger=args.trigger, dry_run=args.dry_run, backfill=args.backfill)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.strict and out["status"] == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
