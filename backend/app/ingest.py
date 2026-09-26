# -*- coding: utf-8 -*-
"""把 data/vocab.json 与 data/policies/*.jsonl 载入数据库。

    python3 -m app.ingest            # 建表 + 载入词表 + 载入事实层
    python3 -m app.ingest --reset    # 先清空事实表再载入

幂等:同一份文件反复载入结果一致(upsert 语义)。JSONL 仍是 git 里可 review 的
事实记录,数据库是它的运行时投影 —— 采集流程写 JSONL 也写库,两边不会漂移。
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import BKK, DATA_DIR, POLICIES_DIR
from .db import engine, init_db, session_scope
from .models import (Agency, Base, CollectRun, Conflict, Deadline, Document, DocumentAgency,
                     DocumentDomain, DocumentGoal, DocumentInstrument, DocumentParty,
                     DocumentRelation, DocumentSource, Domain, Goal, ImplementationStage,
                     Instrument, InstrumentClass, Issue, LegalForm, Party, SourceHealth, Status)

DISPLAY_DATE_ORDER = ("published_at", "resolved_at", "effective_from", "comment_deadline")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _date(v) -> date | None:
    return date.fromisoformat(v) if v else None


def _dt(v) -> datetime | None:
    if not v:
        return None
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=BKK)


def load_vocab(s: Session) -> dict:
    """词表 → 词表各表。先载词表,后面事实层的外键才有得指。"""
    vocab = json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8"))

    def upsert(model, rows, mapper):
        for r in rows:
            obj = s.get(model, r["id"])
            values = mapper(r)
            if obj is None:
                s.add(model(id=r["id"], **values))
            else:
                for k, val in values.items():
                    setattr(obj, k, val)

    upsert(Domain, vocab["domains"],
           lambda r: dict(zh=r["zh"], th=r.get("th", ""), en=r.get("en", ""), chip=r.get("chip", "")))
    upsert(Agency, vocab["agencies"],
           lambda r: dict(zh=r["zh"], th=r.get("th", ""), abbr=r.get("abbr") or "",
                          ministry=r.get("ministry")))
    upsert(LegalForm, vocab["legal_forms"],
           lambda r: dict(zh=r["zh"], th=r.get("th", ""), abbr=r.get("abbr", ""),
                          stability=r.get("stability", 1),
                          justiciable=bool(r.get("justiciable")), note=r.get("note", "")))
    upsert(Status, vocab["statuses"],
           lambda r: dict(zh=r["zh"], pill=r.get("pill", ""), in_force=bool(r.get("in_force"))))
    upsert(InstrumentClass, vocab["instrument_classes"],
           lambda r: dict(zh=r["zh"], desc=r.get("desc", ""), color=r.get("color", "")))
    upsert(Instrument, vocab["instruments"],
           lambda r: dict(zh=r["zh"], class_id=r["class"]))
    upsert(Goal, vocab["goals"], lambda r: dict(zh=r["zh"]))
    upsert(ImplementationStage, vocab["implementation_stages"],
           lambda r: dict(zh=r["zh"], seq=r.get("seq", 0)))
    upsert(Party, vocab["parties"], lambda r: dict(zh=r["zh"]))
    s.flush()
    return vocab


def display_date_of(dates: dict) -> date | None:
    for f in DISPLAY_DATE_ORDER:
        if dates.get(f):
            return _date(dates[f])
    return None


def presentable(r: dict) -> bool:
    """有中文标题且未被标记跳过 —— 才进数据库、才会被呈现。"""
    return bool((r.get("titles") or {}).get("zh")) and not (r.get("flags") or {}).get("skip")


def load_documents(s: Session, records: list[dict], now: datetime | None = None) -> tuple[int, int]:
    """返回 (新增, 更新)。"""
    now = now or datetime.now(BKK)
    added = updated = 0
    for r in records:
        uid = r["uid"]
        if not presentable(r):
            # 待翻译或判定无关的条目只留在 JSONL(审计记录),不进数据库 ——
            # 否则首页会出现空标题。已在库里的(例如刚被标 skip)要移除。
            stale = s.get(Document, uid)
            if stale is not None:
                s.delete(stale)
                s.flush()
            continue
        doc = s.get(Document, uid)
        is_new = doc is None
        if is_new:
            doc = Document(uid=uid, first_seen_at=now)
            s.add(doc)

        dates = r.get("dates") or {}
        gz = r.get("gazette") or {}
        prov = r.get("provenance") or {}
        conf = r.get("confidence") or {}
        titles = r.get("titles") or {}

        doc.issue_id = r.get("issue_id")
        doc.title_zh = titles.get("zh", "")
        doc.title_th = titles.get("th", "") or ""
        doc.title_en = titles.get("en", "") or ""
        doc.summary_zh = r.get("summary_zh", "")
        doc.legal_form_id = r["legal_form_id"]
        doc.status_id = r["status_id"]
        doc.implementation_stage_id = r.get("implementation_stage")
        d = r.get("direction") or {}
        doc.direction = d.get("value", "neutral")
        doc.direction_confidence = d.get("confidence", "none")
        doc.direction_method = d.get("method", "manual")
        doc.doc_no = r.get("doc_no") or ""
        doc.gazette_series = (gz.get("series") or "") if gz else ""
        doc.gazette_volume = gz.get("volume") if gz else None
        doc.gazette_part = (gz.get("part") or "") if gz else ""
        doc.resolved_at = _date(dates.get("resolved_at"))
        doc.published_at = _date(dates.get("published_at"))
        doc.effective_from = _date(dates.get("effective_from"))
        doc.effective_to = _date(dates.get("effective_to"))
        doc.comment_deadline = _date(dates.get("comment_deadline"))
        doc.display_date = display_date_of(dates)
        doc.pipeline = prov.get("pipeline", "manual")
        doc.run_at = _dt(prov.get("run_at"))
        doc.verified = bool(prov.get("verified"))
        doc.verified_at = prov.get("verified_at") or ""
        doc.confidence_dates = conf.get("dates", "none")
        doc.confidence_doc_no = conf.get("doc_no", "none")
        doc.subjects_csv = ",".join(r.get("subjects") or [])
        doc.note = r.get("note", "")
        doc.has_detail_page = bool((r.get("flags") or {}).get("has_detail_page"))
        doc.updated_at_ts = now
        s.flush()

        # 关联表整体重建 —— 比逐条 diff 简单,量级完全撑得住
        for model in (DocumentAgency, DocumentDomain, DocumentInstrument,
                      DocumentGoal, DocumentParty, DocumentSource):
            s.execute(delete(model).where(model.uid == uid))
        s.execute(delete(DocumentRelation).where(DocumentRelation.src_uid == uid))

        for i, aid in enumerate(r.get("agency_ids") or []):
            s.add(DocumentAgency(uid=uid, agency_id=aid, seq=i))
        for i, did in enumerate(r.get("domain_ids") or []):
            s.add(DocumentDomain(uid=uid, domain_id=did, seq=i))
        for iid in r.get("instrument_ids") or []:
            s.add(DocumentInstrument(uid=uid, instrument_id=iid))
        for gid in r.get("goal_ids") or []:
            s.add(DocumentGoal(uid=uid, goal_id=gid))
        for ap in r.get("affected_parties") or []:
            s.add(DocumentParty(uid=uid, party_id=ap["party_id"],
                                stance=ap.get("stance", "neutral")))
        for src in r.get("sources") or []:
            s.add(DocumentSource(uid=uid, role=src.get("role", "secondary"),
                                 url=src.get("url") or "", note=src.get("note", "")))
        for rel in r.get("relations") or []:
            s.add(DocumentRelation(src_uid=uid, type=rel["type"], dst_uid=rel["uid"]))
        s.flush()
        added += is_new
        updated += not is_new
    return added, updated


def load_issues(s: Session, records: list[dict]) -> int:
    for r in records:
        obj = s.get(Issue, r["issue_id"]) or Issue(issue_id=r["issue_id"])
        obj.title_zh = r["title_zh"]
        obj.title_th = r.get("title_th", "")
        obj.summary_zh = r.get("summary_zh", "")
        obj.watch = r.get("watch", "")
        obj.domains_csv = ",".join(r.get("domain_ids") or [])
        obj.stages_json = json.dumps(r.get("stages") or [], ensure_ascii=False)
        s.add(obj)
    s.flush()
    return len(records)


def load_conflicts(s: Session, records: list[dict]) -> int:
    for r in records:
        obj = s.get(Conflict, r["id"]) or Conflict(id=r["id"])
        obj.severity = r.get("severity", "med")
        obj.title_zh = r["title_zh"]
        obj.domains_csv = ",".join(r.get("domain_ids") or [])
        obj.impact_zh = r.get("impact_zh", "")
        obj.detected_by = r.get("detected_by", "manual")
        obj.confidence = r.get("confidence", "med")
        obj.sides_json = json.dumps(r.get("sides") or [], ensure_ascii=False)
        s.add(obj)
    s.flush()
    return len(records)


def load_deadlines(s: Session, records: list[dict]) -> int:
    for r in records:
        obj = s.get(Deadline, r["id"]) or Deadline(id=r["id"])
        obj.title_zh = r["title_zh"]
        obj.domains_csv = ",".join(r.get("domain_ids") or [])
        obj.agencies_csv = ",".join(r.get("agency_ids") or [])
        obj.recurrence_json = json.dumps(r.get("recurrence") or {}, ensure_ascii=False)
        obj.note = r.get("note", "")
        obj.confidence = r.get("confidence", "med")
        s.add(obj)
    s.flush()
    return len(records)


def load_source_health(s: Session, payload: dict) -> int:
    last_run = _dt(payload.get("last_run_at"))
    for r in payload.get("sources") or []:
        obj = s.get(SourceHealth, r["id"]) or SourceHealth(id=r["id"], name=r.get("name", r["id"]))
        obj.name = r.get("name", r["id"])
        obj.url = r.get("url", "") or ""
        obj.status = r.get("status", "unattempted")
        obj.last_attempt_at = last_run
        obj.last_ok_at = _dt(r.get("last_ok"))
        obj.detail = r.get("detail", "")
        s.add(obj)
    s.flush()
    return len(payload.get("sources") or [])


def load_runs(s: Session, records: list[dict]) -> int:
    """运行历史整表重建 —— runs.jsonl 是唯一来源。"""
    s.execute(delete(CollectRun))
    for r in records:
        s.add(CollectRun(started_at=_dt(r["started_at"]), finished_at=_dt(r.get("finished_at")),
                         status=r.get("status", "unknown"), trigger=r.get("trigger", "manual"),
                         added=r.get("added", 0), updated=r.get("updated", 0),
                         duration_s=r.get("duration_s", 0.0), detail=r.get("detail", "")))
    s.flush()
    return len(records)


def reset_facts(s: Session) -> None:
    """只清事实表,词表保留(词表是配置,不是数据)。"""
    for model in (DocumentRelation, DocumentSource, DocumentParty, DocumentGoal,
                  DocumentInstrument, DocumentDomain, DocumentAgency,
                  Document, Issue, Conflict, Deadline):
        s.execute(delete(model))
    s.flush()


def ingest_all(reset: bool = False) -> dict:
    init_db()
    with session_scope() as s:
        load_vocab(s)
        if reset:
            reset_facts(s)
        # 议题先于文件 —— documents.issue_id 是外键
        n_issues = load_issues(s, read_jsonl(POLICIES_DIR / "issues.jsonl"))
        added, updated = load_documents(s, read_jsonl(POLICIES_DIR / "documents.jsonl"))
        n_conf = load_conflicts(s, read_jsonl(POLICIES_DIR / "conflicts.jsonl"))
        n_dl = load_deadlines(s, read_jsonl(POLICIES_DIR / "deadlines.jsonl"))
        sh_path = POLICIES_DIR / "sources.json"
        n_sh = load_source_health(
            s, json.loads(sh_path.read_text(encoding="utf-8"))) if sh_path.exists() else 0
        n_runs = load_runs(s, read_jsonl(POLICIES_DIR / "runs.jsonl"))
        return {"documents_added": added, "documents_updated": updated, "issues": n_issues,
                "conflicts": n_conf, "deadlines": n_dl, "sources": n_sh, "runs": n_runs}


def main() -> None:
    ap = argparse.ArgumentParser(description="载入词表与事实层到数据库")
    ap.add_argument("--reset", action="store_true", help="先清空事实表(词表保留)")
    args = ap.parse_args()
    stats = ingest_all(reset=args.reset)
    print(f"入库完成 [{engine.url.render_as_string(hide_password=True)}]")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
