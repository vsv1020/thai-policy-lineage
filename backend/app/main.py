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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

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
}
# 根目录下允许单独访问的文件
PUBLIC_FILES = {"index.html", "privacy.html", "robots.txt", "sitemap.xml", "favicon.ico", "favicon.svg",
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
    if request.url.path.startswith("/data/site/"):
        # 派生数据每天更新一次,短缓存即可;API 不缓存
        response.headers.setdefault("Cache-Control", "public, max-age=300")
    return response


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


@app.get("/{name}", include_in_schema=False)
def root_file(name: str):
    path = REPO_ROOT / name
    if name in PUBLIC_FILES and path.is_file():
        return FileResponse(path)
    if name == INDEXNOW_KEY_FILE:    # IndexNow 核验文件:内容就是 key 本身
        return PlainTextResponse(INDEXNOW_KEY_FILE[:-4])
    if name == "robots.txt":        # 没生成过也给一个合理默认
        return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\n")
    return JSONResponse({"detail": "Not Found"}, status_code=404)


for prefix, directory in PUBLIC_DIRS.items():
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(prefix, StaticFiles(directory=str(directory), html=True),
              name=prefix.strip("/").replace("/", "_"))
