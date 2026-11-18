# -*- coding: utf-8 -*-
"""每日监控与爬虫统计在繁体版上线后的口径:GSC 收录按字形分开、检查名额固定分配、
抽查简繁各半、百度不推繁体、整站重交等部署跟上、繁体首页与 hreflang 体检、可疑字形进日报。"""
from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import delete

from app import seo, seo_monitor as M, seo_track as T
from app.config import BKK, settings
from app.db import session_scope
from app.models import CrawlHit

SITE = settings.site_url
HANT = f"{SITE}/zh-hant"


def _rep():
    return M.Report(SITE, date(2026, 11, 19))


def test_is_hant_url():
    assert M.is_hant_url(f"{HANT}/p/a.html") and M.is_hant_url(f"{HANT}/")
    assert not M.is_hant_url(f"{SITE}/p/a.html") and not M.is_hant_url(f"{SITE}/zh-hantx/a.html")


# ─────────────────────────── GSC ───────────────────────────

def _gsc_client(calls):
    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "searchAnalytics" in u:
            return httpx.Response(200, json={"rows": []})
        if u.endswith("/sitemaps"):
            return httpx.Response(200, json={"sitemap": []})
        if "urlInspection" in u:
            body = json.loads(req.content)
            url = body["inspectionUrl"]
            calls.append((url, body["languageCode"]))
            if M.is_hant_url(url):      # 繁体页:Google 把它归并到对应的简体页
                return httpx.Response(200, json={"inspectionResult": {"indexStatusResult": {
                    "verdict": "NEUTRAL", "coverageState": "Duplicate, Google chose different canonical than user",
                    "googleCanonical": url.replace("/zh-hant/", "/", 1)}}})
            return httpx.Response(200, json={"inspectionResult": {"indexStatusResult": {
                "verdict": "PASS", "coverageState": "Submitted and indexed", "googleCanonical": url}}})
        return httpx.Response(200, json={})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gsc_index_metrics_split_by_script(monkeypatch):
    monkeypatch.setattr(M, "gsc_token", lambda raw: "tok")
    urls = [f"{SITE}/p/{i}.html" for i in range(80)] + [f"{HANT}/p/{i}.html" for i in range(80)]
    calls: list = []
    rep, state = _rep(), {}
    with _gsc_client(calls) as c:
        out = M.gsc(c, rep, {"GSC_SERVICE_ACCOUNT_JSON": "x"}, urls, f"{SITE}/sitemap.xml", state, False, 60)
    hant_calls = [u for u, _ in calls if M.is_hant_url(u)]
    assert len(calls) == 60 and len(hant_calls) == round(60 * M.HANT_INSPECT_SHARE), "名额按固定比例分配"
    assert all(lang == ("zh-TW" if M.is_hant_url(u) else "zh-CN") for u, lang in calls)
    m = rep.metrics
    assert m["gsc_checked"] == 45 and m["gsc_indexed"] == 45, "主指标只算简体"
    assert m["gsc_hant_checked"] == 15 and m["gsc_hant_indexed"] == 0
    assert out["index"]["total"] == 80 and out["index_hant"]["total"] == 80
    codes = {i["code"]: i for i in rep.issues}
    assert "gsc_not_indexed" not in codes and "gsc_canonical" not in codes, "繁体页不拉低简体指标、不触发简体告警"
    assert codes["gsc_hant_canonical_hans"]["level"] == "info"
    assert "不用改摘要" in codes["gsc_hant_canonical_hans"]["fix"]
    assert codes["gsc_hant_not_indexed"]["level"] == "info"
    md = M.render_md(dict(rep.to_dict(), sections={"gsc": out}), None)
    assert "Google 收录(简体)" in md and "Google 收录(繁体,单列)" in md


def test_gsc_quota_goes_to_the_other_side_when_one_runs_out(monkeypatch):
    monkeypatch.setattr(M, "gsc_token", lambda raw: "tok")
    urls = [f"{SITE}/p/{i}.html" for i in range(10)] + [f"{HANT}/p/{i}.html" for i in range(100)]
    calls: list = []
    with _gsc_client(calls) as c:
        M.gsc(c, _rep(), {"GSC_SERVICE_ACCOUNT_JSON": "x"}, urls, f"{SITE}/sitemap.xml", {}, False, 60)
    assert len(calls) == 60 and sum(not M.is_hant_url(u) for u, _ in calls) == 10


# ─────────────────────────── 抽查与提交 ───────────────────────────

def test_pick_pages_newest_half_simplified_half_traditional():
    urls = [f"{SITE}/p/{i:02d}.html" for i in range(20)] + [f"{HANT}/p/{i:02d}.html" for i in range(20)]
    lm = {u: "2026-11-05" for u in urls}
    newest = M.pick_pages(urls, lm, {}, 10, date(2026, 11, 19))
    assert sum(M.is_hant_url(u) for u in newest) == 5
    only_hans = [u for u in urls if not M.is_hant_url(u)]
    assert M.pick_pages(only_hans, lm, {}, 10, date(2026, 11, 19)) == sorted(only_hans, reverse=True)[:10]


def test_baidu_push_skips_hant_urls():
    sent = []

    def handler(req):
        sent.extend(req.content.decode().split("\n"))
        return httpx.Response(200, json={"success": 2, "remain": 8})
    sm = {f"{HANT}/p/a.html": "2026-11-06", f"{SITE}/p/a.html": "2026-11-05", f"{SITE}/p/b.html": "2026-11-04"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        M.baidu(c, _rep(), "tok", sm, set(sm), {})
    assert sent == [f"{SITE}/p/a.html", f"{SITE}/p/b.html"]


def _site(root, repo_urls, live_urls, key, calls, hant_ok=True):
    """模拟线上站点:repo_urls 写进仓库 sitemap,live_urls 是线上 sitemap。"""
    sm = lambda us: ('<?xml version="1.0"?><urlset>' + "".join(  # noqa: E731
        f"<url><loc>{u}</loc><lastmod>2026-11-05</lastmod></url>" for u in us) + "</urlset>")
    (root / "sitemap.xml").write_text(sm(repo_urls), encoding="utf-8")
    page = ('<html lang="zh-CN"><head><title>t</title></head><body><h1>x</h1>' + "政策" * 30 + "</body></html>")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.indexnow.org":
            calls.append(json.loads(req.content))
            return httpx.Response(202)
        if req.url.scheme == "http" or req.url.host != M._host(SITE):
            return httpx.Response(301, headers={"location": SITE + "/"})
        p = req.url.path
        if p == f"/{key}.txt":
            return httpx.Response(200, text=key)
        if p == "/sitemap.xml":
            return httpx.Response(200, text=sm(live_urls))
        if p == "/robots.txt":
            return httpx.Response(200, text=f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
        if p == "/zh-hant":
            return httpx.Response(301, headers={"location": "/zh-hant/"}) if hant_ok else httpx.Response(404)
        if p == "/zh-hant/" and not hant_ok:
            return httpx.Response(404)
        return httpx.Response(200, text=page)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def monitor_env(tmp_path, monkeypatch):
    key = "0123456789abcdef0123456789abcdef"
    cfg = tmp_path / "seo.json"
    cfg.write_text(json.dumps({"indexnow_key": key, "indexnow_resubmit": {"epoch": "e2"}}), encoding="utf-8")
    monkeypatch.setattr(seo, "SEO_CONFIG", cfg)
    monkeypatch.setattr(M, "REPO_ROOT", tmp_path)
    return tmp_path, key


def test_resubmit_waits_until_server_has_new_version(monitor_env):
    root, key = monitor_env
    hans = [f"{SITE}/p/{i}.html" for i in range(3)]
    repo = hans + [u.replace(SITE, HANT, 1) for u in hans]
    out = root / "seo"
    out.mkdir()
    (out / "state.json").write_text(json.dumps({"indexnow": {u: "2026-11-05" for u in hans},
                                                "indexnow_epoch": "e1"}), encoding="utf-8")
    calls: list = []
    with _site(root, repo, hans, key, calls) as c:                 # 线上还是旧版:没有繁体页
        res = M.run(c, SITE, {}, date(2026, 11, 19), out, n_pages=3)
    codes = {i["code"] for i in res["report"]["issues"]}
    assert "deploy_lag" in codes and "indexnow_resubmit_deferred" in codes
    assert res["state"]["indexnow_epoch"] == "e1", "顺延,不记新 epoch"
    assert calls == [], "旧页面不整站重交"
    M.write_outputs(res["report"], out, res["state"])
    calls.clear()
    with _site(root, repo, repo, key, calls) as c:                 # 服务器跟上了
        res = M.run(c, SITE, {}, date(2026, 11, 20), out, n_pages=3)
    assert res["state"]["indexnow_epoch"] == "e2"
    assert sorted(calls[0]["urlList"]) == sorted(repo)


def test_check_site_reports_hant_home_and_redirect(monitor_env):
    root, key = monitor_env
    urls = [f"{SITE}/p/a.html"]
    with _site(root, urls, urls, key, [], hant_ok=False) as c:
        rep = M.Report(SITE, date(2026, 11, 19))
        out = M.check_site(c, rep, key, M.parse_sitemap((root / "sitemap.xml").read_text()))
    assert out["hant_home"] is False and "hant_home" in {i["code"] for i in rep.issues}
    with _site(root, urls, urls, key, []) as c:
        rep = M.Report(SITE, date(2026, 11, 19))
        out = M.check_site(c, rep, key, M.parse_sitemap((root / "sitemap.xml").read_text()))
    assert out["hant_home"] is True and not {"hant_home", "hant_redirect"} & {i["code"] for i in rep.issues}


def test_suspicious_hant_forms_become_a_report_issue(monitor_env):
    root, key = monitor_env
    (root / "zh-hant" / "p").mkdir(parents=True)
    (root / "zh-hant" / "p" / "x.html").write_text("<p>要求專傢俱備至少5年</p>", encoding="utf-8")
    rep = _rep()
    M.hant_check(rep, root / "zh-hant")
    iss = next(i for i in rep.issues if i["code"] == "hant_suspicious")
    assert rep.metrics["hant_suspicious"] == 1 and "p/x.html" in iss["items"][0]
    rep2 = _rep()
    (root / "zh-hant" / "p" / "x.html").write_text("<p>要求專家具備至少5年</p>", encoding="utf-8")
    M.hant_check(rep2, root / "zh-hant")
    assert rep2.metrics["hant_suspicious"] == 0 and not rep2.issues


def test_audit_html_checks_lang_and_hreflang():
    good = (f'<html lang="zh-Hant"><head><title>t</title><link rel="canonical" href="{HANT}/p/x.html">'
            f'<link rel="alternate" hreflang="zh-Hans" href="{SITE}/p/x.html">'
            f'<link rel="alternate" hreflang="zh-Hant" href="{HANT}/p/x.html">'
            f'<link rel="alternate" hreflang="x-default" href="{SITE}/p/x.html"></head><body><h1>x</h1></body></html>')
    probs = lambda h, u: M.audit_html(u, h, {})["problems"]  # noqa: E731
    assert not any("lang" in p for p in probs(good, f"{HANT}/p/x.html"))
    assert any("<html lang> 不是 zh-CN" in p for p in probs(good.replace(HANT + "/p/x.html\">", SITE + "/p/x.html\">", 1),
                                                           f"{SITE}/p/x.html"))
    missing = good.replace('<link rel="alternate" hreflang="x-default"', '<link rel="x"')
    assert any("hreflang 不全" in p for p in probs(missing, f"{HANT}/p/x.html"))


# ─────────────────────────── 爬虫统计 ───────────────────────────

def test_track_report_counts_hant_landing_separately(tmp_path, monkeypatch):
    from app import config
    (tmp_path / "sitemap.xml").write_text("".join(f"<loc>{u}</loc>" for u in (
        f"{SITE}/p/a.html", f"{SITE}/p/b.html", f"{HANT}/p/a.html", f"{HANT}/p/b.html", f"{HANT}/p/c.html")),
        encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    now = datetime(2026, 11, 19, 10, tzinfo=BKK)
    with session_scope() as s:
        s.execute(delete(CrawlHit))
        for path in ("/p/a.html", "/zh-hant/p/a.html", "/zh-hant/p/b.html"):
            s.add(CrawlHit(ts=now, day=now.date(), bot="Googlebot", group="search", path=path, status=200))
    with session_scope() as s:
        cov = T.report(s, 7, now=now)["coverage"]
        s.execute(delete(CrawlHit))
    assert cov["sitemap_landing"] == 2 and cov["crawled_by_search"] == 1 and cov["search_pct"] == 50.0
    assert cov["hant_sitemap_landing"] == 3 and cov["hant_crawled_by_search"] == 2
    keys = {k for k, _ in M.METRIC_ZH}
    assert {"crawl_hant_landing", "crawl_hant_by_search", "hant_suspicious", "gsc_hant_checked"} <= keys
