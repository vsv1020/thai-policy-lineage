# -*- coding: utf-8 -*-
"""测试用临时数据库。

必须在 import app.* 之前设好 DATABASE_URL —— app.db 在模块级建 engine。
conftest 比测试模块先加载,所以放在这里是安全的。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="policy-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
# 固定样例数据:真实数据每天被采集改写,不适合当测试基准
os.environ["POLICIES_DIR"] = str(Path(__file__).resolve().parent / "fixtures" / "policies")
os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["EXPORT_AFTER_COLLECT"] = "0"

import pytest  # noqa: E402

from app.db import init_db, session_scope  # noqa: E402
from app.ingest import ingest_all  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    ingest_all(reset=True)
    yield


@pytest.fixture()
def session():
    with session_scope() as s:
        yield s
