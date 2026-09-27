# -*- coding: utf-8 -*-
"""SEO / GEO 效果度量(服务端):爬虫抓取 + 搜索与 AI 来源的真人访问。

    GET /api/admin/seo?days=30   后台「SEO / GEO」页的数据,需 ADMIN_TOKEN

两类信号:
1. 爬虫抓取(CrawlHit):Googlebot、Bingbot、百度蜘蛛有没有来、抓了哪些页、有没有报错;
   GPTBot、ClaudeBot、PerplexityBot 等 AI 爬虫有没有来。爬虫不跑 JS,只能在服务端中间件里记。
2. 真人来源(PageHit.ref_host / utm_source):从搜索引擎点进来 = 已被收录且有排名;
   从 chatgpt.com、perplexity.ai 等点进来 = AI 回答引用了本站(GEO 的直接证据)。

每天 03:00 的 app.seo_monitor 会读这个接口,和 Search Console / Bing 的数据合在一起出日报。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from .config import DATA_DIR, settings
from .db import get_session, session_scope
from .models import CrawlHit, PageHit
from .stats import now_bkk, require_admin

log = logging.getLogger("policy.seo")
router = APIRouter(prefix=settings.api_prefix)

# (显示名, 分组, UA 正则)。顺序有意义:先匹配更具体的名字(OAI-SearchBot 早于 GPTBot 等)
BOTS: list[tuple[str, str, str]] = [
    ("Googlebot", "search", r"Googlebot|Google-InspectionTool|GoogleOther"),
    ("Bingbot", "search", r"bingbot|BingPreview|msnbot"),
    ("Baiduspider", "search", r"Baiduspider"),
    ("YandexBot", "search", r"YandexBot|YandexMobileBot"),
    ("Sogou", "search", r"Sogou"),
    ("360Spider", "search", r"360Spider|HaosouSpider"),
    ("DuckDuckBot", "search", r"DuckDuckBot"),
    ("Applebot", "search", r"Applebot(?!-Extended)"),
    ("Yeti(Naver)", "search", r"Yeti/"),
    ("OAI-SearchBot", "ai", r"OAI-SearchBot"),
    ("ChatGPT-User", "ai", r"ChatGPT-User"),
    ("GPTBot", "ai", r"GPTBot"),
    ("Claude-SearchBot", "ai", r"Claude-SearchBot"),
    ("Claude-User", "ai", r"Claude-User"),
    ("ClaudeBot", "ai", r"ClaudeBot|anthropic-ai"),
    ("PerplexityBot", "ai", r"PerplexityBot"),
    ("Perplexity-User", "ai", r"Perplexity-User"),
    ("Bytespider", "ai", r"Bytespider"),
    ("Amazonbot", "ai", r"Amazonbot"),
    ("Meta-AI", "ai", r"meta-externalagent|meta-externalfetcher"),
    ("CCBot", "ai", r"CCBot"),
    ("DuckAssistBot", "ai", r"DuckAssistBot"),
    ("MistralAI-User", "ai", r"MistralAI-User"),
    ("cohere-ai", "ai", r"cohere-ai"),
]
_BOT_RES = [(n, g, re.compile(p, re.I)) for n, g, p in BOTS]
SEARCH_BOTS = [n for n, g, _ in BOTS if g == "search"]

# 来源域名 → (渠道, 显示名)。按后缀匹配,google.co.th、m.baidu.com 都能归类
SEARCH_REFS = {"google": "Google", "bing.com": "Bing", "baidu.com": "百度", "sogou.com": "搜狗",
               "so.com": "360 搜索", "sm.cn": "神马", "duckduckgo.com": "DuckDuckGo",
               "yandex": "Yandex", "naver.com": "Naver", "search.yahoo": "Yahoo",
               "ecosia.org": "Ecosia", "brave.com": "Brave"}
AI_REFS = {"chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "openai.com": "ChatGPT",
           "perplexity.ai": "Perplexity", "claude.ai": "Claude", "gemini.google.com": "Gemini",
           "bard.google.com": "Gemini", "copilot.microsoft.com": "Copilot",
           "doubao.com": "豆包", "kimi.moonshot.cn": "Kimi", "kimi.com": "Kimi",
           "chat.deepseek.com": "DeepSeek", "yuanbao.tencent.com": "腾讯元宝",
           "metaso.cn": "秘塔", "tongyi.aliyun.com": "通义", "qianwen.com": "通义",
           "you.com": "You.com", "phind.com": "Phind", "poe.com": "Poe", "grok.com": "Grok",
           "chat.mistral.ai": "Mistral"}
SOCIAL_REFS = {"facebook.com": "Facebook", "t.co": "X", "x.com": "X", "twitter.com": "X",
               "line.me": "LINE", "weixin.qq.com": "微信", "weibo.com": "微博",
               "zhihu.com": "知乎", "xiaohongshu.com": "小红书", "reddit.com": "Reddit",
               "linkedin.com": "LinkedIn", "t.me": "Telegram", "youtube.com": "YouTube"}
# ChatGPT 搜索、Perplexity 等会在链接上带 utm_source
AI_UTM = {"chatgpt.com": "ChatGPT", "chatgpt": "ChatGPT", "openai": "ChatGPT",
          "perplexity": "Perplexity", "perplexity.ai": "Perplexity", "claude.ai": "Claude",
          "copilot.com": "Copilot", "gemini": "Gemini"}


def classify_bot(ua: str) -> tuple[str, str] | None:
    """UA → (爬虫名, search/ai);不是已知爬虫返回 None。"""
    if not ua:
        return None
    for name, group, rx in _BOT_RES:
        if rx.search(ua):
            return name, group
    return None


def _match(host: str, table: dict[str, str]) -> str:
    for key, name in table.items():
        if "." not in key:        # 品牌名(google、yandex):匹配任一级域名
            if re.search(rf"(^|\.){re.escape(key)}\.", host + "."):
                return name
        elif host == key or host.endswith("." + key):
            return name
    return ""


def channel_of(ref_host: str, utm_source: str = "") -> tuple[str, str]:
    """一次访问的来源渠道:(ai|search|social|referral|direct, 显示名)。AI 优先于搜索判定。"""
    host = (ref_host or "").lower()
    utm = (utm_source or "").lower()
    if utm in AI_UTM:
        return "ai", AI_UTM[utm]
    if host:
        for table, ch in ((AI_REFS, "ai"), (SEARCH_REFS, "search"), (SOCIAL_REFS, "social")):
            name = _match(host, table)
            if name:
                return ch, name
        return "referral", host
    if utm:
        return "referral", utm
    return "direct", ""


def record_crawl(ua: str, path: str, status: int, at: datetime | None = None) -> None:
    """中间件调用:识别爬虫并落库。任何异常都吞掉 —— 统计不能影响正常响应。"""
    if not settings.stats_enabled:
        return
    hit = classify_bot(ua)
    if not hit or path.startswith(settings.api_prefix + "/"):
        return
    at = at or now_bkk()
    try:
        with session_scope() as s:
            s.add(CrawlHit(ts=at, day=at.date(), bot=hit[0], group=hit[1], path=path[:255],
                           status=status))
    except Exception:  # noqa: BLE001
        log.exception("记录爬虫抓取失败")


def purge_crawls(s: Session, today: date | None = None) -> int:
    cutoff = (today or now_bkk().date()) - timedelta(days=settings.stats_retention_days)
    return s.execute(delete(CrawlHit).where(CrawlHit.day < cutoff)).rowcount or 0


def _is_landing(path: str) -> bool:
    return path.startswith("/p/") and path.endswith(".html")


def latest_monitor() -> dict | None:
    """每日 03:00 监控任务提交到仓库的最新报告(data/seo/latest.json)。"""
    f = DATA_DIR / "seo" / "latest.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def report(s: Session, days: int = 30, now: datetime | None = None) -> dict:
    now = now or now_bkk()
    end = now.date()
    start = end - timedelta(days=days - 1)
    rng = (CrawlHit.day >= start) & (CrawlHit.day <= end)

    bots = [{"bot": b, "group": g, "hits": n, "pages": p, "last_seen": last.isoformat() if last else None}
            for b, g, n, p, last in s.execute(
                select(CrawlHit.bot, CrawlHit.group, func.count(), func.count(distinct(CrawlHit.path)),
                       func.max(CrawlHit.day))
                .where(rng).group_by(CrawlHit.bot, CrawlHit.group)
                .order_by(func.count().desc(), CrawlHit.bot)).all()]
    by_day = {(d, g): n for d, g, n in s.execute(
        select(CrawlHit.day, CrawlHit.group, func.count()).where(rng)
        .group_by(CrawlHit.day, CrawlHit.group)).all()}
    series = [{"day": (start + timedelta(days=i)).isoformat(),
               "search": by_day.get((start + timedelta(days=i), "search"), 0),
               "ai": by_day.get((start + timedelta(days=i), "ai"), 0)} for i in range(days)]
    errors = [{"path": p, "status": st, "n": n, "bots": b} for p, st, n, b in s.execute(
        select(CrawlHit.path, CrawlHit.status, func.count(), func.group_concat(distinct(CrawlHit.bot))
               if settings.is_sqlite else func.string_agg(distinct(CrawlHit.bot), ","))
        .where(rng, CrawlHit.status >= 400).group_by(CrawlHit.path, CrawlHit.status)
        .order_by(func.count().desc()).limit(30)).all()]

    # 落地页覆盖率:sitemap 里的落地页,近 N 天被主流搜索爬虫抓过几成。抓取 ≠ 收录,但没抓过一定没收录
    crawled_search = {p for (p,) in s.execute(
        select(CrawlHit.path).distinct().where(rng, CrawlHit.group == "search")).all() if _is_landing(p)}
    crawled_ai = {p for (p,) in s.execute(
        select(CrawlHit.path).distinct().where(rng, CrawlHit.group == "ai")).all() if _is_landing(p)}
    sitemap_paths = _sitemap_paths()
    cov = {"sitemap_landing": len(sitemap_paths),
           "crawled_by_search": len(sitemap_paths & crawled_search),
           "crawled_by_ai": len(sitemap_paths & crawled_ai)}
    cov["search_pct"] = round(cov["crawled_by_search"] / cov["sitemap_landing"] * 100, 1) if sitemap_paths else None
    cov["never_crawled_sample"] = sorted(sitemap_paths - crawled_search)[:20]

    # 真人来源渠道
    pv = (PageHit.day >= start) & (PageHit.day <= end) & (PageHit.kind == "pv")
    channels: dict[str, int] = {}
    sources: dict[tuple[str, str], int] = {}
    landings: dict[tuple[str, str], int] = {}
    for host, utm, path, n in s.execute(
            select(PageHit.ref_host, PageHit.utm_source, PageHit.path, func.count())
            .where(pv).group_by(PageHit.ref_host, PageHit.utm_source, PageHit.path)).all():
        ch, name = channel_of(host, utm)
        channels[ch] = channels.get(ch, 0) + n
        if ch in ("search", "ai"):
            sources[(ch, name)] = sources.get((ch, name), 0) + n
            landings[(ch, path)] = landings.get((ch, path), 0) + n
    top = lambda d, ch: [{"key": k[1], "n": n} for k, n in  # noqa: E731
                         sorted(d.items(), key=lambda x: (-x[1], x[0])) if k[0] == ch][:15]

    return {
        "range": {"days": days, "start": start.isoformat(), "end": end.isoformat()},
        "generated_at": now.replace(microsecond=0).isoformat(),
        "crawlers": {"bots": bots, "series": series, "errors": errors,
                     "top_paths": [{"path": p, "n": n} for p, n in s.execute(
                         select(CrawlHit.path, func.count()).where(rng).group_by(CrawlHit.path)
                         .order_by(func.count().desc(), CrawlHit.path).limit(20)).all()]},
        "coverage": cov,
        "channels": channels,
        "search_sources": top(sources, "search"),
        "ai_sources": top(sources, "ai"),
        "search_landings": top(landings, "search"),
        "ai_landings": top(landings, "ai"),
        "monitor": latest_monitor(),
    }


def _sitemap_paths() -> set[str]:
    from .config import REPO_ROOT
    try:
        xml = (REPO_ROOT / "sitemap.xml").read_text(encoding="utf-8")
    except OSError:
        return set()
    base = settings.site_url
    return {loc[len(base):] for loc in re.findall(r"<loc>([^<]+)</loc>", xml)
            if loc.startswith(base) and _is_landing(loc[len(base):])}


@router.get("/admin/seo", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_seo(response: Response, days: int = Query(30, ge=1, le=400),
              s: Session = Depends(get_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return report(s, days)
