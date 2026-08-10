# -*- coding: utf-8 -*-
"""引擎与 Session。SQLite 下额外打开外键约束(默认是关的,不开等于没有词表约束)。"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import REPO_ROOT, settings
from .models import Base


def _make_engine() -> Engine:
    url = settings.database_url
    kwargs: dict = {"echo": settings.echo_sql, "future": True}
    if url.startswith("sqlite"):
        (REPO_ROOT / "var").mkdir(exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - 由驱动触发
    if engine.dialect.name != "sqlite":
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")   # 不开的话词表外键形同虚设
    cur.execute("PRAGMA journal_mode=WAL")  # 采集写入与 API 读取并发
    cur.close()


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session]:
    """FastAPI 依赖。"""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
