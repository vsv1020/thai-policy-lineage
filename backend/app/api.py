# -*- coding: utf-8 -*-
"""FastAPI 服务。

    uvicorn app.main:app --reload            # 开发
    uvicorn app.main:app --host 0.0.0.0 --port 8000   # 生产(前面挂 nginx/caddy)

接口返回的形状与 data/site/*.json 完全一致 —— 前端一份渲染代码,
既能吃 API 也能吃静态文件,后端挂了自动降级。
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import analytics as A
from .analytics import iso_bkk
from .config import BKK, settings
from .db import get_session
from .models import (Agency, CollectRun, Document, DocumentAgency, DocumentDomain, Domain,
                     Goal, Instrument, InstrumentClass, Issue, LegalForm, Status)

router = APIRouter(prefix=settings.api_prefix)


@router.get("/health", summary="存活与数据概况")
def health(s: Session = Depends(get_session)) -> dict:
    last = s.scalars(select(CollectRun).order_by(CollectRun.started_at.desc()).limit(1)).first()
    return {
        "ok": True,
        "documents": s.scalar(select(func.count(Document.uid))),
        "issues": s.scalar(select(func.count(Issue.issue_id))),
        "last_run": {
            "started_at": iso_bkk(last.started_at) if last else None,
            "status": last.status if last else None,
            "added": last.added if last else 0,
            "updated": last.updated if last else 0,
        } if last else None,
    }


@router.get("/overview", summary="首页:政策流 + 风向 + 生效日历 + 源状态")
def overview(s: Session = Depends(get_session)) -> dict:
    return A.overview(s)


@router.get("/trends", summary="趋势看板聚合")
def trends(s: Session = Depends(get_session)) -> dict:
    return A.trends(s)


@router.get("/dimensions", summary="政策维度七维分析")
def dimensions(s: Session = Depends(get_session)) -> dict:
    return A.dimensions(s)


@router.get("/lineage", summary="议题演进脉络")
def lineage(s: Session = Depends(get_session)) -> dict:
    return A.lineage(s)


@router.get("/vocab", summary="受控词表(供前端下拉与配色)")
def vocab(s: Session = Depends(get_session)) -> dict:
    return {
        "domains": [{"id": d.id, "zh": d.zh, "th": d.th, "chip": d.chip}
                    for d in s.scalars(select(Domain)).all()],
        "agencies": [{"id": a.id, "zh": a.zh, "abbr": a.abbr}
                     for a in s.scalars(select(Agency).order_by(Agency.zh)).all()],
        "legal_forms": [{"id": f.id, "zh": f.zh, "abbr": f.abbr, "stability": f.stability}
                        for f in s.scalars(
                            select(LegalForm).order_by(LegalForm.stability.desc())).all()],
        "statuses": [{"id": x.id, "zh": x.zh, "in_force": x.in_force}
                     for x in s.scalars(select(Status)).all()],
        "instrument_classes": [{"id": c.id, "zh": c.zh, "desc": c.desc, "color": c.color}
                               for c in s.scalars(select(InstrumentClass)).all()],
        "instruments": [{"id": i.id, "zh": i.zh, "class": i.class_id}
                        for i in s.scalars(select(Instrument)).all()],
        "goals": [{"id": g.id, "zh": g.zh} for g in s.scalars(select(Goal)).all()],
    }


@router.get("/documents", summary="分面检索")
def list_documents(
    s: Session = Depends(get_session),
    q: str | None = Query(None, description="标题/摘要关键词(中泰文均可)"),
    domain: list[str] | None = Query(None),
    agency: list[str] | None = Query(None),
    legal_form: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    direction: str | None = Query(None, pattern="^(tight|loose|neutral)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    pending_gazette: bool = Query(False, description="只看「已决议但未刊公报」的窗口期条目"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(Document)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Document.title_zh.like(like), Document.title_th.like(like),
                             Document.summary_zh.like(like), Document.doc_no.like(like)))
    if domain:
        stmt = stmt.where(Document.uid.in_(
            select(DocumentDomain.uid).where(DocumentDomain.domain_id.in_(domain))))
    if agency:
        stmt = stmt.where(Document.uid.in_(
            select(DocumentAgency.uid).where(DocumentAgency.agency_id.in_(agency))))
    if legal_form:
        stmt = stmt.where(Document.legal_form_id.in_(legal_form))
    if status:
        stmt = stmt.where(Document.status_id.in_(status))
    if direction:
        stmt = stmt.where(Document.direction == direction)
    if date_from:
        stmt = stmt.where(Document.display_date >= date_from)
    if date_to:
        stmt = stmt.where(Document.display_date <= date_to)
    if pending_gazette:
        stmt = stmt.where(Document.status_id == "pending_gazette")

    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    docs = s.scalars(
        stmt.order_by(Document.display_date.desc().nullslast()).limit(limit).offset(offset)
    ).all()
    today = A._today(s)
    return {"total": total, "limit": limit, "offset": offset,
            "items": [A.document_view(s, d, today) for d in docs]}


@router.get("/documents/{uid}", summary="单份文件全字段(含关系与溯源)")
def get_document(uid: str, s: Session = Depends(get_session)) -> dict:
    doc = s.get(Document, uid)
    if doc is None:
        raise HTTPException(404, f"没有这份文件: {uid}")
    today = A._today(s)
    view = A.document_view(s, doc, today)
    view["dates"] = {
        "resolved_at": doc.resolved_at.isoformat() if doc.resolved_at else None,
        "published_at": doc.published_at.isoformat() if doc.published_at else None,
        "effective_from": doc.effective_from.isoformat() if doc.effective_from else None,
        "effective_to": doc.effective_to.isoformat() if doc.effective_to else None,
        "comment_deadline": doc.comment_deadline.isoformat() if doc.comment_deadline else None,
    }
    view["confidence"] = {"dates": doc.confidence_dates, "doc_no": doc.confidence_doc_no}
    view["relations"] = [{"type": r.type, "uid": r.dst_uid} for r in doc.relations_out]
    view["sources"] = [{"role": x.role, "url": x.url, "note": x.note} for x in doc.sources]
    view["agencies"] = [x.agency_id for x in sorted(doc.agencies, key=lambda x: x.seq)]
    view["domains"] = [x.domain_id for x in sorted(doc.domains, key=lambda x: x.seq)]
    view["instruments"] = [x.instrument_id for x in doc.instruments]
    view["goals"] = [x.goal_id for x in doc.goals]
    view["parties"] = [{"party_id": x.party_id, "stance": x.stance} for x in doc.parties]
    view["implementation_stage"] = doc.implementation_stage_id
    view["note"] = doc.note
    return view


@router.get("/runs", summary="采集运行历史")
def runs(s: Session = Depends(get_session), limit: int = Query(20, ge=1, le=100)) -> dict:
    rows = s.scalars(
        select(CollectRun).order_by(CollectRun.started_at.desc()).limit(limit)).all()
    return {"items": [{"id": r.id, "started_at": iso_bkk(r.started_at),
                       "finished_at": iso_bkk(r.finished_at),
                       "status": r.status, "trigger": r.trigger, "added": r.added,
                       "updated": r.updated, "skipped": r.skipped,
                       "duration_s": round(r.duration_s, 1), "detail": r.detail}
                      for r in rows]}
