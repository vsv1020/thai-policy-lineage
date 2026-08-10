# -*- coding: utf-8 -*-
"""运行配置,全部走环境变量 —— 部署时只需要一个 .env。"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

BKK = timezone(timedelta(hours=7))

# backend/app/config.py → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
POLICIES_DIR = DATA_DIR / "policies"
SITE_DIR = DATA_DIR / "site"


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # SQLite 默认落在仓库外的 var/ 目录;生产换成
    # postgresql+psycopg://user:pass@host/dbname 即可,模型完全通用
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'var' / 'policy.db'}")
    echo_sql: bool = _bool("ECHO_SQL", False)

    # 采集
    collect_cron_hour: int = int(os.getenv("COLLECT_HOUR", "7"))     # 曼谷时间每天几点
    collect_cron_minute: int = int(os.getenv("COLLECT_MINUTE", "23"))
    enable_scheduler: bool = _bool("ENABLE_SCHEDULER", True)
    recency_days: int = int(os.getenv("RECENCY_DAYS", "7"))          # 只收多久之内的信号
    http_timeout: int = int(os.getenv("HTTP_TIMEOUT", "30"))
    min_request_interval: float = float(os.getenv("MIN_REQUEST_INTERVAL", "1.0"))

    # 采集后是否把 DB 导出成静态 JSON(给 GitHub Pages 降级用)
    export_after_collect: bool = _bool("EXPORT_AFTER_COLLECT", True)

    # API
    cors_origins: list[str] = [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,https://vsv1020.github.io"
        ).split(",") if o.strip()
    ]
    api_prefix: str = os.getenv("API_PREFIX", "/api")

    # 分析参数(与前端展示口径一致,改这里就改了全站)
    wind_shrink: float = float(os.getenv("WIND_SHRINK", "2.0"))
    trend_months: int = int(os.getenv("TREND_MONTHS", "12"))
    min_trend_months: int = int(os.getenv("MIN_TREND_MONTHS", "6"))
    calendar_days: int = int(os.getenv("CALENDAR_DAYS", "90"))
    feed_size: int = int(os.getenv("FEED_SIZE", "6"))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()

CONF_WEIGHT = {"high": 1.0, "med": 0.7, "low": 0.4, "none": 0.2}
