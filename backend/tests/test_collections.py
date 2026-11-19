# -*- coding: utf-8 -*-
"""专题汇总页:只汇编已收录条目、逐条附官方原文、不写综述;命中太少不生成。"""
from __future__ import annotations

import json
import re

import pytest

from app import seo


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("coll")
    (root / "data" / "site").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "topics.json").write_text(json.dumps({"topics": [
        {"id": "wage", "title_zh": "最低工资", "scope_zh": "收录标题涉及工资的公报。",
         "match": {"title_keywords": ["工资"]}},
        {"id": "nothing", "title_zh": "不存在", "scope_zh": "测试。", "match": {"title_keywords": ["绝对不会命中的词"]}},
    ]}, ensure_ascii=False), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    mp.setattr(seo, "TOPICS_CONFIG", root / "config" / "topics.json")
    mp.setattr(seo, "MIN_COLLECTION", 1)
    from app.db import session_scope
    with session_scope() as s:
        seo.build(s)
    yield root
    mp.undo()


def test_topic_page_lists_only_matching_items_with_official_links(site):
    html = (site / "p" / "t" / "wage.html").read_text(encoding="utf-8")
    titles = re.findall(r'<h2 class="coll-title">(?:<span[^>]*>[^<]*</span> )?<a [^>]*>([^<]+)</a>', html)
    assert titles and all("工资" in t for t in titles)
    assert html.count("泰文原文 ↗") == len(titles), "每一条都要附官方原文"
    assert "一切以泰文原文为准" in html and '"@type": "CollectionPage"' in html
    assert not (site / "p" / "t" / "nothing.html").exists(), "没有命中的专题不生成"


def test_who_pages_and_index_links(site):
    coll = json.loads((site / "data" / "site" / "collections.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in coll["topics"]] == ["wage"]
    assert coll["who"], "有影响对象标注的条目时生成影响对象页"
    who = coll["who"][0]
    html = (site / who["href"]).read_text(encoding="utf-8")
    assert f"影响「{who['zh']}」的泰国政策" in html
    idx = (site / "p" / "index.html").read_text(encoding="utf-8")
    assert 'href="t/wage.html"' in idx and f'href="{who["href"][2:]}"' in idx
    sm = (site / "sitemap.xml").read_text(encoding="utf-8")
    assert "/p/t/wage.html" in sm and f"/{who['href']}" in sm


def test_topic_matching_rules():
    x = {"uid": "U1", "title": "关于进口配额", "domain_id": "customs", "parties": [{"id": "importer", "stance": "constrain"}]}
    assert seo.topic_matches(x, {"title_keywords": ["配额"]})
    assert not seo.topic_matches(x, {"title_keywords": ["配额"], "domains": ["tax"]})
    assert seo.topic_matches(x, {"uids": ["U1"], "parties": ["importer"]})
    assert not seo.topic_matches(x, {"title_keywords": ["土地"]})


def test_configured_topics_are_well_formed():
    """config/topics.json:每个专题有 id、名称、只描述范围的 scope_zh;不用会大面积误收的单字关键词。"""
    import re
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parents[2] / "config" / "topics.json").read_text(encoding="utf-8"))
    ids = [t["id"] for t in cfg["topics"]]
    assert len(ids) == len(set(ids))
    for want in ("income-tax", "ev-auto", "industrial-standards", "energy", "environment"):
        assert want in ids, want
    for t in cfg["topics"]:
        assert re.fullmatch(r"[a-z0-9-]+", t["id"]) and t["title_zh"] and t["scope_zh"].startswith("收录")
        kws = t["match"].get("title_keywords") or []
        assert kws and all(len(k) >= 2 for k in kws), (t["id"], "单字关键词(如「碳」)会误收")
        assert not re.search(r"利好|严格|宽松|重大|应当|建议", t["scope_zh"]), "scope_zh 只描述收录范围,不下结论"
