# -*- coding: utf-8 -*-
"""应用入口:建表 → 装 API → 起定时器 → 顺带把原型静态站挂在 / 上。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import REPO_ROOT, settings
from .db import init_db

log = logging.getLogger("policy")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


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
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)

# 把仓库根目录当静态站挂上 —— 一个进程既是 API 也是站点,部署只需要一个服务。
# 放在最后,避免 /api/* 被静态路由吃掉。
app.mount("/", StaticFiles(directory=str(REPO_ROOT), html=True), name="site")
