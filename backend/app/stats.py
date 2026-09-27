# -*- coding: utf-8 -*-
"""第一方站点统计:浏览量、访客、来源、检索词、外链、广告与打赏表现。

    POST /api/t                  前端 js/track.js 用 sendBeacon 上报,204 无内容
    GET  /api/admin/stats?days=  统计后台数据,需 ADMIN_TOKEN
    GET  /admin                  统计后台页面(admin.html)

    python3 -m app.stats --days 7    终端里看一份文字版报告
    python3 -m app.stats --purge     按 STATS_RETENTION_DAYS 清理旧记录

隐私设计(与 privacy.html 的承诺一一对应,改这里必须同步改那里):
- 不设 Cookie、不用 localStorage 识别用户;
- 不存 IP。访客 = hash(密钥 · 当天日期 · IP · UA) 取前 16 位,密钥按天变化,
  同一个人跨天不可关联 —— 所以只有「按天去重的访客数」,没有「回访率」;
- 浏览器发 Do Not Track / Global Privacy Control 时前后端都不记录;
- 爬虫与预览抓取不计入;
- 原始记录保留 STATS_RETENTION_DAYS 天(默认 400)后删除。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import case, delete, distinct, func, select
from sqlalchemy.orm import Session

from .config import BKK, settings
from .db import get_session, session_scope
from .models import Document, PageHit

log = logging.getLogger("policy.stats")
router = APIRouter(prefix=settings.api_prefix)

MAX_BODY = 2048
# 允许的事件名 → 含义。前端多发的名字一律丢弃,避免统计表被任意写入
EVENTS = {
    "search": "站内检索(label=关键词,value=命中数)",
    "outbound": "外链点击(label=目标域名)",
    "share": "复制/分享政策链接",
    "ad_view": "广告曝光(label=槽位|赞助方)",
    "ad_click": "广告点击(label=槽位|赞助方)",
    "tip_open": "打开打赏弹窗(label=入口)",
    "tip_amount": "选择打赏金额(label=金额)",
    "tip_link": "点击外部打赏渠道(label=渠道)",
}
BOT_RE = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|facebookexternalhit|"
                    r"embedly|curl|wget|python-|httpx|go-http|java/|okhttp|monitor|uptime", re.I)
UID_RE = re.compile(r"(?:#detail/|/p/)([A-Za-z0-9._-]+?)(?:\.html)?$")
OFFICIAL_SUFFIXES = (".go.th", ".or.th", ".ac.th", ".mi.th")

_SECRET = settings.stats_secret or secrets.token_hex(16)
_last_purge: date | None = None


# ─────────────────────────── 上报 ───────────────────────────

def now_bkk() -> datetime:
    return datetime.now(BKK)


def _clip(v, n: int) -> str:
    return str(v or "").strip()[:n]


def device_of(ua: str) -> str:
    if re.search(r"iPad|Tablet|Nexus (7|9|10)|SM-T", ua):
        return "tablet"
    if re.search(r"Mobi|Android|iPhone|iPod", ua):
        return "mobile"
    return "desktop"


def lang_of(raw) -> str:
    """只留 BCP 47 的「语言-地区」部分:en-US@posix → en-us,乱写的值 → 空。"""
    m = re.match(r"([A-Za-z]{2,3})(?:[-_]([A-Za-z]{4}|[A-Za-z]{2}|\d{3}))?", str(raw or "").strip())
    return "-".join(x for x in m.groups() if x).lower() if m else ""


def visitor_id(day: date, ip: str, ua: str) -> str:
    return hmac.new(_SECRET.encode(), f"{day.isoformat()}|{ip}|{ua}".encode(),
                    hashlib.sha256).hexdigest()[:16]


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def parse_hit(body: bytes, headers, ip: str, at: datetime) -> PageHit | None:
    """把一次上报变成一行记录;任何不合规的输入都返回 None(静默丢弃,不报错)。"""
    ua = headers.get("user-agent", "")
    if not ua or BOT_RE.search(ua):
        return None
    if headers.get("dnt") == "1" or headers.get("sec-gpc") == "1":
        return None
    if len(body) > MAX_BODY:
        return None
    try:
        d = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict):
        return None

    kind = "event" if d.get("k") == "event" else "pv"
    name = _clip(d.get("n"), 32) if kind == "event" else ""
    if kind == "event" and name not in EVENTS:
        return None
    path = _clip(d.get("p"), 255)
    if not path.startswith("/"):
        return None
    value = d.get("v")
    value = int(value) if isinstance(value, (int, float)) and abs(value) < 1e9 else None

    # 站内跳转不算来源:引用页与本站同域就丢掉
    site_hosts = {_host(headers.get("origin", "")), _host(settings.site_url)}
    ref = _host(_clip(d.get("r"), 512))
    if ref in site_hosts:
        ref = ""

    country = ""
    if settings.trust_proxy:        # 只有在可信代理后面才信它给的国家头
        c = headers.get("cf-ipcountry", "")
        country = c.upper() if re.fullmatch(r"[A-Za-z]{2}", c) and c.upper() not in ("XX", "T1") else ""

    day = at.date()
    return PageHit(
        ts=at, day=day, hour=at.hour, kind=kind, name=name, path=path,
        label=_clip(d.get("l"), 160), value=value,
        visitor=visitor_id(day, ip, ua), ref_host=ref[:128],
        utm_source=_clip(d.get("us"), 64).lower(), utm_medium=_clip(d.get("um"), 64).lower(),
        utm_campaign=_clip(d.get("uc"), 64),
        device=device_of(ua),
        lang=lang_of(d.get("lang") or headers.get("accept-language", "").split(",")[0]),
        country=country,
    )


def purge(s: Session, keep_days: int | None = None, today: date | None = None) -> int:
    keep = settings.stats_retention_days if keep_days is None else keep_days
    cutoff = (today or now_bkk().date()) - timedelta(days=keep)
    return s.execute(delete(PageHit).where(PageHit.day < cutoff)).rowcount or 0


@router.post("/t", include_in_schema=False, status_code=204)
async def track(request: Request) -> Response:
    global _last_purge
    if not settings.stats_enabled:
        return Response(status_code=204)
    from .main import _client_ip       # 与限流共用同一套真实 IP 判定
    body = await request.body()
    at = now_bkk()
    hit = parse_hit(body, request.headers, _client_ip(request), at)
    if hit is not None:
        with session_scope() as s:
            s.add(hit)
            if _last_purge != at.date():   # 每天顺手清一次过期记录,不依赖定时器
                from .seo_track import purge_crawls
                n = purge(s, today=at.date()) + purge_crawls(s, today=at.date())
                _last_purge = at.date()
                if n:
                    log.info("统计:清理过期记录 %d 条", n)
    return Response(status_code=204)


# ─────────────────────────── 聚合 ───────────────────────────

def _pct(cur: float, prev: float) -> float | None:
    if not prev:
        return None
    return round((cur - prev) / prev * 100, 1)


def _range(s: Session, start: date, end: date):
    return (PageHit.day >= start) & (PageHit.day <= end)


def _totals(s: Session, start: date, end: date) -> dict:
    rng = _range(s, start, end)
    pv = s.scalar(select(func.count()).where(rng, PageHit.kind == "pv")) or 0
    # 访客按天去重后求和:哈希每天换密钥,跨天去重在设计上就做不到
    daily = select(PageHit.day, func.count(distinct(PageHit.visitor)).label("u")) \
        .where(rng, PageHit.kind == "pv").group_by(PageHit.day).subquery()
    uv = s.scalar(select(func.coalesce(func.sum(daily.c.u), 0))) or 0
    ev = dict(s.execute(select(PageHit.name, func.count()).where(rng, PageHit.kind == "event")
                        .group_by(PageHit.name)).all())
    detail = s.scalar(select(func.count()).where(
        rng, PageHit.kind == "pv",
        (PageHit.path.like("%#detail/%")) | (PageHit.path.like("%/p/%.html")))) or 0
    return {"pv": pv, "uv": int(uv), "pages_per_visitor": round(pv / uv, 2) if uv else 0,
            "detail_views": detail, "searches": ev.get("search", 0),
            "outbound": ev.get("outbound", 0), "tip_opens": ev.get("tip_open", 0),
            "ad_views": ev.get("ad_view", 0), "ad_clicks": ev.get("ad_click", 0)}


def _top(s: Session, col, where, limit: int = 15, with_uv: bool = True) -> list[dict]:
    cols = [col.label("key"), func.count().label("n")]
    if with_uv:
        cols.append(func.count(distinct(PageHit.visitor)).label("uv"))
    rows = s.execute(select(*cols).where(where).group_by(col)
                     .order_by(func.count().desc(), col).limit(limit)).all()
    return [dict(r._mapping) for r in rows]


def report(s: Session, days: int = 30, now: datetime | None = None) -> dict:
    now = now or now_bkk()
    end = now.date()
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    rng = _range(s, start, end)
    pv_rng = rng & (PageHit.kind == "pv")

    cur, prev = _totals(s, start, end), _totals(s, prev_start, prev_end)
    summary = {k: {"value": v, "change_pct": _pct(v, prev.get(k, 0))} for k, v in cur.items()}

    # 按天序列,缺的日子补 0,图上才不会把空档连成一条斜线
    by_day = {r.day: r for r in s.execute(
        select(PageHit.day, func.count().label("pv"), func.count(distinct(PageHit.visitor)).label("uv"))
        .where(pv_rng).group_by(PageHit.day)).all()}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        r = by_day.get(d)
        series.append({"day": d.isoformat(), "pv": r.pv if r else 0, "uv": r.uv if r else 0})

    hours = dict(s.execute(select(PageHit.hour, func.count()).where(pv_rng)
                           .group_by(PageHit.hour)).all())

    # 热门政策:详情视图 #detail/<uid> 与落地页 /p/<uid>.html 合并计数
    pol: dict[str, dict] = {}
    for path, n, uv in s.execute(
            select(PageHit.path, func.count(), func.count(distinct(PageHit.visitor)))
            .where(pv_rng, (PageHit.path.like("%#detail/%")) | (PageHit.path.like("%/p/%.html")))
            .group_by(PageHit.path)).all():
        m = UID_RE.search(path)
        if not m or m.group(1).lower() == "index":
            continue
        key = m.group(1).lower()
        e = pol.setdefault(key, {"n": 0, "uv": 0, "landing": 0})
        e["n"] += n
        e["uv"] += uv
        if "/p/" in path:
            e["landing"] += n
    titles = {uid.lower(): (uid, t) for uid, t in s.execute(select(Document.uid, Document.title_zh)).all()}
    policies = sorted(({"uid": titles.get(k, (k, ""))[0], "title": titles.get(k, ("", ""))[1],
                        **v} for k, v in pol.items()), key=lambda x: (-x["n"], x["uid"]))[:20]

    ev = lambda name: rng & (PageHit.kind == "event") & (PageHit.name == name)  # noqa: E731
    searches = [
        {"q": r.q, "n": r.n, "avg_hits": round(float(r.avg), 1) if r.avg is not None else None,
         "zero": r.zero}
        for r in s.execute(
            select(func.lower(PageHit.label).label("q"), func.count().label("n"),
                   func.avg(PageHit.value).label("avg"),
                   func.sum(case((PageHit.value == 0, 1), else_=0)).label("zero"))
            .where(ev("search"), PageHit.label != "")
            .group_by(func.lower(PageHit.label)).order_by(func.count().desc()).limit(30)).all()]

    outbound = _top(s, PageHit.label, ev("outbound"), 20)
    for o in outbound:
        o["official"] = o["key"].endswith(OFFICIAL_SUFFIXES)

    # 广告:曝光与点击按「槽位|赞助方」对齐算 CTR,续约时给赞助商看的就是这张表
    views = dict(s.execute(select(PageHit.label, func.count()).where(ev("ad_view"))
                           .group_by(PageHit.label)).all())
    clicks = dict(s.execute(select(PageHit.label, func.count()).where(ev("ad_click"))
                            .group_by(PageHit.label)).all())
    ads = []
    for key in sorted(set(views) | set(clicks)):
        slot, _, sponsor = key.partition("|")
        v, c = views.get(key, 0), clicks.get(key, 0)
        ads.append({"slot": slot, "sponsor": sponsor, "views": v, "clicks": c,
                    "ctr": round(c / v * 100, 2) if v else None})
    ads.sort(key=lambda a: (-a["views"], -a["clicks"]))

    tip_open_uv = s.scalar(select(func.count(distinct(PageHit.visitor))).where(ev("tip_open"))) or 0
    tips = {
        "opens": cur["tip_opens"], "open_visitors": tip_open_uv,
        "open_rate_pct": round(tip_open_uv / cur["uv"] * 100, 2) if cur["uv"] else None,
        "by_entry": _top(s, PageHit.label, ev("tip_open"), 10, with_uv=False),
        "amounts": _top(s, PageHit.label, ev("tip_amount"), 10, with_uv=False),
        "links": _top(s, PageHit.label, ev("tip_link"), 10, with_uv=False),
    }

    since = now - timedelta(minutes=30)
    realtime = s.scalar(select(func.count(distinct(PageHit.visitor)))
                        .where(PageHit.ts >= since, PageHit.kind == "pv")) or 0

    return {
        "range": {"days": days, "start": start.isoformat(), "end": end.isoformat(),
                  "prev_start": prev_start.isoformat(), "prev_end": prev_end.isoformat()},
        "generated_at": now.replace(microsecond=0).isoformat(),
        "realtime_visitors_30m": realtime,
        "summary": summary,
        "series": series,
        "hours": [hours.get(h, 0) for h in range(24)],
        "pages": _top(s, PageHit.path, pv_rng, 20),
        "policies": policies,
        "referrers": _top(s, PageHit.ref_host, pv_rng & (PageHit.ref_host != ""), 15),
        "direct_pv": s.scalar(select(func.count()).where(pv_rng, PageHit.ref_host == "")) or 0,
        "campaigns": [dict(r._mapping) for r in s.execute(
            select(PageHit.utm_source.label("source"), PageHit.utm_medium.label("medium"),
                   PageHit.utm_campaign.label("campaign"), func.count().label("n"))
            .where(pv_rng, PageHit.utm_source != "")
            .group_by(PageHit.utm_source, PageHit.utm_medium, PageHit.utm_campaign)
            .order_by(func.count().desc()).limit(15)).all()],
        "searches": searches,
        "zero_result_searches": [x for x in searches if x["zero"]][:15],
        "outbound": outbound,
        "ads": ads,
        "tips": tips,
        "devices": _top(s, PageHit.device, pv_rng, 5),
        "languages": _top(s, PageHit.lang, pv_rng & (PageHit.lang != ""), 10),
        "countries": _top(s, PageHit.country, pv_rng & (PageHit.country != ""), 15),
        "config": {"retention_days": settings.stats_retention_days,
                   "stable_secret": bool(settings.stats_secret)},
    }


# ─────────────────────────── 后台接口 ───────────────────────────

def require_admin(request: Request) -> None:
    token = settings.admin_token
    if not token:          # 没配令牌 = 后台不存在,而不是「谁都能看」
        raise HTTPException(404, "Not Found")
    auth = request.headers.get("authorization", "")
    given = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-admin-token", "")
    if not given or not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(401, "令牌无效", headers={"WWW-Authenticate": "Bearer"})


@router.get("/admin/stats", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_stats(response: Response, days: int = Query(30, ge=1, le=400),
                s: Session = Depends(get_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return report(s, days)


@router.get("/admin/ops", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_ops(response: Response, s: Session = Depends(get_session)) -> dict:
    """采集状态:源健康、运行历史、翻译队列、数据新鲜度。只在后台看,前台不展示。"""
    from . import analytics as A
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return A.ops(s)


@router.get("/admin/runs", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_runs(s: Session = Depends(get_session), limit: int = Query(20, ge=1, le=100)) -> dict:
    from .analytics import iso_bkk
    from .models import CollectRun
    rows = s.scalars(select(CollectRun).order_by(CollectRun.started_at.desc()).limit(limit)).all()
    return {"items": [{"id": r.id, "started_at": iso_bkk(r.started_at),
                       "finished_at": iso_bkk(r.finished_at),
                       "status": r.status, "trigger": r.trigger, "added": r.added,
                       "updated": r.updated, "skipped": r.skipped,
                       "duration_s": round(r.duration_s, 1), "detail": r.detail}
                      for r in rows]}


# ─────────────────────────── 命令行 ───────────────────────────

def _fmt_change(x: dict) -> str:
    c = x["change_pct"]
    return "" if c is None else f"({'+' if c >= 0 else ''}{c}%)"


def text_report(r: dict) -> str:
    sm = r["summary"]
    out = [f"站点统计 {r['range']['start']} ~ {r['range']['end']}(对比上一个 {r['range']['days']} 天)",
           f"  浏览量 {sm['pv']['value']} {_fmt_change(sm['pv'])} · 访客 {sm['uv']['value']} "
           f"{_fmt_change(sm['uv'])} · 人均 {sm['pages_per_visitor']['value']} 页",
           f"  政策阅读 {sm['detail_views']['value']} · 检索 {sm['searches']['value']} · "
           f"外链 {sm['outbound']['value']} · 打赏弹窗 {sm['tip_opens']['value']} · "
           f"广告 {sm['ad_clicks']['value']}/{sm['ad_views']['value']}(点击/曝光)",
           f"  最近 30 分钟在线 {r['realtime_visitors_30m']}"]
    sections = [("热门政策", [(p["uid"], p["title"], p["n"]) for p in r["policies"][:10]]),
                ("来源", [(x["key"], "", x["n"]) for x in r["referrers"][:10]]),
                ("检索词", [(x["q"], "零结果" if x["zero"] else "", x["n"]) for x in r["searches"][:10]])]
    for title, rows in sections:
        if rows:
            out.append(f"\n{title}")
            out += [f"  {n:>5}  {a}  {b}".rstrip() for a, b, n in rows]
    return "\n".join(out)


def main() -> None:
    from .db import init_db
    ap = argparse.ArgumentParser(description="站点统计报告 / 清理")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--purge", action="store_true", help=f"删除 {settings.stats_retention_days} 天前的记录")
    args = ap.parse_args()
    init_db()
    with session_scope() as s:
        if args.purge:
            print(f"已删除 {purge(s)} 条过期记录")
            return
        r = report(s, args.days)
    print(json.dumps(r, ensure_ascii=False, indent=1) if args.json else text_report(r))


if __name__ == "__main__":
    main()
