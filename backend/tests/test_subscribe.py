# -*- coding: utf-8 -*-
"""订阅:按领域 Atom、周汇总页、订阅配置导出、Telegram 推送(可选)。网络一律 mock。"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import httpx
import pytest

from app import notify as N, seo
from app.config import settings

ATOM = {"a": "http://www.w3.org/2005/Atom"}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("sub")
    (root / "data" / "site").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "subscribe.json").write_text(json.dumps({"telegram_channel_url": "https://t.me/demo"}))
    mp = pytest.MonkeyPatch()
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    mp.setattr(seo, "SUBSCRIBE_CONFIG", root / "config" / "subscribe.json")
    from app.db import session_scope
    with session_scope() as s:
        seo.build(s)
    yield root
    mp.undo()


def test_one_feed_per_domain_with_only_that_domain(site):
    feeds = sorted((site / "feed").glob("*.xml"))
    assert feeds
    sub = json.loads((site / "data" / "site" / "subscribe.json").read_text())
    assert {f["id"] for f in sub["feeds"]} == {p.stem for p in feeds}
    for f in feeds:
        root = ET.fromstring(f.read_text(encoding="utf-8"))
        assert root.find("a:link[@rel='self']", ATOM).get("href") == f"{settings.site_url}/feed/{f.name}"
        zh = next(x["zh"] for x in sub["feeds"] if x["id"] == f.stem)
        cats = {c.get("term") for c in root.iter("{http://www.w3.org/2005/Atom}category")}
        assert cats <= {zh}, f"{f.name} 混入了别的领域:{cats}"


def test_week_pages_list_items_of_that_week_with_official_links(site):
    weeks = sorted(p for p in (site / "p" / "week").glob("*-W*.html"))
    assert weeks and (site / "p" / "week" / "index.html").is_file()
    html = weeks[-1].read_text(encoding="utf-8")
    a, b = seo.week_range(weeks[-1].stem)
    dates = __import__("re").findall(r'<span class="lib-date">(\d{4}-\d{2}-\d{2})</span>', html)
    assert dates and all(a <= d <= b for d in dates)
    assert ".go.th" in html and "泰文原文" in html
    assert html.count('class="coll-item"') == len(dates) and "<p>" in html, "每条都带摘要,不只是标题"


def test_thin_weeks_are_noindex_and_left_out_of_sitemap(site):
    """只有一两条的周是落地页的重复:页面照常生成(周目录还链着它),但 noindex 且不进 sitemap。"""
    sm = (site / "sitemap.xml").read_text(encoding="utf-8")
    weeks = sorted((site / "p" / "week").glob("*-W*.html"))
    assert weeks
    for p in weeks:
        html = p.read_text(encoding="utf-8")
        thin = html.count('class="coll-item"') < seo.MIN_COLLECTION
        assert ('content="noindex, follow"' in html) == thin, p.name
        assert (f"/p/week/{p.name}" in sm) != thin, p.name
    assert f"{settings.site_url}/p/week/index.html" in sm, "周目录本身照常收录"

    # 样例数据里每周都不到 3 条;条目够多的周直接渲染一页来验证
    item = {"uid": "TH-X-1", "title": "标题", "url": "u", "date": "2026-04-20", "domain": "税务", "org": "税务厅",
            "doc_no": "", "summary": "摘要。", "points": [], "official": "https://www.rd.go.th/x.pdf"}
    full = seo.render_week("2026-W17", [dict(item, uid=f"TH-X-{i}") for i in range(seo.MIN_COLLECTION)], None, None)
    assert 'content="noindex' not in full and 'content="index, follow' in full
    assert 'content="noindex, follow"' in seo.render_week("2026-W17", [item], None, None)


def test_subscribe_json_only_accepts_telegram_links(site, tmp_path, monkeypatch):
    sub = json.loads((site / "data" / "site" / "subscribe.json").read_text())
    assert sub["telegram_channel_url"] == "https://t.me/demo"
    assert all(w["href"].startswith("p/week/") and w["n"] >= 5 for w in sub["weeks"]), "首页只列 5 条以上的周"


def test_week_id_is_iso_week():
    assert seo.week_id("2026-04-22") == "2026-W17"
    assert seo.week_range("2026-W17") == ("2026-04-20", "2026-04-26")


# ─────────────────────────── Telegram 推送 ───────────────────────────

@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "STATE", tmp_path / "telegram.json")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHANNEL", "@demo")
    return tmp_path / "telegram.json"


def _client(calls, status=200):
    def h(req):
        calls.append(json.loads(req.content))
        return httpx.Response(status, json={"ok": status == 200, "description": "bad"})
    return httpx.Client(transport=httpx.MockTransport(h))


def test_first_run_marks_existing_without_sending(state):
    calls = []
    res = N.run(client=_client(calls), sleep=lambda s: None)
    assert res["status"] == "bootstrap" and calls == []
    assert len(json.loads(state.read_text())["sent"]) == res["marked"] > 0


def test_new_items_are_sent_once(state):
    rows = N.candidates()
    state.write_text(json.dumps({"sent": [r["uid"] for r in rows[1:]]}))
    calls = []
    res = N.run(client=_client(calls), sleep=lambda s: None)
    assert res == {"status": "ok", "sent": 1, "pending": 0, "errors": []}
    msg = calls[0]
    assert msg["chat_id"] == "@demo" and msg["parse_mode"] == "HTML"
    assert rows[0]["titles"]["zh"] in msg["text"] and ".go.th" in msg["text"] and "以泰文原文为准" in msg["text"]
    calls.clear()
    assert N.run(client=_client(calls), sleep=lambda s: None)["sent"] == 0 and calls == []


def test_error_stops_and_retries_next_run(state):
    rows = N.candidates()
    state.write_text(json.dumps({"sent": [r["uid"] for r in rows[2:]]}))
    calls = []
    res = N.run(client=_client(calls, 403), sleep=lambda s: None)
    assert res["status"] == "error" and len(calls) == 1 and res["sent"] == 0
    assert rows[0]["uid"] not in json.loads(state.read_text())["sent"]


def test_not_configured_is_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "STATE", tmp_path / "telegram.json")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    (tmp_path / "telegram.json").write_text(json.dumps({"sent": []}))
    res = N.run(client=_client([]), sleep=lambda s: None)
    assert res["status"] == "not_configured" and res["pending"] > 0
