# -*- coding: utf-8 -*-
"""SEO 落地页:每条可呈现政策一页、无需 JS 可读、不泄露内部字段、导出可重复。"""
from __future__ import annotations

import json
import re

import pytest

from app import seo


@pytest.fixture(scope="module")
def built(tmp_path_factory, monkeypatch_module):
    root = tmp_path_factory.mktemp("site")
    (root / "config").mkdir()
    (root / "config" / "ads.json").write_text(json.dumps(
        {"enabled": False, "adsense": {"client": "ca-pub-123"}}), encoding="utf-8")
    site = root / "data" / "site"; site.mkdir(parents=True)
    monkeypatch_module.setattr(seo, "PAGES_DIR", root / "p")
    monkeypatch_module.setattr(seo, "REPO_ROOT", root)
    monkeypatch_module.setattr(seo, "SITE_DIR", site)
    monkeypatch_module.setattr(seo, "ADS_CONFIG", root / "config" / "ads.json")
    from app.db import session_scope
    with session_scope() as s:
        stats = seo.build(s)
    return root, stats


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_one_page_per_presentable_document(built, session):
    from sqlalchemy import func, select
    from app.models import Document
    root, stats = built
    n = session.scalar(select(func.count(Document.uid)))
    pages = [p for p in (root / "p").glob("*.html") if p.name != "index.html"]
    assert len(pages) == n


def test_page_readable_without_js(built):
    """爬虫不跑 JS:标题、摘要、免责声明都必须直接在 HTML 里。"""
    root, _ = built
    html = (root / "p" / "th-mol-20250701-minwage-14.html").read_text(encoding="utf-8")
    assert "400 泰铢" in html
    assert "非官方翻译" in html
    assert 'rel="canonical"' in html
    assert '"@type": "Legislation"' in html


def test_pages_never_claim_unverified_as_verified(built):
    root, _ = built
    for p in (root / "p").glob("th-*.html"):
        t = p.read_text(encoding="utf-8")
        assert "未经人工复核" in t or "已人工复核" in t


def test_sitemap_lists_every_page(built):
    root, stats = built
    sm = (root / "sitemap.xml").read_text(encoding="utf-8")
    assert sm.count("<url>") == stats["sitemap_urls"]
    assert "/api/" not in sm


def test_robots_points_to_sitemap(built):
    root, _ = built
    assert "Sitemap:" in (root / "robots.txt").read_text(encoding="utf-8")


def test_ads_txt_only_with_adsense_client(built):
    root, _ = built
    assert (root / "ads.txt").read_text().startswith("google.com, pub-123, DIRECT")


def test_no_internal_fields_leak(built):
    """落地页是公开的:不能带出 note 以外的内部运维字段。"""
    root, _ = built
    for p in (root / "p").glob("*.html"):
        t = p.read_text(encoding="utf-8")
        assert "enriched_by" not in t and "run_at" not in t
        assert not re.search(r"sk-ant-", t)


def test_build_is_reproducible(built):
    root, _ = built
    before = {p.name: p.read_bytes() for p in (root / "p").glob("*.html")}
    from app.db import session_scope
    with session_scope() as s:
        seo.build(s)
    after = {p.name: p.read_bytes() for p in (root / "p").glob("*.html")}
    assert before == after, "同样的数据两次导出必须逐字节一致,否则 CI 漂移检查会误报"
