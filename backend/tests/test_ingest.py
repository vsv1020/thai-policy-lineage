# -*- coding: utf-8 -*-
"""入库层:幂等、外键约束、日期语义。"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ingest import ingest_all, load_documents
from app.models import Document, DocumentAgency, DocumentDomain, DocumentRelation


def test_ingest_loaded_documents(session):
    assert session.scalar(select(func.count(Document.uid))) >= 12


def test_ingest_is_idempotent(session):
    before = session.scalar(select(func.count(Document.uid)))
    ingest_all()                      # 不 reset,重复载入
    after = session.scalar(select(func.count(Document.uid)))
    assert before == after, "重复载入不应新增行"


def test_multi_agency_document_is_stored_as_rows(session):
    """联署必须落成多行,不是一个逗号串 —— 维度五靠这个。"""
    rows = session.scalars(select(DocumentAgency.agency_id)
                           .where(DocumentAgency.uid == "TH-CAB-20260519-VISAFREE-30D")).all()
    assert set(rows) == {"cabinet", "moi"}


def test_multi_domain_primary_is_seq_zero(session):
    rows = session.execute(
        select(DocumentDomain.domain_id, DocumentDomain.seq)
        .where(DocumentDomain.uid == "TH-IMM-20260801-THIM-MANDATORY")).all()
    by_seq = {seq: did for did, seq in rows}
    assert by_seq[0] == "visa", "主领域必须是 seq=0,它决定 chip 配色"
    assert "digital" in by_seq.values()


def test_relations_are_bidirectional(session):
    """A supersedes B 必须伴随 B superseded_by A,否则脉络图少一条边。"""
    fwd = session.scalars(select(DocumentRelation.dst_uid).where(
        DocumentRelation.src_uid == "TH-RD-20260808-FOREIGN-INCOME",
        DocumentRelation.type == "supersedes")).all()
    assert "TH-RD-2566-POR-161" in fwd
    back = session.scalars(select(DocumentRelation.dst_uid).where(
        DocumentRelation.src_uid == "TH-RD-2566-POR-161",
        DocumentRelation.type == "superseded_by")).all()
    assert "TH-RD-20260808-FOREIGN-INCOME" in back


def test_dates_are_separate_columns(session):
    """三态并存:已决议 + 未刊公报 + 未生效。这是整个数据模型存在的理由。"""
    doc = session.get(Document, "TH-CAB-20260519-VISAFREE-30D")
    assert doc.resolved_at is not None
    assert doc.published_at is None
    assert doc.effective_from is None
    assert doc.status_id == "pending_gazette"
    assert doc.display_date == doc.resolved_at   # 没有刊登日就退到决议日


def test_retroactive_effective_date_allowed(session):
    """生效日可以早于刊登日(追溯生效),不能被当成脏数据。"""
    doc = session.get(Document, "TH-RD-20260808-FOREIGN-INCOME")
    assert doc.effective_from < doc.published_at


def test_unknown_vocab_id_is_rejected_by_foreign_key(session):
    """词表是真表 —— 未知 id 由数据库拒绝,不依赖应用层记得校验。"""
    bad = {
        "uid": "TH-XX-20260101-BAD", "issue_id": None,
        "titles": {"zh": "坏数据"}, "summary_zh": "",
        "agency_ids": ["rd"], "domain_ids": ["visa"],
        "legal_form_id": "prakat", "status_id": "in_force",
        "direction": {"value": "neutral", "confidence": "none"},
        "dates": {"published_at": "2026-01-01"},
        "instrument_ids": ["NOT_A_REAL_INSTRUMENT"],
        "relations": [], "provenance": {"pipeline": "manual"}, "flags": {},
    }
    with pytest.raises(IntegrityError):
        load_documents(session, [bad])
    session.rollback()
