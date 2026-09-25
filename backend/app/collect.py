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


def fetch_ckan(dataset: str, throttle: Throttle) -> list[dict]:
    """取 CKAN 数据集的 resource 列表。失败抛异常,由调用方记 error。"""
    throttle.wait()
    with httpx.Client(timeout=settings.http_timeout,
                      headers={"User-Agent": UA, "Accept": "application/json"},
                      follow_redirects=True) as c:
        r = c.get(f"{CKAN_BASE}/api/3/action/package_show", params={"id": dataset})
        r.raise_for_status()
        payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show 返回 success=false: {dataset}")
    return payload["result"].get("resources", [])


def fetch_resource(url: str, throttle: Throttle) -> Any:
    throttle.wait()
    with httpx.Client(timeout=settings.http_timeout,
                      headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


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

    series = pick(rec, ["series", "ประเภท", "type", "category"]).strip()[:8]
    if series and series not in SERIES_KEEP:
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
    title = pick(rec, ["title", "เรื่อง", "ชื่อเรื่อง", "subject", "name"]).strip()
    if not title:
        return None, "无标题"
    ok, why = passes_red_lines(title)
    if not ok:
        return None, why
    resolved = normalize_date(pick(rec, ["date", "วันที่มีมติ", "วันที่", "resolution_date"]))
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
                   dry_run: bool) -> SourceResult:
    res = SourceResult(id=src["id"], name=src["name"], url=src["url"])
    try:
        resources = fetch_ckan(src["dataset"], throttle)
    except Exception as exc:
        res.status = "error"
        res.detail = f"{type(exc).__name__}: {exc}"[:400]
        return res

    json_res = [r for r in resources
                if (r.get("format") or "").lower() == "json"] or resources
    json_res.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)
    if not json_res:
        res.status = "error"
        res.detail = "数据集里没有可用 resource"
        return res
    if dry_run:
        res.status = "ok"
        res.detail = f"可达,{len(json_res)} 个 resource(dry-run 未下载)"
        return res

    normalize = normalize_gazette if src["id"] == "gazette_json" else normalize_cabinet
    skipped: dict[str, int] = {}
    try:
        payload = fetch_resource(json_res[0]["url"], throttle)
    except Exception as exc:
        res.status = "error"
        res.detail = f"resource 下载失败 {type(exc).__name__}: {exc}"[:400]
        return res

    for rec in iter_records(payload):
        norm, why = normalize(rec, run_at)
        if norm is None:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        d = norm["dates"]
        stamp = d.get("published_at") or d.get("resolved_at")
        if stamp and date.fromisoformat(stamp) < cutoff:
            skipped["早于时间窗"] = skipped.get("早于时间窗", 0) + 1
            continue
        res.records.append(norm)

    res.status = "ok"
    res.detail = (f"{json_res[0].get('name', 'resource')}:收 {len(res.records)} 条"
                  + (f",跳过 {sum(skipped.values())} 条(" +
                     ", ".join(f"{k}×{v}" for k, v in sorted(skipped.items())) + ")"
                     if skipped else ""))
    return res


def append_jsonl(records: list[dict]) -> int:
    """新记录追加到 documents.jsonl —— git 里保留可 review 的事实记录。"""
    if not records:
        return 0
    path = POLICIES_DIR / "documents.jsonl"
    existing = {r["uid"] for r in read_jsonl(path)}
    fresh = [r for r in records if r["uid"] not in existing]
    if fresh:
        with path.open("a", encoding="utf-8") as fh:
            for r in fresh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(fresh)


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


def run_collection(trigger: str = "manual", dry_run: bool = False) -> dict:
    init_db()
    started = datetime.now(BKK)
    t0 = time.monotonic()
    cutoff = (started.date().toordinal() - settings.recency_days)
    cutoff_date = date.fromordinal(cutoff)
    run_at_iso = started.replace(microsecond=0).isoformat()
    throttle = Throttle(settings.min_request_interval)

    run_id = None
    if not dry_run:
        with session_scope() as s:
            run = CollectRun(started_at=started, status="running", trigger=trigger)
            s.add(run)
            s.flush()
            run_id = run.id

    results = [collect_source(src, throttle, run_at_iso, cutoff_date, dry_run)
               for src in SOURCES]
    all_records = [r for res in results for r in res.records]
    ok_count = sum(1 for r in results if r.status == "ok")

    added = updated = appended = 0
    if not dry_run:
        appended = append_jsonl(all_records)
        with session_scope() as s:
            added, updated = load_documents(s, all_records, now=started)

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
            run.added, run.updated = max(added, appended), updated
            run.skipped = len(all_records) - added - updated
            run.duration_s = duration
            run.detail = detail[:4000]
        # 运行记录也落到事实层:数据库重建(CI、换机器)后运行历史不丢,
        # 且「管道每天有没有在跑」本身就是需要审计的事实
        append_run({"started_at": started.replace(microsecond=0).isoformat(),
                    "finished_at": finished.replace(microsecond=0).isoformat(),
                    "status": status, "trigger": trigger,
                    "added": max(added, appended), "updated": updated,
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
    return {"run_id": run_id, "status": status, "added": added, "updated": updated,
            "appended_to_jsonl": appended, "sources_ok": ok_count, "enrich": enrich_result,
            "sources_total": len(results), "duration_s": round(duration, 1),
            "sources": [{"id": r.id, "status": r.status, "detail": r.detail} for r in results]}


def main() -> None:
    ap = argparse.ArgumentParser(description="每日政策数据采集")
    ap.add_argument("--dry-run", action="store_true", help="只探测源可达性,不写库不写文件")
    ap.add_argument("--trigger", default="manual")
    ap.add_argument("--strict", action="store_true",
                    help="所有源都失败时以退出码 2 结束 —— 给 CI 用,让失败变红、触发通知")
    args = ap.parse_args()
    out = run_collection(trigger=args.trigger, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.strict and out["status"] == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
