# -*- coding: utf-8 -*-
"""每日 SEO / GEO 监控(GitHub Actions 每天曼谷时间 03:00 运行,见 .github/workflows/seo.yml)。

    python -m app.seo_monitor                 # 检查 + 提交新页面 + 写日报
    python -m app.seo_monitor --no-submit     # 只检查,不向搜索引擎提交
    python -m app.seo_monitor --site http://127.0.0.1:8000 --no-submit   # 本地试跑

做什么:
1. 线上体检 —— 首页、robots、sitemap、llms.txt、feed、IndexNow 核验文件、HTTP→HTTPS 与裸域跳转;
   抽查落地页(canonical、noindex、标题、描述、H1、结构化数据、官方原文链接、内容是否单薄);
   对比线上 sitemap 与仓库 sitemap,发现服务器没同步。
2. 收录 —— Google Search Console(URL 检查接口逐页查收录状态、搜索表现、sitemap 状态)、
   Bing Webmaster(已收录页数、搜索词);没配凭据时用服务器记录的爬虫抓取间接判断。
3. 提交 —— IndexNow(Bing、Yandex、Naver、Seznam 共用)、百度普通收录、GSC sitemap;只提交新增或变更的页面。
4. GEO —— AI 爬虫抓取、AI 来源访问(服务器 /api/admin/seo);配了 PERPLEXITY_API_KEY 时,
   用 config/seo.json 里的问题实测 AI 回答是否引用本站。
5. 输出 —— data/seo/latest.json、latest.md(日报,含「待处理问题」与修改建议)、history.jsonl(趋势)、
   state.json(提交与收录检查的进度)。随后由每日例行的 Claude 会话读日报并修改站点。

所有外部凭据都是可选的,缺哪个就跳过哪一项,并在日报「未启用的数据源」里写明怎么配。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from .config import BKK, DATA_DIR, REPO_ROOT, settings

OUT_DIR = DATA_DIR / "seo"
UA = "thaipolicy-seo-monitor/1.0 (+https://www.thaipolicy.com/llms.txt)"
THIN_RE = re.compile(r"据标题|待原文核对")
LEVELS = {"error": 0, "warn": 1, "info": 2}
LEVEL_ZH = {"error": "🔴 严重", "warn": "🟠 需处理", "info": "🔵 建议"}


class Report:
    def __init__(self, site: str, today: date):
        self.site = site
        self.today = today
        self.issues: list[dict] = []
        self.metrics: dict = {}
        self.sections: dict = {}
        self.disabled: list[str] = []

    def issue(self, level: str, code: str, msg: str, fix: str = "", items: list | None = None):
        self.issues.append({"level": level, "code": code, "msg": msg, "fix": fix,
                            "items": (items or [])[:20]})

    def to_dict(self) -> dict:
        return {"date": self.today.isoformat(), "site": self.site,
                "generated_at": datetime.now(BKK).replace(microsecond=0).isoformat(),
                "metrics": self.metrics,
                "issues": sorted(self.issues, key=lambda i: (LEVELS[i["level"]], i["code"])),
                "sections": self.sections, "disabled": self.disabled}


# ─────────────────────────── 工具 ───────────────────────────

def parse_sitemap(xml: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for m in re.finditer(r"<url>\s*<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", xml):
        out[m.group(1).strip()] = m.group(2)
    return out


def _get(client: httpx.Client, url: str, **kw) -> tuple[httpx.Response | None, float, str]:
    t = time.monotonic()
    try:
        r = client.get(url, **kw)
        return r, time.monotonic() - t, ""
    except httpx.HTTPError as ex:
        return None, time.monotonic() - t, f"{type(ex).__name__}: {ex}"[:200]


def _attr(html: str, tag_re: str, attr: str) -> str | None:
    m = re.search(tag_re, html, re.I | re.S)
    if not m:
        return None
    a = re.search(rf'{attr}\s*=\s*"([^"]*)"', m.group(0), re.I)
    return a.group(1) if a else None


def audit_html(url: str, html: str, headers: dict) -> dict:
    """单页体检,返回 {problems: [...], thin: bool, title_len, ...}。纯函数,便于测试。"""
    probs = []
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = (title_m.group(1).strip() if title_m else "")
    if not title:
        probs.append("缺 <title>")
    elif len(title) > 60:
        probs.append(f"标题过长({len(title)} 字,搜索结果会被截断)")
    desc = _attr(html, r'<meta[^>]+name="description"[^>]*>', "content")
    if not desc:
        probs.append("缺 meta description")
    elif len(desc) < 40:
        probs.append(f"description 过短({len(desc)} 字)")
    canon = _attr(html, r'<link[^>]+rel="canonical"[^>]*>', "href")
    if not canon:
        probs.append("缺 canonical")
    elif canon != url:
        probs.append(f"canonical 指向别处:{canon}")
    robots = (_attr(html, r'<meta[^>]+name="robots"[^>]*>', "content") or "") + " " + \
        headers.get("x-robots-tag", "")
    if "noindex" in robots.lower():
        probs.append("被设为 noindex")
    h1 = len(re.findall(r"<h1[\s>]", html, re.I))
    if h1 != 1:
        probs.append(f"H1 数量为 {h1}")
    lds = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    for raw in lds:
        try:
            json.loads(raw.replace("<\\/", "</"))
        except ValueError:
            probs.append("结构化数据 JSON 解析失败")
    if not lds:
        probs.append("缺结构化数据")
    # 单条政策的落地页:/p/<uid>.html(专题、周汇总、影响对象等汇总页在子目录里,不算)
    is_landing = bool(re.search(r"/p/(?!index\.html)[^/]+\.html$", url))
    if is_landing and not re.search(r'href="https?://[^"/]*\.go\.th/', html):
        probs.append("缺官方原文(.go.th)链接")
    summary = ""
    m = re.search(r"中文摘要</h2><p>(.*?)</p>", html, re.S)
    if m:
        summary = re.sub(r"<[^>]+>", "", m.group(1))
    return {"problems": probs, "title": title, "title_len": len(title),
            "thin": bool(is_landing and 'class="points"' not in html
                         and (THIN_RE.search(summary) or len(summary) < 60)),
            "summary_len": len(summary)}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _apex(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ─────────────────────────── 1. 线上体检 ───────────────────────────

def check_site(client: httpx.Client, rep: Report, key: str, repo_sitemap: dict) -> dict:
    site = rep.site
    out: dict = {}
    r, dt, err = _get(client, site + "/")
    out["home"] = {"status": r.status_code if r else None, "ms": round(dt * 1000), "error": err}
    if not r or r.status_code != 200:
        rep.issue("error", "site_down", f"首页无法访问:{err or r.status_code}",
                  "检查服务器 docker compose ps、nginx 状态与证书;修好前其他检查都没有意义")
        return out
    if dt > 2.5:
        rep.issue("warn", "slow_home", f"首页响应 {dt:.1f} 秒", "检查服务器负载、nginx gzip 与缓存")

    host = _host(site)
    if site.startswith("https://"):
        r2, _, err2 = _get(client, f"http://{host}/")
        loc = r2.headers.get("location", "") if r2 else ""
        if not r2 or r2.status_code not in (301, 308) or not loc.startswith(site):
            rep.issue("warn", "http_redirect", f"http:// 没有 301 到 {site}({err2 or (r2 and r2.status_code)} → {loc or '无'})",
                      "检查 /etc/nginx/conf.d/ 里本站 80 端口的 server 块")
        if host.startswith("www."):
            r3, _, err3 = _get(client, f"https://{_apex(host)}/")
            loc = r3.headers.get("location", "") if r3 else ""
            if not r3 or r3.status_code not in (301, 308) or not loc.startswith(site):
                rep.issue("warn", "apex_redirect", f"裸域 {_apex(host)} 没有 301 到 www({err3 or (r3 and r3.status_code)})",
                          "证书要同时覆盖裸域与 www;重跑 deploy/nginx-setup.sh")

    r, _, err = _get(client, site + "/robots.txt")
    robots = r.text if r is not None and r.status_code == 200 else ""
    out["robots"] = bool(robots)
    if not robots:
        rep.issue("error", "robots_missing", "robots.txt 无法访问", "确认 app.export 已生成 robots.txt 且 main.py 允许访问")
    else:
        if re.search(r"^Disallow:\s*/\s*$", robots, re.M):
            rep.issue("error", "robots_block", "robots.txt 含 `Disallow: /`,整站被屏蔽",
                      "robots.txt 由 backend/app/seo.py 的 render_robots 生成,检查是否被改动")
        if "Sitemap:" not in robots:
            rep.issue("warn", "robots_no_sitemap", "robots.txt 没有声明 Sitemap", "见 seo.render_robots")

    r, _, err = _get(client, site + "/sitemap.xml")
    live = parse_sitemap(r.text) if r is not None and r.status_code == 200 else {}
    local = site != settings.site_url      # 本地试跑:线上 sitemap 仍写正式域名,换过来再比对
    if local:
        live = {u.replace(settings.site_url, site, 1): lm for u, lm in live.items()}
    out["sitemap_live"] = len(live)
    out["sitemap_repo"] = len(repo_sitemap)
    if not live:
        rep.issue("error", "sitemap_missing", "线上 sitemap.xml 无法访问或为空", "在服务器上跑 deploy/sync.sh 并确认 app.export 成功")
    else:
        missing = sorted(set(repo_sitemap) - set(live))
        if missing:
            rep.issue("warn", "deploy_lag", f"仓库里有 {len(missing)} 个页面线上还没有(服务器未同步)",
                      "服务器每小时跑 deploy/sync.sh;持续出现说明 cron 失效或导出报错,看 /var/log/thai-policy-sync.log",
                      missing)
        foreign = [] if local else [u for u in live if _host(u) != host]
        if foreign:
            rep.issue("error", "sitemap_wrong_host", f"sitemap 里有 {len(foreign)} 个链接不是 {host}",
                      "服务器 .env 的 SITE_URL 要与正式域名一致", foreign)

    for name, what in (("llms.txt", "llms.txt(给 AI 的站点说明)"), ("feed.xml", "Atom 订阅"),
                       ("llms-full.txt", "llms-full.txt")):
        r, _, err = _get(client, f"{site}/{name}")
        ok = r is not None and r.status_code == 200 and len(r.text) > 50
        out[name] = ok
        if not ok:
            rep.issue("warn", f"missing_{name.replace('.', '_').replace('-', '_')}", f"{what} 线上无法访问",
                      "确认镜像已重建(deploy/sync.sh 在代码变动时会 up --build)")

    if key:
        r, _, err = _get(client, f"{site}/{key}.txt")
        out["indexnow_key"] = bool(r is not None and r.status_code == 200 and r.text.strip() == key)
        if not out["indexnow_key"]:
            rep.issue("warn", "indexnow_key", "IndexNow 核验文件线上不可用,今天不提交",
                      "服务器需要运行包含 config/seo.json 的新版本(重建镜像)")
    out["live_urls"] = sorted(live)
    return out


def pick_pages(urls: list[str], lastmods: dict, state: dict, n: int, today: date) -> list[str]:
    """抽查哪些页:最新 10 页必查,其余按「最久没查过」轮换,保证每页都会被定期覆盖。"""
    newest = sorted(urls, key=lambda u: (lastmods.get(u) or "", u), reverse=True)[:10]
    audited = state.get("audited", {})
    rest = sorted((u for u in urls if u not in newest), key=lambda u: (audited.get(u, ""), u))
    return (newest + rest)[:n]


def audit_pages(client: httpx.Client, rep: Report, urls: list[str], state: dict) -> dict:
    problems: dict[str, list[str]] = {}
    thin, fail, slow = [], [], []
    for u in urls:
        r, dt, err = _get(client, u)
        state.setdefault("audited", {})[u] = rep.today.isoformat()
        if r is None or r.status_code != 200:
            fail.append(f"{u} → {err or r.status_code}")
            continue
        if dt > 2.5:
            slow.append(u)
        # 页面里的 canonical 写的是正式域名;本地试跑时按正式域名比对
        a = audit_html(u.replace(rep.site, settings.site_url, 1), r.text,
                       {k.lower(): v for k, v in r.headers.items()})
        if a["problems"]:
            problems[u] = a["problems"]
        if a["thin"]:
            thin.append(u)
    if fail:
        rep.issue("error", "pages_failing", f"{len(fail)} 个页面打不开", "看服务器日志;落地页由 app.export 生成", fail)
    by_problem: dict[str, list[str]] = {}
    for u, ps in problems.items():
        for p in ps:
            by_problem.setdefault(re.split(r"[((::]", p)[0].strip(), []).append(u)
    for p, us in sorted(by_problem.items()):
        lvl = "error" if ("noindex" in p or "canonical" in p or "官方原文" in p) else "warn"
        rep.issue(lvl, f"page:{p}",
                  f"{len(us)} 个页面:{p}", "落地页模板在 backend/app/seo.py 的 render_page / _head", us)
    if thin:
        rep.issue("info", "thin_content", f"抽查的 {len(urls)} 页中有 {len(thin)} 页摘要只依据标题(内容单薄)",
                  "单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点",
                  thin)
    if slow:
        rep.issue("warn", "slow_pages", f"{len(slow)} 个页面响应超过 2.5 秒", "检查服务器负载", slow)
    return {"checked": len(urls), "ok": len(urls) - len(fail) - len(problems),
            "with_problems": len(problems), "failed": len(fail), "thin": len(thin)}


# ─────────────────────────── 2. 服务器侧:爬虫与来源 ───────────────────────────

def server_stats(client: httpx.Client, rep: Report, token: str, baidu_on: bool = False) -> dict | None:
    if not token:
        rep.disabled.append("ADMIN_TOKEN:没配置,拿不到服务器记录的爬虫抓取与搜索/AI 来源访问。"
                            "在 GitHub Secrets 里加 ADMIN_TOKEN(与服务器 .env 相同)")
        return None
    try:
        r = client.get(f"{rep.site}/api/admin/seo", params={"days": 7},
                       headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as ex:
        rep.issue("warn", "admin_api", f"/api/admin/seo 请求失败:{ex}"[:200], "服务器是否已更新到含 seo_track 的版本")
        return None
    if r.status_code != 200:
        rep.issue("warn", "admin_api", f"/api/admin/seo 返回 {r.status_code}",
                  "401 = GitHub 里的 ADMIN_TOKEN 与服务器不一致;404 = 服务器没配 ADMIN_TOKEN 或版本太旧")
        return None
    d = r.json()
    bots = {b["bot"]: b for b in d["crawlers"]["bots"]}
    search_hits = sum(b["hits"] for b in d["crawlers"]["bots"] if b["group"] == "search")
    ai_hits = sum(b["hits"] for b in d["crawlers"]["bots"] if b["group"] == "ai")
    rep.metrics.update({
        "crawl_search_7d": search_hits, "crawl_ai_7d": ai_hits,
        "googlebot_7d": bots.get("Googlebot", {}).get("hits", 0),
        "bingbot_7d": bots.get("Bingbot", {}).get("hits", 0),
        "baiduspider_7d": bots.get("Baiduspider", {}).get("hits", 0),
        "crawl_coverage_pct": d["coverage"].get("search_pct"),
        "visits_search_7d": d["channels"].get("search", 0),
        "visits_ai_7d": d["channels"].get("ai", 0),
    })
    # 百度默认不追踪(不做百度推送时,蜘蛛来不来不是需要处理的问题);配了 BAIDU_PUSH_TOKEN 才提醒
    watch = [("Googlebot", "Google"), ("Bingbot", "Bing")] + ([("Baiduspider", "百度")] if baidu_on else [])
    for b, name in watch:
        if not bots.get(b):
            rep.issue("warn", f"no_{b.lower()}", f"近 7 天没有 {b} 抓取记录",
                      f"在 {name} 站长平台验证站点并提交 sitemap;新站通常需要 1–4 周才开始抓取")
    # 只报近两天仍在发生的:已经修好的路径,7 天窗口里的旧记录不再天天提醒
    since = (rep.today - timedelta(days=1)).isoformat()
    recent = [e for e in d["crawlers"]["errors"] if (e.get("last_seen") or since) >= since]
    if recent:
        rep.issue("warn", "crawl_errors", f"爬虫近两天遇到 {len(recent)} 个报错路径",
                  "404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志",
                  [f"{e['status']} {e['path']}({e['bots']},最近 {e.get('last_seen') or '—'})" for e in recent])
    never = d["coverage"].get("never_crawled_sample") or []
    if d["coverage"].get("sitemap_landing") and never:
        rep.issue("info", "never_crawled", f"{len(never)}+ 个落地页近 7 天未被搜索爬虫抓取",
                  "增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交", never)
    return d


# ─────────────────────────── 3. Google Search Console ───────────────────────────

GSC = "https://www.googleapis.com/webmasters/v3/sites/"
GSC_INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def gsc_token(raw: str) -> str:
    """服务账号 JSON → OAuth access token。只在配置了 GSC 时才需要 google-auth。"""
    from google.auth.transport.requests import Request as GRequest
    from google.oauth2 import service_account
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/webmasters"])
    creds.refresh(GRequest())
    return creds.token


def gsc(client: httpx.Client, rep: Report, env: dict, urls: list[str], sitemap_url: str,
        state: dict, submit: bool, n_inspect: int) -> dict | None:
    raw = env.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        rep.disabled.append("Google Search Console:没配置 GSC_SERVICE_ACCOUNT_JSON,无法直接查询 Google 收录状态。"
                            "配置方法见 docs/seo.md「接入 Search Console」")
        return None
    prop = env.get("GSC_PROPERTY") or f"sc-domain:{_apex(_host(rep.site))}"
    try:
        tok = gsc_token(raw)
    except Exception as ex:  # noqa: BLE001
        rep.issue("warn", "gsc_auth", f"Search Console 认证失败:{ex}"[:200],
                  "检查 GSC_SERVICE_ACCOUNT_JSON 是否完整,服务账号邮箱是否已加为该资源的用户")
        return None
    h = {"Authorization": f"Bearer {tok}"}
    base = GSC + quote(prop, safe="")
    out: dict = {"property": prop}

    end = rep.today - timedelta(days=3)          # GSC 数据约有 2–3 天延迟
    start = end - timedelta(days=27)
    q = lambda dims, limit=25: client.post(base + "/searchAnalytics/query", headers=h, json={  # noqa: E731
        "startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": limit})
    try:
        r = q([])
        if r.status_code == 403:
            rep.issue("warn", "gsc_forbidden", f"服务账号无权访问 {prop}",
                      "在 Search Console → 设置 → 用户和权限,把服务账号邮箱加为「完整」权限用户;"
                      "资源类型不是网域时,在 GitHub Variables 设 GSC_PROPERTY=https://www.thaipolicy.com/")
            return None
        r.raise_for_status()
        tot = (r.json().get("rows") or [{}])[0]
        out["totals_28d"] = {k: tot.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")}
        out["top_queries"] = [{"q": x["keys"][0], "clicks": x["clicks"], "impr": x["impressions"],
                               "pos": round(x["position"], 1)} for x in (q(["query"]).json().get("rows") or [])]
        out["top_pages"] = [{"page": x["keys"][0], "clicks": x["clicks"], "impr": x["impressions"],
                             "pos": round(x["position"], 1)} for x in (q(["page"]).json().get("rows") or [])]
        rep.metrics.update({"gsc_clicks_28d": out["totals_28d"]["clicks"],
                            "gsc_impressions_28d": out["totals_28d"]["impressions"],
                            # 没有曝光时没有排名可言,不要显示成 0
                            "gsc_position": (round(out["totals_28d"]["position"], 1)
                                             if out["totals_28d"]["impressions"] else None)})
        # 高曝光低点击:标题/描述需要改写的候选
        low_ctr = [p for p in out["top_pages"] if p["impr"] >= 50 and p["clicks"] / p["impr"] < 0.01]
        if low_ctr:
            rep.issue("info", "low_ctr", f"{len(low_ctr)} 个页面曝光多但几乎没人点",
                      "改写这些页面的 <title> 与 description,把关键信息(谁、什么、何时生效)前置",
                      [f"{p['page']}(曝光 {p['impr']},点击 {p['clicks']},排名 {p['pos']})" for p in low_ctr])
    except httpx.HTTPError as ex:
        rep.issue("warn", "gsc_query", f"Search Console 搜索数据查询失败:{ex}"[:200], "")

    # sitemap 状态,没提交过就提交
    try:
        sms = client.get(base + "/sitemaps", headers=h).json().get("sitemap") or []
        mine = next((x for x in sms if x.get("path") == sitemap_url), None)
        if mine:
            c = next((x for x in mine.get("contents") or [] if x.get("type") == "web"), {})
            out["sitemap"] = {"submitted": int(c.get("submitted", 0) or 0),
                              "last_downloaded": mine.get("lastDownloaded"),
                              "errors": int(mine.get("errors", 0) or 0)}
            if out["sitemap"]["errors"]:
                rep.issue("warn", "gsc_sitemap_errors", f"GSC 报告 sitemap 有 {out['sitemap']['errors']} 个错误",
                          "在 Search Console → 站点地图 查看详情")
        elif submit:
            rs = client.put(base + "/sitemaps/" + quote(sitemap_url, safe=""), headers=h)
            out["sitemap_submitted"] = rs.status_code in (200, 204)
    except (httpx.HTTPError, ValueError) as ex:
        rep.issue("info", "gsc_sitemap", f"读取 GSC sitemap 状态失败:{ex}"[:200], "")

    # 逐页收录检查(配额每天 2000 次,这里只查一部分,按「最久没查」轮换,结果累积在 state 里)
    idx = state.setdefault("gsc_index", {})
    order = sorted(urls, key=lambda u: (idx.get(u, {}).get("checked", ""), u))[:n_inspect]
    for u in order:
        try:
            r = client.post(GSC_INSPECT, headers=h, json={"inspectionUrl": u, "siteUrl": prop,
                                                          "languageCode": "zh-CN"})
            if r.status_code == 429:
                break
            r.raise_for_status()
            s = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
            idx[u] = {"checked": rep.today.isoformat(), "verdict": s.get("verdict", ""),
                      "coverage": s.get("coverageState", ""), "last_crawl": s.get("lastCrawlTime", ""),
                      "canonical": s.get("googleCanonical", "")}
        except (httpx.HTTPError, ValueError):
            continue
    live = set(urls)
    known = {u: v for u, v in idx.items() if u in live}
    indexed = [u for u, v in known.items() if v.get("verdict") == "PASS"]
    states: dict[str, int] = {}
    for v in known.values():
        states[v.get("coverage") or "未知"] = states.get(v.get("coverage") or "未知", 0) + 1
    out["index"] = {"checked": len(known), "indexed": len(indexed), "total": len(urls),
                    "coverage_states": states}
    rep.metrics.update({"gsc_indexed": len(indexed), "gsc_checked": len(known)})
    not_idx = [f"{u}({v.get('coverage')})" for u, v in known.items() if v.get("verdict") != "PASS"]
    if not_idx:
        rep.issue("warn" if len(not_idx) > len(indexed) else "info", "gsc_not_indexed",
                  f"已检查 {len(known)} 页,{len(not_idx)} 页未被 Google 收录",
                  "「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复",
                  not_idx)
    wrong_canon = [u for u, v in known.items() if v.get("canonical") and v["canonical"] != u]
    if wrong_canon:
        rep.issue("warn", "gsc_canonical", f"{len(wrong_canon)} 页 Google 选了别的规范网址",
                  "通常是内容过于相似;让摘要与要点更具体", wrong_canon)
    return out


# ─────────────────────────── 4. Bing Webmaster ───────────────────────────

BING = "https://ssl.bing.com/webmaster/api.svc/json/"


def _bing_date(v) -> str:
    m = re.search(r"\d{10,13}", str(v or ""))
    return datetime.fromtimestamp(int(m.group(0)[:10]), BKK).date().isoformat() if m else ""


def bing(client: httpx.Client, rep: Report, key: str) -> dict | None:
    if not key:
        rep.disabled.append("Bing Webmaster:没配置 BING_WEBMASTER_API_KEY,拿不到 Bing 已收录页数与搜索词"
                            "(Bing 同时是 ChatGPT 搜索与 Copilot 的检索来源,GEO 很重要)")
        return None
    site = rep.site + "/"
    out: dict = {}
    try:
        r = client.get(BING + "GetCrawlStats", params={"siteUrl": site, "apikey": key})
        r.raise_for_status()
        rows = sorted(r.json().get("d") or [], key=lambda x: _bing_date(x.get("Date")))
        if rows:
            last = rows[-1]
            out["crawl"] = {"date": _bing_date(last.get("Date")), "in_index": last.get("InIndex"),
                            "crawled": last.get("CrawledPages"), "errors": last.get("CrawlErrors")}
            rep.metrics["bing_in_index"] = last.get("InIndex")
        r = client.get(BING + "GetQueryStats", params={"siteUrl": site, "apikey": key})
        r.raise_for_status()
        agg: dict[str, list] = {}
        for x in r.json().get("d") or []:
            a = agg.setdefault(x.get("Query", ""), [0, 0])
            a[0] += x.get("Impressions", 0) or 0
            a[1] += x.get("Clicks", 0) or 0
        out["top_queries"] = [{"q": q, "impr": a[0], "clicks": a[1]}
                              for q, a in sorted(agg.items(), key=lambda kv: -kv[1][0])[:20]]
        rep.metrics["bing_impressions"] = sum(a[0] for a in agg.values())
        rep.metrics["bing_clicks"] = sum(a[1] for a in agg.values())
    except (httpx.HTTPError, ValueError) as ex:
        rep.issue("warn", "bing_api", f"Bing Webmaster 接口失败:{ex}"[:200],
                  "确认站点已在 Bing Webmaster 验证,API Key 来自「设置 → API 访问」")
    return out


# ─────────────────────────── 5. 提交:IndexNow / 百度 ───────────────────────────

def changed_urls(sitemap: dict[str, str | None], done: dict[str, str]) -> list[str]:
    """新增或 lastmod 变化的 URL,最新的排前面。"""
    return sorted((u for u, lm in sitemap.items() if done.get(u) != (lm or "")),
                  key=lambda u: (sitemap[u] or "", u), reverse=True)


def indexnow(client: httpx.Client, rep: Report, key: str, sitemap: dict, live: set[str],
             state: dict) -> dict:
    done = state.setdefault("indexnow", {})
    todo = [u for u in changed_urls(sitemap, done) if u in live][:10000]
    if not todo:
        return {"submitted": 0}
    host = _host(rep.site)
    try:
        r = client.post("https://api.indexnow.org/indexnow", json={
            "host": host, "key": key, "keyLocation": f"{rep.site}/{key}.txt", "urlList": todo})
    except httpx.HTTPError as ex:
        rep.issue("warn", "indexnow", f"IndexNow 提交失败:{ex}"[:200], "明天会自动重试")
        return {"submitted": 0, "error": str(ex)[:200]}
    if r.status_code in (200, 202):
        for u in todo:
            done[u] = sitemap[u] or ""
        return {"submitted": len(todo), "status": r.status_code}
    rep.issue("warn", "indexnow", f"IndexNow 返回 {r.status_code}",
              "403 = 核验文件与 key 不一致;422 = URL 不属于该域名;429 = 提交过于频繁")
    return {"submitted": 0, "status": r.status_code}


def baidu(client: httpx.Client, rep: Report, token: str, sitemap: dict, live: set[str],
          state: dict) -> dict | None:
    if not token:
        return None                     # 百度是可选项,不配就静默跳过,日报里不提
    done = state.setdefault("baidu", {})
    quota = int(state.get("baidu_remain", 10) or 10)
    todo = [u for u in changed_urls(sitemap, done) if u in live][:max(quota, 1)]
    if not todo:
        return {"submitted": 0}
    try:
        r = client.post("http://data.zz.baidu.com/urls", params={"site": rep.site, "token": token},
                        content="\n".join(todo).encode(), headers={"Content-Type": "text/plain"})
        d = r.json()
    except (httpx.HTTPError, ValueError) as ex:
        rep.issue("warn", "baidu", f"百度推送失败:{ex}"[:200], "")
        return {"submitted": 0}
    if "success" in d:
        for u in todo[:d["success"]]:
            done[u] = sitemap[u] or ""
        state["baidu_remain"] = d.get("remain", quota)
        return {"submitted": d["success"], "remain": d.get("remain")}
    rep.issue("warn", "baidu", f"百度推送返回:{d.get('message', d)}"[:200],
              "site init fail = 站点未在百度搜索资源平台验证;over quota = 当天配额用完")
    return {"submitted": 0, "error": d}


# ─────────────────────────── 6. GEO:AI 回答是否引用本站 ───────────────────────────

PPLX_URL = "https://api.perplexity.ai/v1/agent"
PPLX_MODEL = "perplexity/sonar"


def _urls(obj) -> list[str]:
    """从 Agent API 响应里收集来源链接:output[] 中 type=search_results 的 results[].url,
    以及回答里的引用注解。字段层级各版本不完全一致,这里递归收集所有 url / 引用字符串。"""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "uri") and isinstance(v, str) and v.startswith("http"):
                out.append(v)
            else:
                out += _urls(v)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, str) and v.startswith("http"):
                out.append(v)            # 旧格式:citations 是字符串数组
            else:
                out += _urls(v)
    return out


PPLX_HINT = {
    401: "API Key 无效:到 perplexity.ai → Settings → API 重新生成,更新 GitHub Secret PERPLEXITY_API_KEY",
    402: "账户余额不足:在 perplexity.ai → Settings → API → Billing 充值",
    403: "按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,"
         "或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)",
}


def _api_error(r: httpx.Response) -> str:
    """从错误响应里取出人能看懂的原因(JSON 的 error.message,或 HTML/纯文本的前 120 字)。"""
    try:
        d = r.json()
        err = d.get("error") if isinstance(d, dict) else None
        msg = (err.get("message") if isinstance(err, dict) else err) or d.get("detail") or d.get("message")
        return str(msg)[:160] if msg else ""
    except ValueError:
        text = re.sub(r"<[^>]+>", " ", r.text or "")
        return re.sub(r"\s+", " ", text).strip()[:120]


def geo_probe(client: httpx.Client, rep: Report, key: str, questions: list[str]) -> dict | None:
    if not key:
        rep.disabled.append("GEO 实测:没配置 PERPLEXITY_API_KEY,无法实测 AI 搜索回答是否引用本站"
                            "(每天 5 个问题约 0.03 美元);仍可在服务器数据里看 AI 爬虫与 AI 来源访问")
        return None
    apex = _apex(_host(rep.site))
    results, competitors = [], {}
    for q in questions[:8]:
        try:
            # Sonar 的 chat/completions 已于 2026-09-27 下线,改用 Agent API;联网搜索要显式开
            r = client.post(PPLX_URL, timeout=90, headers={"Authorization": f"Bearer {key}"},
                            json={"model": PPLX_MODEL, "input": q, "tools": [{"type": "web_search"}]})
        except httpx.HTTPError as ex:
            results.append({"q": q, "error": f"{type(ex).__name__}: {ex}"[:160]})
            continue
        if r.status_code != 200:
            detail = _api_error(r)
            results.append({"q": q, "error": f"HTTP {r.status_code} {detail}"[:200]})
            if r.status_code in (401, 402, 403):
                # 账号问题,后面的问题问了也一样,别浪费请求
                rep.issue("warn", "geo_api", f"Perplexity 接口返回 {r.status_code}:{detail or '无详情'}"[:300],
                          PPLX_HINT.get(r.status_code, ""))
                break
            continue
        try:
            d = r.json()
        except ValueError:
            results.append({"q": q, "error": "返回不是 JSON"})
            continue
        if isinstance(d, dict) and d.get("status") in ("failed", "cancelled", "incomplete"):
            results.append({"q": q, "error": f"回答未完成:{d.get('status')} {_api_error(r)}"[:200]})
            continue
        hosts = [_host(c) for c in _urls(d.get("output") if isinstance(d, dict) else d)
                 + _urls({k: d.get(k) for k in ("citations", "search_results")} if isinstance(d, dict) else [])]
        for h in set(hosts):
            if not h.endswith(apex):
                competitors[h] = competitors.get(h, 0) + 1
        results.append({"q": q, "cited": any(h.endswith(apex) for h in hosts),
                        "sources": sorted(set(hosts))[:10]})
    asked = [x for x in results if "error" not in x]
    cited = [x for x in asked if x["cited"]]
    rep.metrics.update({"geo_asked": len(asked), "geo_cited": len(cited)})
    if asked and not cited:
        rep.issue("info", "geo_not_cited", f"{len(asked)} 个实测问题的 AI 回答都没有引用本站",
                  "对照被引用的来源(见 GEO 一节),补对应主题的专题页与问答式要点;确保 Bing 已收录",
                  [x["q"] for x in asked])
    return {"results": results,
            "top_cited_domains": sorted(competitors.items(), key=lambda kv: -kv[1])[:15]}


# ─────────────────────────── 输出 ───────────────────────────

def _delta(cur, prev) -> str:
    if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)) or cur == prev:
        return ""
    return f"({'+' if cur > prev else ''}{round(cur - prev, 1)})"


METRIC_ZH = [("sitemap_urls", "sitemap 页面数"), ("pages_checked", "今日抽查页数"),
             ("pages_with_problems", "抽查有问题页数"), ("thin_pages", "内容单薄页数(抽查)"),
             ("gsc_indexed", "Google 已确认收录"), ("gsc_checked", "Google 已检查"),
             ("gsc_impressions_28d", "Google 曝光(28 天)"), ("gsc_clicks_28d", "Google 点击(28 天)"),
             ("gsc_position", "Google 平均排名"), ("bing_in_index", "Bing 已收录"),
             ("bing_impressions", "Bing 曝光"), ("googlebot_7d", "Googlebot 抓取(7 天)"),
             ("bingbot_7d", "Bingbot 抓取(7 天)"), ("baiduspider_7d", "百度蜘蛛抓取(7 天)"),
             ("crawl_ai_7d", "AI 爬虫抓取(7 天)"), ("crawl_coverage_pct", "落地页被搜索爬虫抓取占比 %"),
             ("visits_search_7d", "搜索来源访问(7 天)"), ("visits_ai_7d", "AI 来源访问(7 天)"),
             ("geo_cited", "AI 实测引用本站(题)"), ("indexnow_submitted", "今日 IndexNow 提交"),
             ("baidu_submitted", "今日百度推送")]


def render_md(d: dict, prev: dict | None) -> str:
    m, pm = d["metrics"], (prev or {}).get("metrics", {})
    out = [f"# SEO / GEO 日报 · {d['date']}", "",
           f"站点 {d['site']} · 生成于 {d['generated_at']}(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,"
           "每日例行会话据此修改站点。", ""]
    errs = [i for i in d["issues"] if i["level"] == "error"]
    warns = [i for i in d["issues"] if i["level"] == "warn"]
    out += ["## 结论", "",
            f"- 严重问题 {len(errs)} 个,需处理 {len(warns)} 个,建议 {len(d['issues']) - len(errs) - len(warns)} 个。"]
    if m.get("gsc_checked"):
        out.append(f"- Google 收录:已检查 {m['gsc_checked']} 页,确认收录 {m.get('gsc_indexed', 0)} 页"
                   f"(sitemap 共 {m.get('sitemap_urls', '—')} 页)。")
    else:
        out.append("- Google 收录:未接入 Search Console,只能从爬虫抓取与搜索来源访问间接判断。")
    if "googlebot_7d" in m:
        out.append(f"- 近 7 天抓取:Googlebot {m['googlebot_7d']} · Bingbot {m['bingbot_7d']} · "
                   f"百度 {m['baiduspider_7d']} · AI 爬虫 {m['crawl_ai_7d']};来访:搜索 {m['visits_search_7d']} · AI {m['visits_ai_7d']}。")
    out.append("")
    out += ["## 待处理问题", ""]
    if not d["issues"]:
        out += ["今天没有发现问题。", ""]
    for i in d["issues"]:
        out.append(f"- **{LEVEL_ZH[i['level']]}** `{i['code']}` {i['msg']}")
        if i["fix"]:
            out.append(f"  - 建议:{i['fix']}")
        for it in i["items"][:8]:
            out.append(f"  - {it}")
        if len(i["items"]) > 8:
            out.append(f"  - ……共 {len(i['items'])} 项,完整列表见 latest.json")
    out += ["", "## 关键指标(括号内为较前一日变化)", "", "| 指标 | 今日 |", "|---|---|"]
    out += [f"| {zh} | {m[k]} {_delta(m[k], pm.get(k))} |" for k, zh in METRIC_ZH if m.get(k) is not None]
    sec = d["sections"]
    g = sec.get("gsc") or {}
    if g.get("top_queries"):
        out += ["", "## Google 搜索词(28 天)", "", "| 搜索词 | 曝光 | 点击 | 排名 |", "|---|---|---|---|"]
        out += [f"| {x['q']} | {x['impr']} | {x['clicks']} | {x['pos']} |" for x in g["top_queries"][:15]]
    if g.get("index", {}).get("coverage_states"):
        out += ["", "## Google 收录状态分布(已检查页面)", ""]
        out += [f"- {k}:{v}" for k, v in sorted(g["index"]["coverage_states"].items(), key=lambda kv: -kv[1])]
    b = sec.get("bing") or {}
    if b.get("top_queries"):
        out += ["", "## Bing 搜索词", ""] + [f"- {x['q']}:曝光 {x['impr']} · 点击 {x['clicks']}"
                                           for x in b["top_queries"][:10]]
    srv = sec.get("server") or {}
    if srv:
        out += ["", "## 爬虫抓取(近 7 天)", "", "| 爬虫 | 类型 | 次数 | 页面数 | 最近 |", "|---|---|---|---|---|"]
        out += [f"| {x['bot']} | {'搜索' if x['group'] == 'search' else 'AI'} | {x['hits']} | {x['pages']} | {x['last_seen']} |"
                for x in srv["crawlers"]["bots"]] or ["| — | — | 0 | 0 | — |"]
        if srv.get("ai_sources") or srv.get("search_sources"):
            out += ["", "## 来访渠道(近 7 天)", ""]
            out += [f"- 搜索 · {x['key']}:{x['n']}" for x in srv.get("search_sources", [])]
            out += [f"- AI · {x['key']}:{x['n']}" for x in srv.get("ai_sources", [])]
    geo = sec.get("geo") or {}
    if geo.get("results"):
        out += ["", "## GEO 实测(Perplexity)", ""]
        out += [f"- {'⚠️' if x.get('error') else '✅' if x.get('cited') else '❌'} {x['q']}" + (f" —— 引用:{', '.join(x.get('sources', [])[:5])}"
                                                                   if x.get("sources") else f" —— {x.get('error', '')}")
                for x in geo["results"]]
        if geo.get("top_cited_domains"):
            out.append("- 被引用最多的其他站点:" + "、".join(f"{h}({n})" for h, n in geo["top_cited_domains"][:8]))
    sub = sec.get("submit") or {}
    out += ["", "## 今日提交", "",
            f"- IndexNow:{(sub.get('indexnow') or {}).get('submitted', 0)} 个 URL",
            *([f"- 百度:{sub['baidu'].get('submitted', 0)} 个 URL"] if sub.get("baidu") else []),
            f"- GSC sitemap:{'已提交' if (g or {}).get('sitemap_submitted') else ('已存在' if g.get('sitemap') else '—')}"]
    if d["disabled"]:
        out += ["", "## 未启用的数据源", ""] + [f"- {x}" for x in d["disabled"]]
    return "\n".join(out) + "\n"


def write_outputs(d: dict, out_dir: Path, state: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    hist_f = out_dir / "history.jsonl"
    hist = [json.loads(x) for x in hist_f.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if hist_f.exists() else []
    hist = [h for h in hist if h.get("date") != d["date"]]
    prev = hist[-1] if hist else None
    hist.append({"date": d["date"], "metrics": d["metrics"],
                 "issues": {lv: sum(1 for i in d["issues"] if i["level"] == lv) for lv in LEVELS}})
    hist = hist[-400:]
    d["trend"] = hist[-30:]
    hist_f.write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in hist), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "latest.md").write_text(render_md(d, prev), encoding="utf-8")
    (out_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                                        encoding="utf-8")


# ─────────────────────────── 主流程 ───────────────────────────

def run(client: httpx.Client, site: str, env: dict, today: date, out_dir: Path,
        submit: bool = True, n_pages: int = 40, n_inspect: int = 60) -> dict:
    from .seo import seo_config
    cfg = seo_config()
    key = cfg.get("indexnow_key", "")
    rep = Report(site.rstrip("/"), today)
    state = load_json(out_dir / "state.json", {})
    sm_file = REPO_ROOT / "sitemap.xml"
    repo_sm = parse_sitemap(sm_file.read_text(encoding="utf-8")) if sm_file.exists() else {}
    # 仓库 sitemap 按 SITE_URL 生成;本地试跑换了 --site 时把域名换过来再比对
    if repo_sm and settings.site_url != rep.site:
        repo_sm = {u.replace(settings.site_url, rep.site, 1): lm for u, lm in repo_sm.items()}
    rep.metrics["sitemap_urls"] = len(repo_sm)

    basics = check_site(client, rep, key, repo_sm)
    live = set(basics.pop("live_urls", []))
    rep.sections["site"] = basics
    if rep.issues and rep.issues[0]["code"] == "site_down":
        return {"report": rep.to_dict(), "state": state}

    urls = sorted(live) or sorted(repo_sm)
    pages = pick_pages(urls, repo_sm, state, n_pages, today)
    a = audit_pages(client, rep, pages, state)
    rep.sections["audit"] = a
    rep.metrics.update({"pages_checked": a["checked"], "pages_with_problems": a["with_problems"] + a["failed"],
                        "thin_pages": a["thin"]})

    srv = server_stats(client, rep, env.get("ADMIN_TOKEN", ""), baidu_on=bool(env.get("BAIDU_PUSH_TOKEN")))
    if srv:
        srv.pop("monitor", None)
        rep.sections["server"] = srv
    rep.sections["gsc"] = gsc(client, rep, env, urls, rep.site + "/sitemap.xml", state, submit, n_inspect)
    rep.sections["bing"] = bing(client, rep, env.get("BING_WEBMASTER_API_KEY", ""))

    sub: dict = {}
    if submit and key and basics.get("indexnow_key"):
        sub["indexnow"] = indexnow(client, rep, key, repo_sm, live, state)
        rep.metrics["indexnow_submitted"] = sub["indexnow"].get("submitted", 0)
    if submit:
        sub["baidu"] = baidu(client, rep, env.get("BAIDU_PUSH_TOKEN", ""), repo_sm, live, state)
        if sub["baidu"]:
            rep.metrics["baidu_submitted"] = sub["baidu"].get("submitted", 0)
    rep.sections["submit"] = sub
    rep.sections["geo"] = geo_probe(client, rep, env.get("PERPLEXITY_API_KEY", ""),
                                    cfg.get("geo_questions") or [])
    return {"report": rep.to_dict(), "state": state}


def main() -> None:
    ap = argparse.ArgumentParser(description="每日 SEO / GEO 监控")
    ap.add_argument("--site", default=settings.site_url, help="要检查的站点(默认 SITE_URL)")
    ap.add_argument("--out", default=str(OUT_DIR), help="日报输出目录")
    ap.add_argument("--no-submit", action="store_true", help="不向搜索引擎提交")
    ap.add_argument("--pages", type=int, default=40, help="每天抽查多少个页面")
    ap.add_argument("--inspect", type=int, default=60, help="每天用 GSC 检查多少个 URL 的收录状态")
    args = ap.parse_args()
    env = {k: os.getenv(k, "") for k in ("ADMIN_TOKEN", "GSC_SERVICE_ACCOUNT_JSON", "GSC_PROPERTY",
                                         "BING_WEBMASTER_API_KEY", "BAIDU_PUSH_TOKEN", "PERPLEXITY_API_KEY")}
    today = datetime.now(BKK).date()
    with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": UA}) as client:
        res = run(client, args.site, env, today, Path(args.out), submit=not args.no_submit,
                  n_pages=args.pages, n_inspect=args.inspect)
    d = res["report"]
    write_outputs(d, Path(args.out), res["state"])
    errs = [i for i in d["issues"] if i["level"] == "error"]
    print(f"SEO/GEO 日报 {d['date']}:严重 {len(errs)} · 共 {len(d['issues'])} 个问题 → {args.out}/latest.md")
    # 站点挂了、整站被屏蔽这类问题要让 Actions 变红,GitHub 会发邮件
    if any(i["code"] in ("site_down", "robots_block", "sitemap_missing") for i in errs):
        sys.exit(1)


if __name__ == "__main__":
    main()
