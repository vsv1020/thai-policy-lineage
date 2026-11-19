# -*- coding: utf-8 -*-
"""IndexNow 整站重新提交:config/seo.json 的 indexnow_resubmit.epoch 变了,就把已提交记录视为全部过期、
整站重交一次(改模板不改 lastmod,不这样 Bing 不会重抓);百度推送不跟着重推。"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from app import seo_monitor as M
from app.config import settings

SITE = settings.site_url


class _Rep(M.Report):
    def __init__(self):
        super().__init__(SITE, date(2026, 11, 18))


def _client(calls, status=202):
    import httpx

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(status)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_indexnow_resubmits_everything_once_when_epoch_changes():
    sm = {f"{SITE}/p/{i}.html": "2026-01-01" for i in range(5)}
    live = set(sm)
    state = {"indexnow": {u: "2026-01-01" for u in sm}, "baidu": {u: "2026-01-01" for u in sm}}
    calls: list = []
    with _client(calls) as c:
        assert M.indexnow(c, _Rep(), "k" * 32, sm, live, state)["submitted"] == 0, "没有 epoch:照旧只交变化的"
        r = M.indexnow(c, _Rep(), "k" * 32, sm, live, state, epoch="2026-11-18")
        assert r == {"submitted": 5, "status": 202, "resubmit": "2026-11-18"}
        assert sorted(calls[-1]["urlList"]) == sorted(sm)
        assert state["indexnow_epoch"] == "2026-11-18" and len(state["indexnow"]) == 5
        n = len(calls)
        assert M.indexnow(c, _Rep(), "k" * 32, sm, live, state, epoch="2026-11-18")["submitted"] == 0
        assert len(calls) == n, "同一个 epoch 只重交一次"
    assert state["baidu"] == {u: "2026-01-01" for u in sm}, "百度推送不跟着全量重推"


def test_indexnow_resubmit_retries_after_failure_and_respects_limit(monkeypatch):
    sm = {f"{SITE}/p/{i}.html": "2026-01-01" for i in range(5)}
    state = {"indexnow": {u: "2026-01-01" for u in sm}}
    calls: list = []
    with _client(calls, status=500) as c:
        assert M.indexnow(c, _Rep(), "k" * 32, sm, set(sm), state, epoch="e1")["submitted"] == 0
    assert "indexnow_epoch" not in state and len(state["indexnow"]) == 5, "失败不记 epoch,明天重试"
    monkeypatch.setattr(M, "INDEXNOW_MAX", 3)
    with _client(calls) as c:
        assert M.indexnow(c, _Rep(), "k" * 32, sm, set(sm), state, epoch="e1")["submitted"] == 3
        assert len(state["indexnow"]) == 3, "超出单次上限的旧记录作废"
        assert M.indexnow(c, _Rep(), "k" * 32, sm, set(sm), state, epoch="e1")["submitted"] == 2, "第二天补交其余"


def test_seo_config_has_resubmit_epoch():
    cfg = json.loads((Path(__file__).resolve().parents[2] / "config" / "seo.json").read_text(encoding="utf-8"))
    rs = cfg["indexnow_resubmit"]
    assert rs["_comment"] and re.fullmatch(r"\S+", rs["epoch"])


