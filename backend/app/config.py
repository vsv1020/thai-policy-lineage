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
    # 每个客户端 IP 每分钟 /api 请求上限;0 = 关闭(交给反向代理做)
    api_rate_per_min: int = int(os.getenv("API_RATE_PER_MIN", "120"))
    # 在 Caddy/nginx 后面时设 1,才会用 X-Forwarded-For 识别真实 IP;
    # 直接暴露在公网时必须为 0,否则客户端可伪造 IP 绕过限流
    trust_proxy: bool = _bool("TRUST_PROXY", False)

    # LLM 翻译分类(app.enrich)。两家都没配 key 时自动跳过
    # 服务商:deepseek / anthropic;留空 = 自动(配了 DEEPSEEK_API_KEY 用 DeepSeek,否则 Claude)
    enrich_provider: str = os.getenv("ENRICH_PROVIDER", "").strip().lower()
    # 模型名;留空 = 按服务商取默认(deepseek-chat / claude-opus-5)
    enrich_model_override: str = os.getenv("ENRICH_MODEL", "").strip()
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    enrich_max_per_run: int = int(os.getenv("ENRICH_MAX_PER_RUN", "40"))
    enrich_after_collect: bool = _bool("ENRICH_AFTER_COLLECT", True)

    # 站点公开地址(用于 sitemap 与 SEO 落地页的 canonical 链接)
    site_url: str = os.getenv("SITE_URL", "https://vsv1020.github.io/thai-policy-lineage").rstrip("/")

    # 站点统计(第一方、无 Cookie、不存 IP,见 app/stats.py)
    stats_enabled: bool = _bool("STATS_ENABLED", True)
    # 统计后台 /admin 的访问令牌;不设则后台接口一律 404。生成:openssl rand -hex 24
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    # 访客哈希的密钥。不设则每次进程启动随机生成 —— 重启当天的访客数会重复计一次
    stats_secret: str = os.getenv("STATS_SECRET", "")
    stats_retention_days: int = int(os.getenv("STATS_RETENTION_DAYS", "400"))

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
