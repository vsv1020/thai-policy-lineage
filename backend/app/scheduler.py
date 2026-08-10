# -*- coding: utf-8 -*-
"""每天一次的定时采集(APScheduler,进程内)。

时区固定 Asia/Bangkok:泰国公报的刊登与生效都按当地日界计算,用 UTC 会让
「今天刊登」在跨日时段错位一天。

如果更想用系统 cron / systemd timer(进程崩了也不会漏跑),把 ENABLE_SCHEDULER=0,
然后 `cd backend && python3 -m app.collect --trigger schedule`,见 backend/README.md。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import BKK, settings

log = logging.getLogger("policy.scheduler")


def _job() -> None:
    from .collect import run_collection
    try:
        out = run_collection(trigger="schedule")
        log.info("定时采集结束: %s", out)
    except Exception:                      # 定时任务里绝不能让异常逃出去杀掉调度器
        log.exception("定时采集失败,下一次仍会照常触发")


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=BKK)
    sched.add_job(
        _job,
        CronTrigger(hour=settings.collect_cron_hour, minute=settings.collect_cron_minute,
                    timezone=BKK),
        id="daily_collect",
        # 进程重启错过了触发点,1 小时内补跑一次;不合并堆积的多次触发
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    sched.start()
    log.info("定时采集已启动:每天 %02d:%02d(曼谷时间)",
             settings.collect_cron_hour, settings.collect_cron_minute)
    return sched
