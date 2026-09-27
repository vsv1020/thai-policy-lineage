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
            "affected_parties": [], "relations": [],
            "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/documents/FIXTURE.pdf"}],
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
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    (isolated_jsonl / "documents.jsonl").write_text(json.dumps(_raw(), ensure_ascii=False) + "\n")
    res = E.run_enrichment()
    assert res["status"] == "no_credentials" and res["pending"] == 1


# ─────────────── DeepSeek ───────────────

import httpx  # noqa: E402

from app.config import settings  # noqa: E402


def deepseek(payload=GOOD, finish="stop", status=200, content=None):
    """DeepSeekClient + 假 HTTP 层;requests 记录每次请求体。"""
    requests = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append({"url": str(req.url), "auth": req.headers.get("authorization"),
                         "body": json.loads(req.content)})
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "x"}})
        text = content if content is not None else json.dumps(payload, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": text},
                                                      "finish_reason": finish}]})
    c = E.DeepSeekClient("sk-test", "https://api.deepseek.com", "deepseek-chat",
                         transport=httpx.MockTransport(handler))
    return c, requests


def _write(d, *recs):
    (d / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))


def test_provider_auto_selection(monkeypatch):
    monkeypatch.setattr(settings, "enrich_provider", "")
    monkeypatch.setattr(settings, "enrich_model_override", "")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert E.provider() == "anthropic" and E.model_name() == "claude-opus-5"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    assert E.provider() == "deepseek" and E.model_name() == "deepseek-chat"
    monkeypatch.setattr(settings, "enrich_provider", "anthropic")      # 显式配置优先
    assert E.provider() == "anthropic"
    monkeypatch.setattr(settings, "enrich_model_override", "deepseek-reasoner")
    assert E.model_name("deepseek") == "deepseek-reasoner"


def test_deepseek_request_shape_and_result(isolated_jsonl):
    _write(isolated_jsonl, _raw())
    client, reqs = deepseek()
    res = E.run_enrichment(client=client)
    assert res["enriched"] == 1 and res["provider"] == "deepseek" and res["model"] == "deepseek-chat"
    r = reqs[0]
    assert r["url"] == "https://api.deepseek.com/chat/completions"
    assert r["auth"] == "Bearer sk-test"
    assert r["body"]["response_format"] == {"type": "json_object"}
    system = r["body"]["messages"][0]["content"]
    assert "json" in system and '"enum"' in system, "JSON 模式要求提示词含 json 与格式说明"
    row = json.loads((isolated_jsonl / "documents.jsonl").read_text().splitlines()[0])
    assert row["titles"]["zh"] == GOOD["title_zh"]
    assert row["provenance"]["enriched_by"] == "deepseek-chat"
    assert row["provenance"]["verified"] is False


def test_deepseek_royal_titles_never_sent(isolated_jsonl):
    _write(isolated_jsonl, _raw(th="ประกาศ เรื่อง พระราชทานเครื่องราชอิสริยาภรณ์"))
    client, reqs = deepseek()
    assert E.run_enrichment(client=client)["skipped_red_line"] == 1
    assert reqs == []


@pytest.mark.parametrize("kw", [
    {"finish": "length"},                                     # 截断
    {"finish": "content_filter", "content": ""},              # 内容过滤
    {"content": ""},                                          # 空内容
    {"content": "这不是 JSON"},
    {"payload": {k: v for k, v in GOOD.items() if k != "domain_ids"}},     # 缺字段
    {"payload": dict(GOOD, legal_form_id="NOT_REAL")},                      # 必选枚举越界
    {"payload": dict(GOOD, relevant="yes")},                                # 类型错
    {"payload": dict(GOOD, title_zh="  ")},                                 # 空标题
])
def test_deepseek_bad_output_is_dropped_not_written(isolated_jsonl, kw):
    _write(isolated_jsonl, _raw())
    client, _ = deepseek(**kw)
    res = E.run_enrichment(client=client)
    assert res["failed"] == 1 and res["enriched"] == 0
    row = json.loads((isolated_jsonl / "documents.jsonl").read_text().splitlines()[0])
    assert row["titles"]["zh"] == "", "不合格输出不能写入任何内容"


def test_deepseek_http_error_fails_one_item_not_the_run(isolated_jsonl, monkeypatch):
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    _write(isolated_jsonl, _raw(), _raw(uid="TH-GAZ-2"))
    client, reqs = deepseek(status=503)
    res = E.run_enrichment(client=client)
    assert res["failed"] == 2 and res["status"] == "failed"
    assert len(reqs) == 6, "每条 503 应重试到 3 次"


def test_deepseek_irrelevant_needs_only_title(isolated_jsonl):
    _write(isolated_jsonl, _raw())
    client, _ = deepseek(payload={"relevant": False, "title_zh": "人事任免", "summary_zh": ""})
    res = E.run_enrichment(client=client)
    assert res["skipped_irrelevant"] == 1
