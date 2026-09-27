# -*- coding: utf-8 -*-
"""前台只呈现可考证的内容:必须有泰国政府域名(*.go.th)的官方原文链接。
没有原文的条目只留在事实层(JSONL),不进库、不上页面、不进分析、不花钱翻译。"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app import analytics as A
from app.ingest import is_official_url, presentable
from app.models import Deadline, Document

UNSOURCED = "TH-DBD-2569-ORDER-1"        # 样例数据里故意不给官方链接的一条
ROOT = Path(__file__).resolve().parents[2]


def _rec(**sources):
    return {"titles": {"zh": "中文标题"}, "flags": {}, "sources": [sources] if sources else []}


def test_official_url_must_be_thai_government_domain():
    assert is_official_url("https://ratchakitcha.soc.go.th/documents/111315.pdf")
    assert is_official_url("https://www.rd.go.th/12345.html")
    assert not is_official_url("https://www.somelawfirm.co.th/news/tax")     # 律所、媒体不算
    assert not is_official_url("https://go.th.evil.example/x")              # 伪装域名
    assert not is_official_url("ftp://ratchakitcha.soc.go.th/x")
    assert not is_official_url("")


def test_presentable_requires_official_source():
    assert not presentable(_rec())
    assert not presentable(_rec(role="secondary", url="https://www.rd.go.th/x"))     # 角色必须是 official
    assert not presentable(_rec(role="official", url="https://news.example.com/x"))  # 域名必须是 go.th
    assert presentable(_rec(role="official", url="https://www.rd.go.th/x"))


def test_unsourced_document_is_not_in_database(session):
    uids = set(session.scalars(select(Document.uid)).all())
    assert UNSOURCED not in uids
    assert len(uids) >= 10


def test_conflicts_and_lineage_only_reference_visible_documents(session):
    uids = set(session.scalars(select(Document.uid)).all())
    for c in A.dim6_conflicts(session)["items"]:
        assert all(x["uid"] in uids for x in c["sides"] if x.get("uid"))
    for it in A.lineage(session)["issues"]:
        assert any(st["uid"] for st in it["stages"]), "议题至少关联一份已考证文件"
        assert all(st["uid"] in uids for st in it["stages"] if st["uid"])


def test_deadlines_need_official_source(session):
    ids = set(session.scalars(select(Deadline.id)).all())
    assert len(ids) == 3, "样例中只有 3 条截止日带 *.go.th 出处"


def test_translation_skips_unsourced(monkeypatch):
    from app import enrich as E
    rec = {"titles": {"zh": "", "th": "ประกาศ"}, "flags": {}, "sources": []}
    assert not E.is_pending(rec)
    rec["sources"] = [{"role": "official", "url": "https://ratchakitcha.soc.go.th/documents/1.pdf"}]
    assert E.is_pending(rec)


def test_no_missing_source_wording_in_frontend():
    for f in ("js/detail.js", "backend/app/seo.py", "index.html"):
        assert "尚未取得官方原文" not in (ROOT / f).read_text(encoding="utf-8"), f
