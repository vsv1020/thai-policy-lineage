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
    """A implements B 必须伴随 B implemented_by A,否则脉络图少一条边。"""
    fwd = session.scalars(select(DocumentRelation.dst_uid).where(
        DocumentRelation.src_uid == "TH-RD-2565-DG-427",
        DocumentRelation.type == "implements")).all()
    assert "TH-RD-2565-DECREE-743" in fwd
    back = session.scalars(select(DocumentRelation.dst_uid).where(
        DocumentRelation.src_uid == "TH-RD-2565-DECREE-743",
        DocumentRelation.type == "implemented_by")).all()
    assert "TH-RD-2565-DG-427" in back


def test_dates_are_separate_columns(session):
    """三态并存:已决议 + 未刊公报 + 未生效。这是整个数据模型存在的理由。"""
    doc = session.get(Document, "TH-CAB-20260519-VISAFREE-30D")
    assert doc.resolved_at is not None
    assert doc.published_at is None
    assert doc.effective_from is None
    assert doc.status_id == "pending_gazette"
    assert doc.display_date == doc.resolved_at   # 没有刊登日就退到决议日


def test_retroactive_effective_date_allowed(session):
    """生效日可以早于刊登/公布日(追溯适用),不能被当成脏数据。"""
    doc = session.get(Document, "TH-BOI-20260115-MEASURES-2026")
    assert doc.effective_from < doc.published_at


def test_no_fabricated_demo_data_remains(session):
    """事实层不允许再有虚构演示条目 —— 编造的公报号是负资产。"""
    demos = session.scalars(select(Document.uid).where(Document.pipeline == "demo")).all()
    assert demos == [], f"仍存在演示数据: {demos}"


def test_every_document_has_agency_and_date(session):
    """红线三的库级不变量:没有发文机关或没有任何日期的条目不得入库。"""
    for doc in session.scalars(select(Document)).all():
        assert doc.agencies, f"{doc.uid} 没有发文机关"
        assert doc.display_date is not None, f"{doc.uid} 没有任何可用日期"


def test_no_fabricated_source_urls(session):
    """拿不到官方链接就必须留空,不能填二手链接冒充原文。"""
    from app.models import DocumentSource
    for src in session.scalars(select(DocumentSource)).all():
        assert src.url == "" or src.url.startswith("http")
        if src.role == "official":
            assert src.url, "official 来源必须有真实链接,否则应标为 secondary"


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
        "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/documents/FIXTURE.pdf"}],
    }
    with pytest.raises(IntegrityError):
        load_documents(session, [bad])
    session.rollback()
