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
    # 手写静态页要有 <html lang="zh-CN">:导出繁体版时会改成 zh-Hant,找不到就报错
    head = ('<!DOCTYPE html><html lang="zh-CN"><head><title>政策脉络 · 泰国</title><meta name="description" content="' + "泰国政策中文数据库" * 6
            + '">\n<!-- seo:head x -->\nOLD\n<!-- /seo:head -->\n</head><body><h1>t</h1>')
    (root / "index.html").write_text(head + "<footer>\n<!-- seo:links x -->\n<!-- /seo:links -->\n</footer>",
                                     encoding="utf-8")
    (root / "privacy.html").write_text(head, encoding="utf-8")
    (root / "about.html").write_text(head, encoding="utf-8")
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
    # 同名系列:带上日期区分,日期不能被截掉
    assert seo.page_title("最低贷款利率", "2026-03-02") == "最低贷款利率(2026-03-02) | 泰国政策"
    t = seo.page_title("很" * 90, "2026-03-02")
    assert len(t) <= 56 and t.endswith("…(2026-03-02) | 泰国政策")


def test_clip_stops_at_sentence_end_not_mid_sentence():
    short = "不到上限的原样返回。"
    assert seo.clip(short) == short
    s = "第一句话写得比较长" * 10 + "。" + "第二句话" * 30 + "。"
    assert seo.clip(s) == "第一句话写得比较长" * 10 + "。", "超长时停在最后一个完整的句子"
    s = "很" * 100 + "," + "长" * 100
    assert seo.clip(s) == "很" * 100 + "…", "没有句号就停在逗号处并加省略号"
    assert seo.clip("字" * 400) == "字" * 149 + "…"
    assert all(len(seo.clip(x * 60)) <= 150 for x in ("甲乙丙。", "甲乙,丙丁", "abc def "))


def _lds(html: str) -> list[dict]:
    import re
    return [json.loads(x.replace("<\\/", "</"))
            for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_agency_website_items_do_not_claim_gazette_publication(site):
    """BOI、税务厅、PDPC 官网来源的条目没有公报卷期,日期是官网发布日 ——
    开头那句话是 AI 最常引用的,不能写成本站没核对过的「在皇家公报刊登」。"""
    root, _ = site
    web = (root / "p" / "th-boi-20260115-measures-2026.html").read_text(encoding="utf-8")
    assert "于 2026-01-15 发布《" in web and "<div class=\"k\">发布日</div>" in web and "发文机关发布" in web
    for wrong in ("在泰国皇家公报刊登", "刊登公报日", "刊登皇家公报"):
        assert wrong not in web, wrong
    gaz = (root / "p" / "th-mol-20250701-minwage-14.html").read_text(encoding="utf-8")
    assert "于 2025-07-01 在泰国皇家公报刊登《" in gaz and "刊登公报日" in gaz and "刊登皇家公报" in gaz


def test_upcoming_status_shows_full_date():
    v = {"dates": {"effective_from": "2027-01-01"}, "status_label": "01-01 起施行"}
    assert seo._status(v) == "2027-01-01 起施行"
    assert seo._status({"dates": {"effective_from": "2026-01-01"}, "status_label": "现行有效"}) == "现行有效"


def test_every_page_has_share_image_and_unique_title(site):
    root, _ = site
    import re
    pages = [p for p in (root / "p").rglob("*.html")] + [root / "index.html", root / "about.html"]
    titles = {}
    for p in pages:
        html = p.read_text(encoding="utf-8")
        assert f'<meta property="og:image" content="{SITE}/assets/og.png">' in html, p
        assert '<meta name="twitter:card" content="summary_large_image">' in html, p
        assert "nofollow" not in html.replace("noindex, follow", ""), f"官方原文链接不加 nofollow:{p}"
        if p.parent.name == "p" and p.name.startswith("th-"):
            titles.setdefault(re.search(r"<title>(.*?)</title>", html).group(1), []).append(p.name)
    assert not {t: ps for t, ps in titles.items() if len(ps) > 1}


def test_share_image_is_shipped_at_declared_size():
    import struct
    from app.config import REPO_ROOT
    raw = (REPO_ROOT / seo.OG_IMAGE).read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (1200, 630)


def test_topic_page_leads_with_summaries_then_full_list(site):
    root, _ = site
    html = (root / "p" / "topic" / "tax.html").read_text(encoding="utf-8")
    assert "最新收录" in html and 'class="coll-item"' in html and "泰文原文 ↗" in html
    assert "个人所得税" in html, "开场白说明本领域收什么"
    assert 'href="../../feed/tax.xml"' in html and 'type="application/atom+xml" title="政策脉络 · 泰国 · 税务"' in html
    assert "其他领域" in html and 'href="../guide/royal-gazette.html"' in html
    coll = next(x for x in _lds(html) if x["@type"] == "CollectionPage")
    assert coll["mainEntity"]["numberOfItems"] >= html.count('class="coll-item"') > 0
    assert M.audit_html(f"{SITE}/p/topic/tax.html", html, {})["problems"] == []


def test_topic_page_groups_long_lists_by_year(monkeypatch):
    monkeypatch.setattr(seo, "TOPIC_LATEST", 2)
    items = [{"uid": f"TH-X-{i}", "title": f"标题 {i}", "url": f"{SITE}/p/th-x-{i}.html", "date": d, "org": "税务厅",
              "doc_no": "", "summary": "摘要。", "points": [], "official": "https://www.rd.go.th/x.pdf"}
             for i, d in enumerate(["2026-03-01", "2026-01-05", "2025-12-30", "2025-02-02"])]
    html = seo.render_topic("tax", "税务", "Taxation", items, [("t/excise.html", "消费税")], [("visa", "签证居留", 3)])
    assert html.count('class="coll-item"') == 2 and html.count('class="lib-row"') == 4
    assert 'id="y2026"' in html and 'id="y2025"' in html and html.index('id="y2026"') < html.index('id="y2025"')
    assert 'href="../t/excise.html"' in html and 'href="visa.html"' in html
    assert "更新至 2026-03" in html


def test_gazette_guide_page(site):
    """「泰国皇家公报」指南:Bing 上搜公报本身的词有了对应页面;数字从数据现算,问答与结构化数据一致。"""
    import re
    root, _ = site
    path = root / "p" / "guide" / "royal-gazette.html"
    html = path.read_text(encoding="utf-8")
    url = f"{SITE}/p/guide/royal-gazette.html"
    assert M.audit_html(url, html, {})["problems"] == []
    for kw in ("泰国皇家公报", "泰国政府公报", "ราชกิจจานุเบกษา", "ratchakitcha.soc.go.th", "佛历", "非官方"):
        assert kw in html, kw
    assert "王室" not in html, "指南不展开王室相关内容"
    kho = re.search(r"<li><b>ข 类</b>(.*?)</li>", html)
    assert kho and re.sub(r"<[^>]+>", "", kho.group(1)) == "(ฉบับทะเบียนฐานันดร):本站不收录。", "ข 类只列泰文名称,不释义"
    assert "勋衔" not in html and "卷号每年递增一卷" in html
    faq = next(x for x in _lds(html) if x["@type"] == "FAQPage")
    text = re.sub(r"<[^>]+>", "", html)
    for q in faq["mainEntity"]:
        assert q["name"] in text and q["acceptedAnswer"]["text"] in __import__("html").unescape(text)
    # 编号示例取自真实条目,并链到它的落地页
    ex = re.search(r'例:<a href="\.\./(th-[^"]+\.html)">', html)
    assert ex and (root / "p" / ex.group(1)).is_file()
    assert url in M.parse_sitemap((root / "sitemap.xml").read_text(encoding="utf-8"))
    assert url in (root / "llms.txt").read_text(encoding="utf-8")
    assert 'href="p/guide/royal-gazette.html"' in (root / "index.html").read_text(encoding="utf-8")
    assert 'href="../p/guide/royal-gazette.html"' in (root / "p" / "th-mol-20250701-minwage-14.html").read_text(encoding="utf-8")


def test_thai_citation_matches_series():
    from app import seo_guide as G
    assert G.thai_citation("ง พิเศษ", 143, "52") == "เล่ม 143 ตอนพิเศษ 52 ง"
    assert G.thai_citation("ก", 143, "12") == "เล่ม 143 ตอนที่ 12 ก"
    assert G.series_zh("ง พิเศษ") == "ง 类特刊" and G.series_zh("ก") == "ก 类"


def test_llms_txt_lists_audience_pages_and_effective_dates(site):
    root, _ = site
    llms = (root / "llms.txt").read_text(encoding="utf-8")
    assert "## 按影响对象" in llms and f"{SITE}/p/who/" in llms and "## 指南" in llms
    assert "刊登日不等于生效日" in llms
    full = (root / "llms-full.txt").read_text(encoding="utf-8")
    assert "- 生效日:2025-07-01" in full and "- 影响对象:" in full


def test_index_blocks_injected_idempotently(site):
    root, _ = site
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "OLD" not in html and f'<link rel="canonical" href="{SITE}/">' in html
    assert '"@type": "Dataset"' in html and 'class="seo-nav"' in html and 'href="p/topic/' in html
    with session_scope() as s:
        seo.build(s)
    assert (root / "index.html").read_text(encoding="utf-8") == html


def test_landing_pages_link_back_to_their_collections(site):
    """汇总页(p/t、p/who)列出的每个成员落地页,都要有一条链回该汇总页的内链。"""
    import re
    root, _ = site
    colls = sorted((root / "p" / "t").glob("*.html")) + sorted((root / "p" / "who").glob("*.html"))
    assert colls, "测试数据应至少生成一个汇总页"
    for c in colls:
        rel = f"{c.parent.name}/{c.name}"
        members = set(re.findall(r'class="coll-title">.*?<a href="\.\./([^"/]+\.html)"', c.read_text(encoding="utf-8")))
        assert members
        for m in members:
            page = (root / "p" / m).read_text(encoding="utf-8")
            assert 'class="in-colls"' in page and f'href="{rel}"' in page, (rel, m)


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
        if f.is_dir():                    # 与 StaticFiles(html=True) 一致:目录地址给目录里的 index.html
            f = f / "index.html"
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

    # 改了模板:config 里换一个 indexnow_resubmit.epoch,下一次整站重交一次并记下 epoch
    (tmp_path / "seo.json").write_text(json.dumps({"indexnow_key": key, "geo_questions": ["q"],
                                                   "indexnow_resubmit": {"epoch": "2026-09-29"}}))
    with _mock_site(root, key, calls) as client:
        res = M.run(client, SITE, {}, date(2026, 9, 29), tmp_path / "seo")
    assert len(calls) == 1 and len(calls[0]["urlList"]) == d["metrics"]["sitemap_urls"]
    assert res["state"]["indexnow_epoch"] == "2026-09-29"
    assert "整站重新提交" in M.render_md(res["report"], None)


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


def test_conventional_crawler_paths_redirect_instead_of_404():
    from app.main import app
    with TestClient(app) as c:
        for path, dst in (("/favicon.ico", "/favicon.svg"), ("/feed", "/feed.xml"), ("/feed/", "/feed.xml"),
                          ("/rss.xml", "/feed.xml")):
            r = c.get(path, follow_redirects=False)
            assert r.status_code == 301 and r.headers["location"] == dst, path
        assert c.get("/comments/feed/", follow_redirects=False).status_code == 410


def test_missing_pages_get_html_404_but_api_and_assets_stay_json(tmp_path, monkeypatch):
    """从搜索结果点进已下线页面的人看到带导航的 404 页;状态码仍是 404,接口与资源文件不受影响。"""
    from app import main
    page = tmp_path / "404.html"
    page.write_text("<html><body><h1>页面不存在</h1></body></html>", encoding="utf-8")
    monkeypatch.setattr(main, "NOT_FOUND_PAGE", page)
    with TestClient(main.app) as c:
        for path in ("/no-such-page.html", "/old/section/", "/whatever"):
            r = c.get(path)
            assert r.status_code == 404 and "页面不存在" in r.text, path
            assert r.headers["content-type"].startswith("text/html") and r.headers["x-robots-tag"] == "noindex"
        for path in ("/api/documents/TH-NOPE-1-X", "/js/nope.js", "/data/site/nope.json"):
            r = c.get(path)
            assert r.status_code == 404 and r.headers["content-type"].startswith("application/json"), path
    monkeypatch.setattr(main, "NOT_FOUND_PAGE", tmp_path / "missing.html")
    with TestClient(main.app) as c:        # 还没导出过 404 页:退回默认的 JSON
        assert c.get("/no-such-page.html").json() == {"detail": "Not Found"}


def test_static_files_declare_short_browser_cache():
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/css/main.css").headers["cache-control"] == "public, max-age=3600"
        assert c.get("/js/track.js").headers["cache-control"] == "public, max-age=3600"
        assert c.get("/").headers["cache-control"] == "public, max-age=300"
        assert c.get("/robots.txt").headers["cache-control"] == "public, max-age=300"
        assert c.get("/admin").headers["cache-control"] == "no-store", "后台页不缓存"
        assert "cache-control" not in c.get("/api/health").headers
        assert "cache-control" not in c.get("/js/nope.js").headers, "404 不缓存"


@pytest.mark.parametrize("ua,expect", [
    ("Mozilla/5.0 (compatible; YisouSpider/5.0; +http://www.yisou.com/help/yisouspider.html)", ("YisouSpider", "search")),
    ("Mozilla/5.0 (compatible; PetalBot;+https://webmaster.petalsearch.com/site/petalbot)", ("PetalBot", "search")),
    ("Mozilla/5.0 (compatible; ChatGLM-Spider/1.0; +https://chatglm.cn/)", ("ChatGLM-Spider", "ai")),
])
def test_classify_bot_knows_chinese_engines(ua, expect):
    assert T.classify_bot(ua) == expect


@pytest.mark.parametrize("host,expect", [
    ("yiyan.baidu.com", ("ai", "文心一言")), ("chat.baidu.com", ("ai", "文心一言")),
    ("www.baidu.com", ("search", "百度")), ("www.tongyi.com", ("ai", "通义")), ("chatglm.cn", ("ai", "智谱清言")),
])
def test_channel_of_separates_baidu_ai_from_baidu_search(host, expect):
    assert T.channel_of(host) == expect


def test_page_hits_count_only_successful_page_fetches(clean_hits):
    """「抓取次数」把脚本、数据文件和报错请求都算在内:会渲染的爬虫每页带出十来个子请求,
    冒用爬虫 UA 的扫描器一天能刷出几百次 404。page_hits 只算成功取到的页面。"""
    now = datetime(2026, 11, 13, 10, tzinfo=BKK)
    rows = [("Applebot", "search", "/p/a.html", 200), ("Applebot", "search", "/js/track.js", 200),
            ("Applebot", "search", "/data/site/ads.json", 200), ("Applebot", "search", "/css/main.css", 200),
            ("Applebot", "search", "/zh-hant/", 200), ("Applebot", "search", "/", 304),
            ("cohere-ai", "ai", "/.env", 404), ("cohere-ai", "ai", "/index.php", 404), ("cohere-ai", "ai", "/userfiles", 404),
            ("cohere-ai", "ai", "/p/gone.html", 404), ("GPTBot", "ai", "/p/b.html", 200), ("GPTBot", "ai", "/llms.txt", 200)]
    with session_scope() as s:
        for bot, g, path, st in rows:
            s.add(CrawlHit(ts=now, day=now.date(), bot=bot, group=g, path=path, status=st))
    with session_scope() as s:
        bots = {b["bot"]: b for b in T.report(s, 7, now=now)["crawlers"]["bots"]}
    assert (bots["Applebot"]["hits"], bots["Applebot"]["page_hits"]) == (6, 3)
    assert (bots["cohere-ai"]["hits"], bots["cohere-ai"]["page_hits"]) == (4, 0), "扫描器的 404 不算读到了页面"
    assert (bots["GPTBot"]["hits"], bots["GPTBot"]["page_hits"]) == (2, 1)


def test_monitor_reports_page_fetches_next_to_raw_hits():
    def data(with_pages: bool):
        bots = [{"bot": "Googlebot", "group": "search", "hits": 300, "pages": 160, "page_hits": 150, "last_seen": "2026-11-18"},
                {"bot": "Bingbot", "group": "search", "hits": 200, "pages": 150, "page_hits": 140, "last_seen": "2026-11-18"},
                {"bot": "cohere-ai", "group": "ai", "hits": 245, "pages": 245, "page_hits": 0, "last_seen": "2026-11-13"},
                {"bot": "GPTBot", "group": "ai", "hits": 26, "pages": 20, "page_hits": 18, "last_seen": "2026-11-17"}]
        if not with_pages:
            bots = [{k: v for k, v in b.items() if k != "page_hits"} for b in bots]
        return {"crawlers": {"bots": bots, "errors": []}, "coverage": {}, "channels": {}}
    rep = M.Report(SITE, date(2026, 11, 18))
    d = M.server_stats(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data(True)))), rep, "tok")
    assert rep.metrics["crawl_ai_7d"] == 271, "原有指标口径不变"
    assert rep.metrics["crawl_ai_pages_7d"] == 18 and rep.metrics["crawl_search_pages_7d"] == 290
    rep.sections["server"] = d
    md = M.render_md(rep.to_dict(), None)
    assert "AI 爬虫 271(其中成功取到页面 18 次)" in md and "| cohere-ai | AI | 245 | 0 | 245 |" in md
    # 服务器还是旧版本(没有 page_hits)时不出这两项,表格里写「—」
    rep = M.Report(SITE, date(2026, 11, 18))
    d = M.server_stats(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data(False)))), rep, "tok")
    assert "crawl_ai_pages_7d" not in rep.metrics and rep.metrics["crawl_ai_7d"] == 271
    rep.sections["server"] = d
    md = M.render_md(rep.to_dict(), None)
    assert "成功取到页面" not in md.split("## 关键指标")[0] and "| GPTBot | AI | 26 | — | 20 |" in md


def test_only_recent_crawl_errors_are_reported():
    rep = M.Report(SITE, date(2026, 9, 29))
    data = {"crawlers": {"bots": [{"bot": "Googlebot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"},
                                  {"bot": "Bingbot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"}],
                         "errors": [{"path": "/feed", "status": 404, "n": 3, "bots": "Googlebot", "last_seen": "2026-09-27"},
                                    {"path": "/comments/feed/", "status": 410, "n": 2, "bots": "Googlebot", "last_seen": "2026-09-29"},
                                    {"path": "/js/${esc(ch.href)}", "status": 404, "n": 1, "bots": "GPTBot", "last_seen": "2026-09-29"},
                                    {"path": "/client/.env", "status": 404, "n": 1, "bots": "Googlebot", "last_seen": "2026-09-29"},
                                    {"path": "/api", "status": 404, "n": 1, "bots": "Amazonbot", "last_seen": "2026-09-29"},
                                    {"path": "/actions", "status": 404, "n": 1, "bots": "ClaudeBot", "last_seen": "2026-09-29"},
                                    {"path": "/__vite_rsc_findSourceMapURL", "status": 404, "n": 1, "bots": "cohere-ai", "last_seen": "2026-09-29"},
                                    {"path": "/gone.html", "status": 404, "n": 1, "bots": "Googlebot", "last_seen": "2026-09-29"}]},
            "coverage": {}, "channels": {}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    M.server_stats(client, rep, "tok")
    issue = next(i for i in rep.issues if i["code"] == "crawl_errors")
    assert len(issue["items"]) == 1 and "/gone.html" in issue["items"][0], "已修好的旧 404 与故意的 410 不再提醒"


def test_ads_txt_404_ignored_only_when_ads_off(tmp_path, monkeypatch):
    data = {"crawlers": {"bots": [{"bot": "Googlebot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"},
                                  {"bot": "Bingbot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"}],
                         "errors": [{"path": "/ads.txt", "status": 404, "n": 1, "bots": "Googlebot", "last_seen": "2026-09-29"}]},
            "coverage": {}, "channels": {}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    monkeypatch.setattr(M, "REPO_ROOT", tmp_path)
    rep = M.Report(SITE, date(2026, 9, 29))
    M.server_stats(client, rep, "tok")
    assert not [i for i in rep.issues if i["code"] == "crawl_errors"], "没开广告时 /ads.txt 404 是预期"
    (tmp_path / "ads.txt").write_text("google.com, pub-1, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    rep = M.Report(SITE, date(2026, 9, 29))
    M.server_stats(client, rep, "tok")
    issue = next(i for i in rep.issues if i["code"] == "crawl_errors")
    assert "/ads.txt" in issue["items"][0], "仓库有 ads.txt 而线上 404 要报"


def test_foreign_404_scanner_paths_ignored_real_ones_kept(tmp_path, monkeypatch):
    def err(path, status=404):
        return {"path": path, "status": status, "n": 1, "bots": "Bingbot", "last_seen": "2026-09-29"}
    noise = ["/userfiles", "/cgi-bin/php", "/index.php", "/config.json", "/_debugbar/open",
             "/cgi-bin/php-cgi", "/core/settings.py"]
    real = ["/p/th-gaz-old.html", "/gone.html", "/p/topic/visa", "/css/old.css", "/sitemap_index.xml"]
    data = {"crawlers": {"bots": [{"bot": "Googlebot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"},
                                  {"bot": "Bingbot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"}],
                         "errors": [err(p) for p in noise + real] + [err("/index.php/x", 500)]},
            "coverage": {}, "channels": {}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    for d in ("p", "css"):
        (tmp_path / d).mkdir()
    monkeypatch.setattr(M, "REPO_ROOT", tmp_path)
    rep = M.Report(SITE, date(2026, 9, 29))
    M.server_stats(client, rep, "tok")
    items = next(i for i in rep.issues if i["code"] == "crawl_errors")["items"]
    got = {it.split("(")[0] for it in items}
    assert got == {f"404 {p}" for p in real} | {"500 /index.php/x"}, "站内不可能有的路径不报;旧页面、错误内链、5xx 照报"


def test_script_relative_404_ignored_real_scripts_kept():
    def err(path):
        return {"path": path, "status": 404, "n": 1, "bots": "GPTBot", "last_seen": "2026-09-29"}
    noise = ["/js/'+s+'", "/js/feed.xml", "/js/p/week/index.html"]
    real = ["/js/old.js", "/p/week/index.htm", "/feed.xml"]
    data = {"crawlers": {"bots": [{"bot": "Googlebot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"},
                                  {"bot": "Bingbot", "group": "search", "hits": 1, "pages": 1, "last_seen": "2026-09-29"}],
                         "errors": [err(p) for p in noise + real]},
            "coverage": {}, "channels": {}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    rep = M.Report(SITE, date(2026, 9, 29))
    M.server_stats(client, rep, "tok")
    items = next(i for i in rep.issues if i["code"] == "crawl_errors")["items"]
    assert {it.split("(")[0] for it in items} == {f"404 {p}" for p in real}, "脚本字符串被解析到 /js/ 下的地址不报;缺脚本照报"


def test_short_summary_gets_lede_in_description(session):
    from sqlalchemy import select
    from app import analytics as A
    from app.models import Document
    doc = session.scalars(select(Document).order_by(Document.uid)).first()
    orig = doc.summary_zh
    doc.summary_zh = "短摘要。"
    html = seo.render_page(session, doc, A._today(session), {})
    desc = __import__("re").search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert desc.startswith("短摘要。") and "当前状态" in desc and len(desc) >= 40
    doc.summary_zh = orig
    session.rollback()


def test_skipped_page_paths_reads_skip_flag(tmp_path, monkeypatch):
    (tmp_path / "d.jsonl").write_text(
        '{"uid": "TH-GAZ-1-A", "flags": {"skip": true}}\n'
        '{"uid": "TH-GAZ-2-B", "flags": {"skip": false}}\n'
        'not json\n', encoding="utf-8")
    monkeypatch.setattr(M, "POLICIES_DIR", tmp_path)
    assert M.skipped_page_paths() == {"/p/th-gaz-1-a.html", "/zh-hant/p/th-gaz-1-a.html"}, "繁体版同样不生成"
