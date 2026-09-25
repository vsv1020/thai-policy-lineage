# -*- coding: utf-8 -*-
"""翻译分类:模型一律 mock。测的是护栏,不是模型质量。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import enrich as E


def _raw(uid="TH-GAZ-20260901-ABC", th="ประกาศกรมสรรพากร เรื่อง ภาษีเงินได้"):
    return {"uid": uid, "issue_id": None, "titles": {"zh": "", "th": th, "en": ""},
            "summary_zh": "", "instrument_ids": [], "goal_ids": [], "implementation_stage": None,
            "subjects": [], "agency_ids": ["cabinet"], "domain_ids": ["biz"],
            "legal_form_id": "prakat", "status_id": "gazetted",
            "direction": {"value": "neutral", "confidence": "none", "method": "none"},
            "doc_no": "ง 1/2", "gazette": None,
            "dates": {"resolved_at": None, "published_at": "2026-09-01", "effective_from": None,
                      "effective_to": None, "comment_deadline": None},
            "affected_parties": [], "relations": [], "sources": [],
            "provenance": {"pipeline": "gazette_json", "run_at": None, "verified": False,
                           "verified_at": None},
            "confidence": {"dates": "high", "doc_no": "high"}, "flags": {}, "note": ""}


GOOD = {"relevant": True, "title_zh": "税务厅公告:个人所得税", "summary_zh": "据标题,本文件涉及个税。",
        "agency_ids": ["rd"], "domain_ids": ["tax"], "legal_form_id": "prakat",
        "instrument_ids": ["tax_incentive"], "goal_ids": ["fiscal_revenue"],
        "implementation_stage": "implementing_rule", "direction": "neutral",
        "direction_confidence": "low",
        "affected_parties": [{"party_id": "foreign_resident", "stance": "neutral"}]}


class FakeClient:
    """模拟 client.beta.messages.create;记录调用次数与请求。"""
    def __init__(self, payload=GOOD, stop="end_turn"):
        self.calls = []
        self.payload, self.stop = payload, stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_schema_enums_come_from_vocab():
    v = E._vocab()
    sch = E.output_schema(v)
    assert set(sch["properties"]["domain_ids"]["items"]["enum"]) == {d["id"] for d in v["domains"]}
    assert sch["additionalProperties"] is False


def test_apply_marks_llm_and_unverified():
    v = E._vocab()
    out = E.apply_enrichment(_raw(), GOOD, v, "claude-opus-5")
    assert out["titles"]["zh"] == GOOD["title_zh"]
    assert out["provenance"]["verified"] is False, "模型产出永远不算人工复核"
    assert out["direction"]["method"] == "llm"
    assert out["agency_ids"] == ["rd"] and out["domain_ids"] == ["tax"]


def test_apply_drops_ids_outside_vocab():
    """schema 之外的第二道闸:就算模型返回了词表外 id 也会被丢掉。"""
    v = E._vocab()
    bad = dict(GOOD, domain_ids=["tax", "NOT_REAL"], instrument_ids=["fake"],
               affected_parties=[{"party_id": "aliens", "stance": "support"}])
    out = E.apply_enrichment(_raw(), bad, v, "m")
    assert out["domain_ids"] == ["tax"]
    assert out["instrument_ids"] == []
    assert out["affected_parties"] == []


def test_irrelevant_is_flagged_skip():
    v = E._vocab()
    out = E.apply_enrichment(_raw(), dict(GOOD, relevant=False), v, "m")
    assert out["flags"]["skip"] is True


def test_presentable_excludes_pending_and_skipped():
    from app.ingest import presentable
    assert not presentable(_raw())                                   # 无中文标题
    r = _raw(); r["titles"]["zh"] = "x"; r["flags"]["skip"] = True
    assert not presentable(r)
    r["flags"]["skip"] = False
    assert presentable(r)


@pytest.fixture
def isolated_jsonl(tmp_path, monkeypatch):
    """把 POLICIES_DIR 指到临时目录,避免测试改写真实事实层。"""
    d = tmp_path / "policies"; d.mkdir()
    monkeypatch.setattr(E, "POLICIES_DIR", d)
    return d


def test_royal_titles_never_sent_to_model(isolated_jsonl):
    rec = _raw(th="ประกาศ เรื่อง พระราชทานเครื่องราชอิสริยาภรณ์")
    (isolated_jsonl / "documents.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n")
    client = FakeClient()
    res = E.run_enrichment(client=client)
    assert client.calls == [], "王室相关条目绝不能发给模型"
    assert res["skipped_red_line"] == 1


def test_refusal_is_skipped_not_written(isolated_jsonl):
    (isolated_jsonl / "documents.jsonl").write_text(json.dumps(_raw(), ensure_ascii=False) + "\n")
    res = E.run_enrichment(client=FakeClient(stop="refusal"))
    assert res["failed"] == 1 and res["enriched"] == 0
    row = json.loads((isolated_jsonl / "documents.jsonl").read_text().splitlines()[0])
    assert row["titles"]["zh"] == "", "拒答时不能写入任何内容"


def test_request_uses_fallbacks_and_structured_output(isolated_jsonl):
    (isolated_jsonl / "documents.jsonl").write_text(json.dumps(_raw(), ensure_ascii=False) + "\n")
    client = FakeClient()
    E.run_enrichment(client=client)
    kw = client.calls[0]
    assert kw["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in kw["betas"]
    assert kw["output_config"]["format"]["type"] == "json_schema"


def test_no_credentials_skips_cleanly(isolated_jsonl, monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(k, raising=False)
    (isolated_jsonl / "documents.jsonl").write_text(json.dumps(_raw(), ensure_ascii=False) + "\n")
    res = E.run_enrichment()
    assert res["status"] == "no_credentials" and res["pending"] == 1
