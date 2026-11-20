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


def test_overlong_document_title_is_clipped_not_rejected():
    """2026-11-20:内阁决议 TH-CABX-20250318-2 的泰文标题 1420 个字符,documents.title_th 是 VARCHAR(512)。
    翻译上线后入库,SQLite 的长度检查会让采集失败、PostgreSQL 会让整站启动失败。现在截到列宽并加省略号。"""
    from app.models import Document
    width = Document.__table__.c.title_th.type.length
    title = "มติคณะรัฐมนตรี " * 120
    with session_scope() as s:
        doc = Document(uid="TH-CABX-20250318-ZZTEST", title_zh="测试", title_th=title,
                       legal_form_id="resolution", status_id="pending_gazette")
        assert len(doc.title_th) == width and doc.title_th.endswith("…")
        assert doc.title_th[:-1] == title[:width - 1]
        assert Document(uid="x", title_zh="短标题", title_th="ประกาศ").title_th == "ประกาศ"
        s.rollback()


def test_every_record_in_the_fact_layer_fits_after_translation():
    """事实层全部记录(含尚未翻译、还不入库的)按「已翻译」载入数据库,不超过任何列宽。"""
    import json
    from app.config import REPO_ROOT
    from app.ingest import load_documents, read_jsonl
    rows = read_jsonl(REPO_ROOT / "data" / "policies" / "documents.jsonl")      # 仓库真实数据,不是测试夹具
    assert any(len((r.get("titles") or {}).get("th", "")) > 512 for r in rows), "样本里应有超长泰文标题"
    filled = []
    for r in rows:
        r = json.loads(json.dumps(r))
        r["titles"]["zh"] = r["titles"].get("zh") or "待译"
        r.setdefault("flags", {}).pop("skip", None)
        filled.append(r)
    with session_scope() as s:
        load_documents(s, filled)
        s.flush()
        s.rollback()
