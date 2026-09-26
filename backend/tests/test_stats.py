# -*- coding: utf-8 -*-
"""站点统计:上报过滤、隐私承诺、聚合口径、后台鉴权。

隐私相关的断言对应 privacy.html 里写给读者的承诺 —— 这些测试挂了,
要么改回代码,要么同步改隐私政策,不能只改一边。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import stats as S
from app.config import BKK, settings
from app.db import session_scope
from app.models import PageHit

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
NOW = datetime(2026, 9, 20, 14, 30, tzinfo=BKK)


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    with session_scope() as s:
        s.execute(delete(PageHit))
    yield
    with session_scope() as s:
        s.execute(delete(PageHit))


def hit(payload: dict, ua: str = UA, ip: str = "203.0.113.7", at: datetime = NOW, **headers):
    h = {"user-agent": ua, **headers}
    return S.parse_hit(json.dumps(payload).encode(), h, ip, at)


def add(*hits):
    with session_scope() as s:
        for h in hits:
            assert h is not None
            s.add(h)


# ─────────────── 上报过滤 ───────────────

def test_pageview_is_recorded_without_ip(client):
    r = client.post("/api/t", content=json.dumps({"k": "pv", "p": "/", "r": "https://www.google.com/search"}),
                    headers={"user-agent": UA, "content-type": "text/plain"})
    assert r.status_code == 204
    with session_scope() as s:
        rows = s.scalars(select(PageHit)).all()
    assert len(rows) == 1
    h = rows[0]
    assert h.kind == "pv" and h.path == "/" and h.ref_host == "www.google.com" and h.device == "mobile"
    # 不存 IP:任何一列都不能出现客户端地址
    assert "testclient" not in json.dumps({c.name: str(getattr(h, c.name)) for c in PageHit.__table__.columns})
    assert len(h.visitor) == 16


@pytest.mark.parametrize("payload,ua,headers", [
    ({"k": "pv", "p": "/"}, "Googlebot/2.1 (+http://www.google.com/bot.html)", {}),
    ({"k": "pv", "p": "/"}, "curl/8.0", {}),
    ({"k": "pv", "p": "/"}, "", {}),
    ({"k": "pv", "p": "/"}, UA, {"dnt": "1"}),
    ({"k": "pv", "p": "/"}, UA, {"sec-gpc": "1"}),
    ({"k": "event", "n": "drop_table", "p": "/"}, UA, {}),      # 未登记的事件名
    ({"k": "pv", "p": "https://evil.example/"}, UA, {}),        # 路径必须是站内路径
])
def test_rejected_hits(payload, ua, headers):
    assert hit(payload, ua=ua, **headers) is None


def test_garbage_and_oversize_bodies_are_dropped():
    h = {"user-agent": UA}
    assert S.parse_hit(b"not json", h, "1.1.1.1", NOW) is None
    assert S.parse_hit(b"[1,2]", h, "1.1.1.1", NOW) is None
    big = json.dumps({"k": "pv", "p": "/", "l": "x" * 5000}).encode()
    assert S.parse_hit(big, h, "1.1.1.1", NOW) is None


@pytest.mark.parametrize("raw,want", [("zh-CN", "zh-cn"), ("en-US@posix", "en-us"), ("th", "th"),
                                      ("zh_Hant", "zh-hant"), ("<script>", ""), ("", "")])
def test_lang_normalised(raw, want):
    assert S.lang_of(raw) == want


def test_internal_referrer_is_not_a_source():
    h = hit({"k": "pv", "p": "/", "r": "https://mysite.example/p/x.html"},
            origin="https://mysite.example")
    assert h.ref_host == ""


def test_visitor_hash_rotates_daily():
    a = hit({"k": "pv", "p": "/"}, at=NOW)
    b = hit({"k": "pv", "p": "/"}, at=NOW + timedelta(hours=1))
    c = hit({"k": "pv", "p": "/"}, at=NOW + timedelta(days=1))
    assert a.visitor == b.visitor, "同一天同一人应算一个访客"
    assert a.visitor != c.visitor, "跨天必须不可关联"


def test_country_header_only_trusted_behind_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", False)
    assert hit({"k": "pv", "p": "/"}, **{"cf-ipcountry": "TH"}).country == ""
    monkeypatch.setattr(settings, "trust_proxy", True)
    assert hit({"k": "pv", "p": "/"}, **{"cf-ipcountry": "TH"}).country == "TH"


def test_stats_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings, "stats_enabled", False)
    client.post("/api/t", content='{"k":"pv","p":"/"}', headers={"user-agent": UA})
    with session_scope() as s:
        assert s.scalars(select(PageHit)).first() is None


# ─────────────── 聚合口径 ───────────────

def test_report_numbers():
    add(
        # 访客 A:当天 3 次浏览(首页、详情、落地页)
        hit({"k": "pv", "p": "/", "r": "https://www.google.com/"}),
        hit({"k": "pv", "p": "/#detail/TH-RD-2566-POR-161"}),
        hit({"k": "pv", "p": "/p/th-rd-2566-por-161.html"}),
        # 访客 B:电脑,1 次浏览,带 UTM
        hit({"k": "pv", "p": "/", "us": "Facebook", "um": "social", "uc": "launch"}, ua=UA_DESKTOP, ip="198.51.100.2"),
        # 访客 A 前一天也来过 → 按天去重后是 2 个访客日
        hit({"k": "pv", "p": "/"}, at=NOW - timedelta(days=1)),
        # 事件
        hit({"k": "event", "n": "search", "p": "/", "l": "DTV", "v": 3}),
        hit({"k": "event", "n": "search", "p": "/", "l": "dtv", "v": 3}),
        hit({"k": "event", "n": "search", "p": "/", "l": "退休签", "v": 0}),
        hit({"k": "event", "n": "outbound", "p": "/", "l": "ratchakitcha.soc.go.th"}),
        hit({"k": "event", "n": "ad_view", "p": "/", "l": "home_sidebar|某律所"}),
        hit({"k": "event", "n": "ad_view", "p": "/", "l": "home_sidebar|某律所"}),
        hit({"k": "event", "n": "ad_click", "p": "/", "l": "home_sidebar|某律所"}),
        hit({"k": "event", "n": "tip_open", "p": "/", "l": "header"}),
        hit({"k": "event", "n": "tip_amount", "p": "/", "l": "100"}),
        # 上一个统计周期的数据,只影响环比
        hit({"k": "pv", "p": "/"}, at=NOW - timedelta(days=10)),
    )
    with session_scope() as s:
        r = S.report(s, days=7, now=NOW)

    sm = r["summary"]
    assert sm["pv"]["value"] == 5
    assert sm["uv"]["value"] == 3                  # 今天 A、B + 昨天 A
    assert sm["detail_views"]["value"] == 2
    assert sm["pv"]["change_pct"] == 400.0         # 上期 1 → 本期 5
    assert sm["searches"]["value"] == 3
    assert len(r["series"]) == 7 and r["series"][-1] == {"day": "2026-09-20", "pv": 4, "uv": 2}
    assert r["hours"][14] == 5                     # 今天 4 次 + 昨天同一时段 1 次

    pol = r["policies"][0]
    assert pol["uid"] == "TH-RD-2566-POR-161" and pol["n"] == 2 and pol["landing"] == 1
    assert pol["title"], "应从 documents 表补上中文标题"

    assert r["referrers"] == [{"key": "www.google.com", "n": 1, "uv": 1}]
    assert r["campaigns"][0]["source"] == "facebook"

    dtv = next(q for q in r["searches"] if q["q"] == "dtv")
    assert dtv["n"] == 2 and dtv["zero"] == 0                      # 大小写合并
    assert [q["q"] for q in r["zero_result_searches"]] == ["退休签"]

    assert r["outbound"][0]["official"] is True
    assert r["ads"] == [{"slot": "home_sidebar", "sponsor": "某律所", "views": 2, "clicks": 1, "ctr": 50.0}]
    assert r["tips"]["opens"] == 1 and r["tips"]["amounts"][0]["key"] == "100"
    assert {d["key"] for d in r["devices"]} == {"mobile", "desktop"}
    assert r["realtime_visitors_30m"] == 2


def test_purge_respects_retention():
    add(hit({"k": "pv", "p": "/"}, at=NOW - timedelta(days=500)), hit({"k": "pv", "p": "/"}, at=NOW))
    with session_scope() as s:
        assert S.purge(s, keep_days=400, today=NOW.date()) == 1
    with session_scope() as s:
        assert len(s.scalars(select(PageHit)).all()) == 1


def test_text_report_renders():
    add(hit({"k": "pv", "p": "/#detail/TH-RD-2566-POR-161"}))
    with session_scope() as s:
        out = S.text_report(S.report(s, days=7, now=NOW))
    assert "浏览量 1" in out and "TH-RD-2566-POR-161" in out


# ─────────────── 后台鉴权 ───────────────

def test_admin_disabled_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.get("/api/admin/stats").status_code == 404
    assert client.get("/api/admin/stats", headers={"authorization": "Bearer "}).status_code == 404


def test_admin_requires_correct_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "s3cret-token-for-tests")
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/stats", headers={"authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/api/admin/stats?days=7", headers={"authorization": "Bearer s3cret-token-for-tests"})
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex" and r.headers["cache-control"] == "no-store"
    assert set(r.json()) >= {"summary", "series", "policies", "searches", "ads", "tips"}


def test_admin_page_is_served_but_not_indexed(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "统计后台" in r.text
    assert "noindex" in r.headers["x-robots-tag"]
