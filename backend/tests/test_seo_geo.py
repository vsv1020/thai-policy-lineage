# -*- coding: utf-8 -*-
"""SEO / GEO:专题页、robots、llms.txt、feed、结构化数据;爬虫识别与来源渠道;每日监控。"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import seo, seo_monitor as M, seo_track as T
from app.config import BKK, settings
from app.db import session_scope
from app.models import CrawlHit, PageHit

SITE = settings.site_url


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("geo")
    (root / "data" / "site").mkdir(parents=True)
    head = ('<head><title>政策脉络 · 泰国</title><meta name="description" content="' + "泰国政策中文数据库" * 6
            + '">\n<!-- seo:head x -->\nOLD\n<!-- /seo:head -->\n</head><body><h1>t</h1>')
    (root / "index.html").write_text(head + "<footer>\n<!-- seo:links x -->\n<!-- /seo:links -->\n</footer>",
                                     encoding="utf-8")
    (root / "privacy.html").write_text(head, encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    with session_scope() as s:
        stats = seo.build(s)
    yield root, stats
    mp.undo()


# ─────────────────────────── 站内产物 ───────────────────────────

def test_topic_pages_and_sitemap(site):
    root, stats = site
    topics = sorted(p.stem for p in (root / "p" / "topic").glob("*.html"))
    assert topics and stats["topics"] == len(topics)
    sm = M.parse_sitemap((root / "sitemap.xml").read_text(encoding="utf-8"))
    for t in topics:
        assert f"{SITE}/p/topic/{t}.html" in sm
    html = (root / "p" / "topic" / f"{topics[0]}.html").read_text(encoding="utf-8")
    assert '"@type": "CollectionPage"' in html and 'href="../../css/main.css"' in html
    assert M.audit_html(f"{SITE}/p/topic/{topics[0]}.html", html, {})["problems"] == []


def test_robots_welcomes_ai_crawlers_but_hides_api(site):
    root, _ = site
    txt = (root / "robots.txt").read_text(encoding="utf-8")
    for bot in ("GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}" in txt
    assert txt.count("Disallow: /api/") == 2, "具名的 AI 组也要继承后台与 API 的屏蔽"
    assert "\nDisallow: /\n" not in txt
    assert f"Sitemap: {SITE}/sitemap.xml" in txt


def test_llms_txt_and_feed(site):
    root, _ = site
    llms = (root / "llms.txt").read_text(encoding="utf-8")
    full = (root / "llms-full.txt").read_text(encoding="utf-8")
    assert llms.startswith("# 政策脉络") and "## 最新政策" in llms and f"{SITE}/p/" in llms
    assert "泰文原文(官方):https://" in full and ".go.th" in full
    feed = ET.fromstring((root / "feed.xml").read_text(encoding="utf-8"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = feed.findall("a:entry", ns)
    assert entries and entries[0].find("a:link", ns).get("href").startswith(f"{SITE}/p/")


def test_landing_page_geo_blocks(site):
    root, _ = site
    html = (root / "p" / "th-mol-20250701-minwage-14.html").read_text(encoding="utf-8")
    assert '<p class="lede">' in html and "当前状态" in html
    assert '<dl class="facts">' in html and "引用本页" in html
    assert '"@type": "BreadcrumbList"' in html
    ld = [json.loads(x.replace("<\\/", "</")) for x in
          __import__("re").findall(r'<script type="application/ld\+json">(.*?)</script>', html, 16)]
    leg = next(x for x in ld if x["@type"] == "Legislation")
    assert leg["translationOfWork"]["inLanguage"] == "th"
    assert M.audit_html(f"{SITE}/p/th-mol-20250701-minwage-14.html", html, {})["problems"] == []


def test_long_titles_are_shortened():
    t = seo.page_title("很" * 90)
    assert len(t) <= 56 and t.endswith(" | 泰国政策") and "…" in t
    assert seo.page_title("短标题") == "短标题 | 泰国政策"


def test_index_blocks_injected_idempotently(site):
    root, _ = site
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "OLD" not in html and f'<link rel="canonical" href="{SITE}/">' in html
    assert '"@type": "Dataset"' in html and 'class="seo-nav"' in html and 'href="p/topic/' in html
    with session_scope() as s:
        seo.build(s)
    assert (root / "index.html").read_text(encoding="utf-8") == html


def test_jsonld_cannot_break_out_of_script():
    assert "</script>" not in seo._ld({"x": "</script><b>"})[:-9]


# ─────────────────────────── 爬虫与来源 ───────────────────────────

@pytest.mark.parametrize("ua,expect", [
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", ("Googlebot", "search")),
    ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", ("Bingbot", "search")),
    ("Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)", ("Baiduspider", "search")),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0", ("OAI-SearchBot", "ai")),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)", ("GPTBot", "ai")),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", ("ClaudeBot", "ai")),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0)", ("PerplexityBot", "ai")),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36", None),
])
def test_classify_bot(ua, expect):
    assert T.classify_bot(ua) == expect


@pytest.mark.parametrize("host,utm,expect", [
    ("www.google.co.th", "", ("search", "Google")),
    ("m.baidu.com", "", ("search", "百度")),
    ("chatgpt.com", "", ("ai", "ChatGPT")),
    ("", "chatgpt.com", ("ai", "ChatGPT")),
    ("www.perplexity.ai", "", ("ai", "Perplexity")),
    ("gemini.google.com", "", ("ai", "Gemini")),
    ("l.facebook.com", "", ("social", "Facebook")),
    ("example.org", "", ("referral", "example.org")),
    ("", "", ("direct", "")),
])
def test_channel_of(host, utm, expect):
    assert T.channel_of(host, utm) == expect


@pytest.fixture()
def clean_hits():
    with session_scope() as s:
        s.execute(delete(CrawlHit)); s.execute(delete(PageHit))
    yield
    with session_scope() as s:
        s.execute(delete(CrawlHit)); s.execute(delete(PageHit))


def test_middleware_records_crawlers_only(clean_hits, monkeypatch):
    from app.main import app
    with TestClient(app) as c:
        c.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 (compatible; GPTBot/1.2)"})
        c.get("/p/does-not-exist.html", headers={"user-agent": "Googlebot/2.1"})
        c.get("/robots.txt", headers={"user-agent": "Mozilla/5.0 Chrome/128"})
        c.get("/api/meta", headers={"user-agent": "Googlebot/2.1"})
    with session_scope() as s:
        rows = sorted((h.bot, h.group, h.path, h.status) for h in s.scalars(select(CrawlHit)))
    assert rows == [("GPTBot", "ai", "/robots.txt", 200), ("Googlebot", "search", "/p/does-not-exist.html", 404)]


def test_admin_seo_report(clean_hits, monkeypatch):
    from app.main import app
    now = datetime(2026, 9, 20, 10, tzinfo=BKK)
    with session_scope() as s:
        for bot, g, path, st in [("Googlebot", "search", "/p/a.html", 200), ("Googlebot", "search", "/p/a.html", 200),
                                 ("GPTBot", "ai", "/p/b.html", 200), ("Bingbot", "search", "/p/gone.html", 404)]:
            s.add(CrawlHit(ts=now, day=now.date(), bot=bot, group=g, path=path, status=st))
        for ref, utm in [("www.google.com", ""), ("chatgpt.com", ""), ("", "perplexity"), ("", "")]:
            s.add(PageHit(ts=now, day=now.date(), hour=10, kind="pv", path="/p/a.html", visitor="v",
                          ref_host=ref, utm_source=utm))
    with session_scope() as s:
        r = T.report(s, 7, now=now)
    bots = {b["bot"]: b for b in r["crawlers"]["bots"]}
    assert bots["Googlebot"]["hits"] == 2 and bots["GPTBot"]["group"] == "ai"
    assert r["crawlers"]["errors"][0]["path"] == "/p/gone.html"
    assert r["channels"] == {"search": 1, "ai": 2, "direct": 1}
    assert {x["key"] for x in r["ai_sources"]} == {"ChatGPT", "Perplexity"}

    monkeypatch.setattr(settings, "admin_token", "")
    with TestClient(app) as c:
        assert c.get("/api/admin/seo").status_code == 404
    monkeypatch.setattr(settings, "admin_token", "tok-for-tests")
    with TestClient(app) as c:
        assert c.get("/api/admin/seo").status_code == 401
        ok = c.get("/api/admin/seo", headers={"Authorization": "Bearer tok-for-tests"})
        assert ok.status_code == 200 and "coverage" in ok.json()


def test_indexnow_key_file_served():
    from app import main
    if not main.INDEXNOW_KEY_FILE:
        pytest.skip("config/seo.json 没有 indexnow_key")
    with TestClient(main.app) as c:
        r = c.get("/" + main.INDEXNOW_KEY_FILE)
        assert r.status_code == 200 and r.text == main.INDEXNOW_KEY_FILE[:-4]
        for f in ("llms.txt", "feed.xml", "favicon.svg"):
            assert c.get("/" + f).status_code in (200, 404)   # 仓库里导出过就 200;白名单不会 403


# ─────────────────────────── 每日监控 ───────────────────────────

def test_audit_html_flags_problems():
    bad = ('<html><head><title></title><meta name="robots" content="noindex"></head>'
           '<body><h1>a</h1><h1>b</h1></body></html>')
    probs = M.audit_html(f"{SITE}/p/x.html", bad, {})["problems"]
    for frag in ("缺 <title>", "缺 meta description", "缺 canonical", "noindex", "H1 数量为 2",
                 "缺结构化数据", "缺官方原文"):
        assert any(frag in p for p in probs), frag


def test_changed_urls_only_new_or_modified():
    sm = {"u1": "2026-01-01", "u2": "2026-02-01", "u3": None}
    assert M.changed_urls(sm, {}) == ["u2", "u1", "u3"]
    assert M.changed_urls(sm, {"u1": "2026-01-01", "u2": "2026-01-15", "u3": ""}) == ["u2"]


def _mock_site(root, key, calls):
    """把导出的站点目录当成线上站点;记录对搜索引擎提交接口的调用。"""
    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if req.url.host == "api.indexnow.org":
            calls.append(json.loads(req.content))
            return httpx.Response(202)
        if u.startswith("http://") or req.url.host != M._host(SITE):
            return httpx.Response(301, headers={"location": SITE + "/"})
        path = req.url.path
        if path == f"/{key}.txt":
            return httpx.Response(200, text=key)
        if path == "/api/admin/seo":
            return httpx.Response(401)
        f = root / (path.lstrip("/") or "index.html")
        if f.is_file():
            return httpx.Response(200, text=f.read_text(encoding="utf-8"))
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_monitor_end_to_end(site, tmp_path, monkeypatch):
    root, _ = site
    key = "0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(seo, "SEO_CONFIG", tmp_path / "seo.json")
    (tmp_path / "seo.json").write_text(json.dumps({"indexnow_key": key, "geo_questions": ["q"]}))
    monkeypatch.setattr(M, "REPO_ROOT", root)
    calls: list = []
    today = date(2026, 9, 27)
    with _mock_site(root, key, calls) as client:
        res = M.run(client, SITE, {"ADMIN_TOKEN": "x"}, today, tmp_path / "seo", n_pages=100)
    d = res["report"]
    codes = {i["code"] for i in d["issues"]}
    assert not [i for i in d["issues"] if i["level"] == "error"], d["issues"]
    assert "admin_api" in codes and "deploy_lag" not in codes
    assert calls and len(calls[0]["urlList"]) == d["metrics"]["sitemap_urls"]
    assert calls[0]["keyLocation"] == f"{SITE}/{key}.txt"
    assert any("Search Console" in x for x in d["disabled"])

    M.write_outputs(d, tmp_path / "seo", res["state"])
    md = (tmp_path / "seo" / "latest.md").read_text(encoding="utf-8")
    assert "## 待处理问题" in md and "## 关键指标" in md

    # 第二天:没有变化就不重复提交
    calls.clear()
    state = json.loads((tmp_path / "seo" / "state.json").read_text(encoding="utf-8"))
    assert len(state["indexnow"]) == d["metrics"]["sitemap_urls"]
    with _mock_site(root, key, calls) as client:
        M.run(client, SITE, {}, date(2026, 9, 28), tmp_path / "seo")
    assert calls == []


def test_monitor_site_down_is_error(tmp_path, monkeypatch):
    monkeypatch.setattr(seo, "SEO_CONFIG", tmp_path / "none.json")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(502)))
    d = M.run(client, SITE, {}, date(2026, 9, 27), tmp_path)["report"]
    assert d["issues"][0]["code"] == "site_down" and d["issues"][0]["level"] == "error"


def test_geo_probe_stops_on_account_error_and_explains():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(403, json={"error": {"message": "insufficient quota"}})
    rep = M.Report(SITE, date(2026, 9, 27))
    out = M.geo_probe(httpx.Client(transport=httpx.MockTransport(handler)), rep, "k", ["q1", "q2", "q3"])
    assert len(calls) == 1, "账号问题只请求一次"
    assert out["results"][0]["error"].startswith("HTTP 403 insufficient quota")
    issue = next(i for i in rep.issues if i["code"] == "geo_api")
    assert "insufficient quota" in issue["msg"] and "额度" in issue["fix"]
    assert "geo_asked" in rep.metrics and rep.metrics["geo_asked"] == 0
    md = M.render_md({**rep.to_dict(), "sections": {"geo": out}}, None)
    assert "⚠️ q1" in md and "❌" not in md.split("## GEO")[1]


def test_geo_probe_uses_agent_api_and_reads_nested_citations():
    """Agent API:来源在 output[] 里 type=search_results 的 results[].url,没有顶层 citations。"""
    body = {"status": "completed", "output": [
        {"type": "search_results", "results": [{"id": 1, "url": "https://www.thaipolicy.com/p/x.html"},
                                                {"id": 2, "url": "https://other.example/a"}]},
        {"type": "message", "content": [{"type": "output_text", "text": "答案 [1][2]"}]}]}
    seen = []

    def handler(req):
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(200, json=body)
    rep = M.Report(SITE, date(2026, 9, 27))
    out = M.geo_probe(httpx.Client(transport=httpx.MockTransport(handler)), rep, "k", ["q1"])
    assert seen[0][0] == "https://api.perplexity.ai/v1/agent"
    assert seen[0][1] == {"model": "perplexity/sonar", "input": "q1", "tools": [{"type": "web_search"}]}
    assert rep.metrics == {"geo_asked": 1, "geo_cited": 1}
    assert out["top_cited_domains"] == [("other.example", 1)]


def test_geo_probe_failed_status_is_error_not_uncited():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"status": "failed", "error": {"message": "boom"}})))
    rep = M.Report(SITE, date(2026, 9, 27))
    out = M.geo_probe(client, rep, "k", ["q1"])
    assert "failed" in out["results"][0]["error"] and rep.metrics["geo_asked"] == 0
