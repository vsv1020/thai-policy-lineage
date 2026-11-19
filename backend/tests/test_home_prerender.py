# -*- coding: utf-8 -*-
"""首页预渲染与前端同一口径:用 node 真跑 js/data.js 的 policyCard 与 renderOverview,
与 seo.render_policy_card / seo.home_texts 的输出逐条比对(不跑 JS 的爬虫读到的,就是前端加载后显示的)。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app import analytics as A, seo
from app.db import session_scope

ROOT = Path(__file__).resolve().parents[2]
node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="需要 node 运行 js/data.js")

HARNESS = r"""
const fs = require('fs');
const api = fs.readFileSync(process.argv[1], 'utf8');
const m = api.match(/const esc = [\s\S]*?\[c\]\)\);/);          // 用 js/api.js 里真正的 esc
const esc = new Function(m[0] + '\nreturn esc;')();
const out = {};
const doc = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
const win = { PolicyData: { esc, set: (id, html) => { if (html) out[id] = html; }, getData: () => new Promise(() => {}) } };
const src = fs.readFileSync(process.argv[2], 'utf8') + '\n;return { policyCard, renderOverview };';
const fns = new Function('window', 'document', 'localStorage', src)(win, doc, {});
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
fns.renderOverview(data.overview);
out.cards = data.cards.map(fns.policyCard);
process.stdout.write(JSON.stringify(out));
"""


def _run_js(overview: dict, cards: list[dict]) -> dict:
    return json.loads(subprocess.run(
        [node, "-e", HARNESS, "--", str(ROOT / "js" / "api.js"), str(ROOT / "js" / "data.js")],
        input=json.dumps({"overview": overview, "cards": cards}, ensure_ascii=False),
        capture_output=True, text=True, check=True).stdout)


def _norm(h: str) -> str:
    """前端卡片多出的只是点击打开站内详情的 onclick 与手型光标;预渲染版刻意不带(脚本加载前直接去落地页)。"""
    h = re.sub(r'\s+onclick="[^"]*"', "", h)
    h = h.replace(' style="cursor:pointer"', "").replace("&#x27;", "&#39;")
    return re.sub(r"\s+", " ", h).strip()


EDGE = [  # 覆盖 policyCard 的各个分支
    {"uid": "TH-X-1", "domain": "tax", "domain_label": "税务", "direction": "loose", "title_zh": "标题<b>&'\"",
     "summary_zh": "摘" * 100, "key_points": [], "org": "税务厅", "doc_no": "ง 143/52", "doc_no_label": "公报",
     "dates": {"published_at": "2026-01-02"}, "source_url": "https://www.rd.go.th/x.pdf?a=1&b=2", "verified": True,
     "parties": [{"stance": "support", "label": "中小企业"}, {"stance": "neutral", "label": "消费者"},
                 {"stance": "constrain", "label": "多余"}]},
    {"uid": "TH-X-2", "domain": "visa", "domain_label": "签证居留", "direction": "neutral", "title_zh": "决议",
     "summary_zh": "短摘要", "key_points": ["一", "二", "三"], "org": "", "doc_no": "", "doc_no_label": "文号",
     "dates": {"resolved_at": "2026-02-03"}, "date": "2026-02-03", "source_url": "", "verified": False, "parties": []},
    {"uid": "TH-X-3", "domain": "biz", "domain_label": "公司投资", "direction": "tight", "title_zh": "官网公告",
     "summary_zh": "摘要", "key_points": ["要点"], "org": "BOI", "doc_no": "ป.1/2568", "doc_no_label": "文号",
     "dates": {"published_at": "2026-03-04"}, "source_url": "https://www.boi.go.th/a", "verified": False,
     "parties": [{"stance": "constrain", "label": "外资企业"}]},
]


@pytest.fixture(scope="module")
def overview():
    with session_scope() as s:
        return A.overview(s)


def test_policy_card_matches_frontend(overview):
    """测试库里的全部条目加上几条边界样例:Python 版与 js/data.js 的 policyCard 归一化后逐条相同。"""
    cards = (overview["policies"] or []) + EDGE
    js = _run_js(overview, cards)["cards"]
    assert len(js) == len(cards) >= 3
    for p, h in zip(cards, js):
        assert _norm(seo.render_policy_card(p)) == _norm(h), p["uid"]


def test_home_texts_match_render_overview(overview):
    """页头时间戳、条数与数据说明:导出时写进 index.html 的,与前端 renderOverview 填写的完全相同。"""
    js = _run_js(overview, [])
    py = seo.home_texts(overview)
    for k in ("stamp", "today-sub", "lag-note"):
        assert py[k] == js[k], k
    feed = seo.render_home_feed([p for p in overview["policies"] if p.get("featured")])
    assert _norm(feed) == _norm(js["feed"])


def test_index_html_prerender_blocks(tmp_path, monkeypatch, overview):
    page = tmp_path / "index.html"
    blocks = "".join(f'<span id="{n}"><!-- seo:{n} x -->旧<!-- /seo:{n} --></span>'
                     for n in ("stamp", "today-sub", "lag-note"))
    page.write_text('<html lang="zh-CN"><head>\n<!-- seo:head x -->\n<!-- /seo:head -->\n</head><body>'
                    + blocks + '<div id="feed">\n<!-- seo:feed x -->\n旧\n<!-- /seo:feed -->\n</div>'
                    '<footer>\n<!-- seo:links x -->\n<!-- /seo:links -->\n</footer></body></html>', encoding="utf-8")
    monkeypatch.setattr(seo, "REPO_ROOT", tmp_path)
    assert seo.update_index_html([], [], {}, overview=overview)
    t = page.read_text(encoding="utf-8")
    for n, text in seo.home_texts(overview).items():
        assert f"<!-- seo:{n} x -->{text}<!-- /seo:{n} -->" in t, n
    assert "旧" not in t
    seo.update_index_html([], [], {}, overview=overview)
    assert page.read_text(encoding="utf-8") == t, "幂等"
