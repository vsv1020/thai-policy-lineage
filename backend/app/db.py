# -*- coding: utf-8 -*-
"""引擎与 Session。SQLite 下额外打开外键约束(默认是关的,不开等于没有词表约束)。"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapper, Session, sessionmaker

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


def _check_lengths(mapper: Mapper, _conn, target) -> None:
    """SQLite 不检查 VARCHAR(n) 的长度,PostgreSQL 会直接拒收整批写入。开发、测试与 CI 都跑 SQLite,
    所以在这里替 PostgreSQL 把关:超长就报错,让问题在 CI 里暴露,而不是在生产环境启动时才把整站拖垮
    (2026-11-19 的事故:collect_runs.trigger 写入 23 个字符,上限 16)。"""
    for prop in mapper.column_attrs:
        col = prop.columns[0]
        if isinstance(col.type, String) and col.type.length:
            v = getattr(target, prop.key, None)
            if isinstance(v, str) and len(v) > col.type.length:
                raise ValueError(f"{mapper.class_.__name__}.{prop.key} 有 {len(v)} 个字符,超过列宽 "
                                 f"{col.type.length}(PostgreSQL 会拒收):{v[:60]!r}")


if engine.dialect.name == "sqlite":
    event.listen(Base, "before_insert", _check_lengths, propagate=True)
    event.listen(Base, "before_update", _check_lengths, propagate=True)


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
