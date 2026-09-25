# -*- coding: utf-8 -*-
"""上线阻断项的回归测试:静态挂载只能暴露白名单内的东西。

早期版本把仓库根目录整个挂在 / 上,.git/、数据库、源码、.env 都能被直接下载。
这组测试确保它不会再回来。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", [
    "/.git/config", "/.git/HEAD",
    "/var/policy.db",
    "/backend/app/config.py", "/backend/.env", "/backend/.env.example",
    "/data/policies/documents.jsonl", "/data/vocab.json",
    "/docs/research-report.md", "/docker-compose.yml",
    "/css/../backend/app/config.py", "/data/site/../policies/sources.json",
    "/config/ads.json", "/config/support.json", "/config/analytics.json", "/admin.html", "/assets/../config/support.json",
])
def test_private_paths_are_not_served(client, path):
    r = client.get(path)
    assert r.status_code == 404, f"{path} 不应可访问,实际 {r.status_code}"


@pytest.mark.parametrize("path", ["/", "/index.html", "/privacy.html", "/css/main.css", "/js/api.js",
                                  "/js/vendor/qrcode-generator-1.4.4.js", "/js/promptpay.js",
                                  "/data/site/policies.json", "/data/site/support.json",
                                  "/data/site/analytics.json", "/js/track.js", "/admin",
                                  "/robots.txt"])
def test_public_paths_are_served(client, path):
    assert client.get(path).status_code == 200


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" in r.headers


def test_robots_blocks_api(client):
    assert "Disallow: /api/" in client.get("/robots.txt").text
