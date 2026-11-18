# -*- coding: utf-8 -*-
"""应用入口:建表 → 装 API → 起定时器 → 挂静态站。

静态站只按白名单暴露 —— 早期版本把整个仓库根目录挂在 / 上,
.git/、数据库文件、源码、以及生产机上的 backend/.env 都能被直接下载。
新增公开目录必须显式加进 PUBLIC_DIRS,不要改回挂根目录。
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import router
from .stats import router as stats_router
from .seo_track import classify_bot, record_crawl, router as seo_router
from .config import REPO_ROOT, SITE_DIR, settings
from .db import init_db

log = logging.getLogger("policy")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

# 对外公开的目录:URL 前缀 → 磁盘目录。只有这些能被访问。
PUBLIC_DIRS = {
    "/css": REPO_ROOT / "css",
    "/js": REPO_ROOT / "js",
    "/data/site": SITE_DIR,
    "/p": REPO_ROOT / "p",          # 每条政策的静态落地页(SEO),由 app.export 生成
    "/assets": REPO_ROOT / "assets",  # 打赏收款码等静态图片
    "/feed": REPO_ROOT / "feed",      # 按领域的 Atom 订阅,由 app.export 生成
    "/zh-hant": REPO_ROOT / "zh-hant",  # 繁体版静态页(镜像简体结构),由 app.export 生成
}
# 根目录下允许单独访问的文件
PUBLIC_FILES = {"index.html", "privacy.html", "about.html", "robots.txt", "sitemap.xml", "favicon.ico", "favicon.svg",
                "ads.txt", "feed.xml", "llms.txt", "llms-full.txt"}

def _indexnow_file() -> str:
    """config/seo.json 里的 IndexNow key → 站点根目录的 <key>.txt(搜索引擎用它核验提交者)。"""
    import json
    import re
    try:
        key = json.loads((REPO_ROOT / "config" / "seo.json").read_text(encoding="utf-8")).get("indexnow_key", "")
    except (OSError, ValueError):
        return ""
    return f"{key}.txt" if re.fullmatch(r"[A-Za-z0-9-]{8,128}", key or "") else ""


INDEXNOW_KEY_FILE = _indexnow_file()

# 静态内容的浏览器缓存(秒):URL 前缀 → 有效期。文件名不带指纹,所以都设得短,过期后凭 ETag 复核(没变就是 304)。
# 不设的话浏览器按「距上次修改时间的 10%」自己估:久未改动的脚本可能被缓存好几天,发版后旧脚本迟迟不换;
# 而每次都重新请求样式表又拖慢回访者的首屏。派生数据 /data/site/ 在下面的中间件里单独处理
CACHE_SECONDS = (("/css/", 3600), ("/js/", 3600), ("/assets/", 86400), ("/p/", 600), ("/feed/", 600),
                 ("/zh-hant/", 600))
ROOT_CACHE_SECONDS = 300      # 首页与根目录下的 html / xml / txt
# 页面类地址的 404 用这一页(app.export 生成);接口与数据文件的 404 仍是 JSON
NOT_FOUND_PAGE = REPO_ROOT / "p" / "404.html"
NOT_FOUND_PAGE_HANT = REPO_ROOT / "zh-hant" / "404.html"     # /zh-hant/ 下的地址用繁体的 404 页

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = None
    if settings.enable_scheduler:
        from .scheduler import start_scheduler
        scheduler = start_scheduler()
    else:
        log.info("定时器已关闭(ENABLE_SCHEDULER=0),采集只能手动或由外部 cron 触发")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="政策脉络 · 泰国 API",
    description="泰国政策的中文结构化数据与分析接口。译文为非官方翻译,以泰文原文为准。",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],   # POST 只有统计上报 /api/t
    allow_headers=["*"],
)

# ── 限流:每个客户端 IP 每分钟最多 API_RATE_PER_MIN 次 /api 请求 ──
# 进程内实现,单实例够用;多实例部署时放到反向代理(Caddy/nginx)上做。
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and settings.api_rate_per_min > 0:
        now = time.monotonic()
        q = _hits[_client_ip(request)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.api_rate_per_min:
            return JSONResponse({"detail": "请求过于频繁,请稍后再试"}, status_code=429,
                                headers={"Retry-After": "60"})
        q.append(now)
    response = await call_next(request)
    # 搜索引擎 / AI 爬虫的抓取记录(不跑 JS,前端统计看不到);只识别已知爬虫,普通访问零开销
    ua = request.headers.get("user-agent", "")
    if request.method in ("GET", "HEAD") and classify_bot(ua):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(record_crawl, ua, request.url.path, response.status_code)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    path = request.url.path
    if path.startswith("/data/site/"):
        # 派生数据每天更新一次,短缓存即可;API 不缓存
        response.headers.setdefault("Cache-Control", "public, max-age=300")
    elif response.status_code == 200 and request.method in ("GET", "HEAD"):
        ttl = next((t for prefix, t in CACHE_SECONDS if path.startswith(prefix)), None)
        if ttl is None and (path == "/" or (path.count("/") == 1 and path.endswith((".html", ".xml", ".txt", ".svg")))):
            ttl = ROOT_CACHE_SECONDS
        if ttl:        # 后台页自己设了 no-store,setdefault 不会覆盖它
            response.headers.setdefault("Cache-Control", f"public, max-age={ttl}")
    return response


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, exc: StarletteHTTPException):
    """页面类地址(.html、目录、无后缀)的 404 给一张带导航的 HTML 页,状态码仍是 404:
    从搜索结果点进已下线页面的人能接着找,而不是看到一行 {"detail":"Not Found"}。"""
    path = request.url.path
    page_like = path.endswith((".html", "/")) or "." not in path.rsplit("/", 1)[-1]
    page = NOT_FOUND_PAGE_HANT if path.startswith("/zh-hant/") and NOT_FOUND_PAGE_HANT.is_file() else NOT_FOUND_PAGE
    if (exc.status_code == 404 and page_like and not path.startswith(settings.api_prefix + "/")
            and page.is_file()):
        return FileResponse(page, status_code=404, headers={"X-Robots-Tag": "noindex"})
    return await http_exception_handler(request, exc)


app.include_router(router)
app.include_router(stats_router)
app.include_router(seo_router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(REPO_ROOT / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    """统计后台页面。页面本身不含数据,数据接口 /api/admin/stats 另需 ADMIN_TOKEN。"""
    return FileResponse(REPO_ROOT / "admin.html",
                        headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


# 爬虫按惯例会探测的地址:给它们指到真实文件,而不是在抓取报告里留一串 404
# (/favicon.ico 是浏览器与 Google 的默认图标地址;/feed 是 WordPress 等博客的订阅地址)
# /zh-hant 不带斜杠时会先被下面的 /{name} 接住(返回 404),这里显式 301 到繁体首页
CONVENTIONAL_REDIRECTS = {"/favicon.ico": "/favicon.svg", "/zh-hant": "/zh-hant/",
                          "/feed": "/feed.xml", "/feed/": "/feed.xml",
                          "/rss": "/feed.xml", "/rss.xml": "/feed.xml", "/atom.xml": "/feed.xml"}


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/zh-hant", include_in_schema=False)
@app.get("/feed", include_in_schema=False)
@app.get("/feed/", include_in_schema=False)
@app.get("/rss", include_in_schema=False)
@app.get("/rss.xml", include_in_schema=False)
@app.get("/atom.xml", include_in_schema=False)
def conventional_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(CONVENTIONAL_REDIRECTS[request.url.path], status_code=301)


@app.get("/comments/feed/", include_in_schema=False)
@app.get("/comments/feed", include_in_schema=False)
def gone() -> PlainTextResponse:
    """本站没有评论订阅;410 告诉爬虫「永久没有」,比 404 更快停止重试。"""
    return PlainTextResponse("Gone", status_code=410)


@app.get("/{name}", include_in_schema=False)
def root_file(name: str):
    path = REPO_ROOT / name
    if name in PUBLIC_FILES and path.is_file():
        return FileResponse(path)
    if name == INDEXNOW_KEY_FILE:    # IndexNow 核验文件:内容就是 key 本身
        return PlainTextResponse(INDEXNOW_KEY_FILE[:-4])
    if name == "robots.txt":        # 没生成过也给一个合理默认
        return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\n")
    raise HTTPException(status_code=404)


for prefix, directory in PUBLIC_DIRS.items():
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(prefix, StaticFiles(directory=str(directory), html=True),
              name=prefix.strip("/").replace("/", "_"))
