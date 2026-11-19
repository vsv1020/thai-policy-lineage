# -*- coding: utf-8 -*-
"""数据库列宽:SQLite 不检查 VARCHAR(n),PostgreSQL 会拒收。

2026-11-19 的事故:runs.jsonl 里一条 trigger 是 backfill-topic:land-use(23 个字符),collect_runs.trigger
是 VARCHAR(16)。测试与 CI 跑 SQLite 全绿,生产环境 PostgreSQL 在启动时的 ingest 里拒收,容器反复重启、
整站下线。这里锁住两件事:运行记录的自由文本会截到列宽;其余超长写入在 SQLite 上也会报错。"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import delete, select

from app.config import BKK
from app.db import session_scope
from app.models import CollectRun, Domain


def test_long_run_trigger_is_clipped_to_column_width():
    trigger = "backfill-topic:industrial-standards"
    with session_scope() as s:
        s.add(CollectRun(started_at=datetime(2026, 11, 19, 8, 48, tzinfo=BKK), status="ok", trigger=trigger))
    with session_scope() as s:
        run = s.scalars(select(CollectRun).where(CollectRun.trigger.like("backfill-topic%"))).one()
        width = CollectRun.__table__.c.trigger.type.length
        assert run.trigger == trigger[:width] and len(run.trigger) == width
        s.execute(delete(CollectRun).where(CollectRun.id == run.id))


def test_overlong_value_fails_on_sqlite_like_postgres():
    width = Domain.__table__.c.chip.type.length
    with pytest.raises(ValueError, match="超过列宽"):
        with session_scope() as s:
            s.add(Domain(id="zz-test", zh="测试", th="", en="", chip="x" * (width + 1)))


def test_real_run_history_loads(tmp_path):
    """仓库里真实的 runs.jsonl 整表载入不报错(事故里就是这一步失败)。"""
    from app.config import DATA_DIR
    from app.ingest import load_runs, read_jsonl
    records = read_jsonl(DATA_DIR / "policies" / "runs.jsonl")
    assert records
    with session_scope() as s:
        assert load_runs(s, records) == len(records)
        s.rollback()
