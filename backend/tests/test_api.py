# -*- coding: utf-8 -*-
"""API 层:分面检索、单件详情、降级契约。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router


@pytest.fixture(scope="module")
def client():
    # 只装 router,不走 main.py 的 lifespan(不需要定时器和静态挂载)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["documents"] >= 12


def test_overview_shape_matches_static_export(client):
    """API 与静态文件必须同形状 —— 前端只有一份渲染代码。"""
    d = client.get("/api/overview").json()
    assert "sources" not in d, "采集状态只在后台可见"
    for key in ("updated_at", "stats", "wind", "calendar", "policies"):
        assert key in d
    p = d["policies"][0]
    for key in ("uid", "date", "domain", "domain_label", "direction", "title_zh",
                "summary_zh", "org", "status", "status_label", "verified", "featured"):
        assert key in p


def test_pending_gazette_filter(client):
    """这是这套数据模型最有价值的查询:决议已过、公报未刊的窗口期。"""
    d = client.get("/api/documents", params={"pending_gazette": True}).json()
    assert d["total"] >= 1
    for i in d["items"]:
        assert i["status_label"] == "待刊公报"


def test_facet_filters_combine(client):
    d = client.get("/api/documents", params={"domain": "visa", "direction": "tight"}).json()
    assert d["total"] >= 1
    for i in d["items"]:
        assert i["direction"] == "tight"


def test_keyword_search_matches_thai_text(client):
    """中文搜译文、泰文搜原文/文号 —— 双语检索是产品承诺。"""
    zh = client.get("/api/documents", params={"q": "最低工资"}).json()
    assert zh["total"] >= 1
    th = client.get("/api/documents", params={"q": "ประกาศคณะกรรมการค่าจ้าง"}).json()
    assert th["total"] >= 1, "泰文文号应可检索"


def test_pagination(client):
    a = client.get("/api/documents", params={"limit": 5, "offset": 0}).json()
    b = client.get("/api/documents", params={"limit": 5, "offset": 5}).json()
    assert a["total"] == b["total"]
    assert {i["uid"] for i in a["items"]}.isdisjoint({i["uid"] for i in b["items"]})


def test_document_detail_exposes_all_dates(client):
    """四类日期各自独立可读 —— 决议日与刊登日不是同一件事。"""
    d = client.get("/api/documents/TH-MOL-20250701-MINWAGE-14").json()
    assert d["dates"]["resolved_at"] == "2025-06-17"
    assert d["dates"]["published_at"] == "2025-07-01"
    assert d["dates"]["effective_from"] == "2025-07-01"
    assert d["confidence"]["doc_no"] in ("high", "med", "low", "none")


def test_document_detail_exposes_relations(client):
    d = client.get("/api/documents/TH-RD-2565-DECREE-743").json()
    assert any(r["type"] == "implemented_by" for r in d["relations"])
    assert d["instruments"] and d["goals"]
    assert d["implementation_stage"]


def test_document_404(client):
    assert client.get("/api/documents/TH-NOPE-1-X").status_code == 404


def test_invalid_direction_rejected(client):
    assert client.get("/api/documents", params={"direction": "sideways"}).status_code == 422


def test_limit_bounds_enforced(client):
    assert client.get("/api/documents", params={"limit": 9999}).status_code == 422


def test_dimensions_all_seven_present(client):
    d = client.get("/api/dimensions").json()
    for i in range(1, 8):
        assert any(k.startswith(f"dim{i}_") for k in d), f"缺维度 {i}"


def test_dimensions_carry_sample_size(client):
    """每个统计型维度都要能自证样本量,否则读者无法判断结论可信度。"""
    d = client.get("/api/dimensions").json()
    for key, v in d.items():
        if key == "scope" or key == "dim6_conflicts":
            continue
        assert "n" in v and "sufficient" in v, f"{key} 缺样本量标注"


def test_vocab_endpoint(client):
    d = client.get("/api/vocab").json()
    assert len(d["domains"]) >= 10
    forms = d["legal_forms"]
    assert forms == sorted(forms, key=lambda f: -f["stability"])


def test_collection_status_is_admin_only(client, monkeypatch):
    """采集状态只在后台:公开接口不再暴露运行历史与数据源状态。"""
    from app.config import settings
    assert client.get("/api/runs").status_code == 404
    assert client.get("/api/ops").status_code == 404
    assert "last_run" not in client.get("/api/health").json()
    monkeypatch.setattr(settings, "admin_token", "t0ken-for-tests")
    from app.main import app as full_app          # 后台接口挂在完整应用上
    client = TestClient(full_app)
    assert client.get("/api/admin/ops").status_code == 401
    auth = {"authorization": "Bearer t0ken-for-tests"}
    ops = client.get("/api/admin/ops", headers=auth)
    assert ops.status_code == 200 and {"health", "sources", "runs", "corpus"} <= set(ops.json())
    assert "items" in client.get("/api/admin/runs", headers=auth).json()
