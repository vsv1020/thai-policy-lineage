# -*- coding: utf-8 -*-
"""前端结构回归:index.html 被脚本批量编辑过多次,曾经一次删按钮的切片切多了,
把「演进脉络」和「政策维度」两个整视图删掉 —— 测试全绿、没人发现。这组测试防它再来。"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
ADMIN = (ROOT / "admin.html").read_text(encoding="utf-8")


def scripts_of(html: str) -> dict[str, str]:
    """页面实际加载的脚本(vendor 与 echarts 之类的第三方库除外)。"""
    out = {}
    for src in re.findall(r'<script src="([^"]+)"', html):
        if src.startswith("js/") and "vendor" not in src and "echarts" not in src:
            out[src] = (ROOT / src).read_text(encoding="utf-8")
    return out


class Balance(HTMLParser):
    VOID = {"meta", "link", "br", "img", "input", "hr", "source"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> 与 <{self.stack[-1] if self.stack else '∅'}> 不配对")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def test_tags_balanced():
    b = Balance(); b.feed(HTML)
    assert not b.errors, b.errors[:5]
    assert b.stack == [], f"未闭合: {b.stack}"


def test_every_nav_item_has_a_view():
    navs = set(re.findall(r'class="nav-item[^"]*" data-v="([^"]+)"', HTML))
    views = set(re.findall(r'<section class="view[^"]*" id="v-([^"]+)"', HTML))
    assert navs, "导航项不应为空"
    assert navs <= views, f"导航指向不存在的视图: {navs - views}"


def test_expected_views_present():
    for v in ("today", "search", "detail", "lineage", "dims", "trends", "morph"):
        assert f'id="v-{v}"' in HTML, f"视图 v-{v} 丢失"


def test_morphology_is_live():
    assert 'data-v="morph"' in HTML and "js/morph.js" in HTML
    nav = re.search(r'<div class="nav-item[^"]*"[^>]*>.*?政策形态.*?</div>', HTML).group(0)
    assert "规划中" not in nav and "soon" not in nav


def test_collection_status_only_in_admin():
    """采集状态只放在管理后台,前台不显示。"""
    assert 'id="v-ops"' not in HTML and 'data-v="ops"' not in HTML and "js/ops.js" not in HTML
    assert "采集状态" not in HTML
    assert "js/ops.js" in ADMIN and 'id="ops-sources"' in ADMIN


def _missing_containers(html: str) -> list[str]:
    wanted, dynamic = set(), set()
    for src in scripts_of(html).values():
        # 只认我们自己的 set/put/setEl(前面不能是「.」—— 排除 URLSearchParams.set 之类)
        wanted |= set(re.findall(r"(?<![.\w])(?:set|put|setEl)\('([a-z0-9-]+)'", src))
        wanted |= set(re.findall(r"getElementById\('([a-z0-9-]+)'\)", src))
        # JS 模板里自己生成的元素(如分面里的输入框)不要求出现在静态 HTML 中
        dynamic |= set(re.findall(r'id="([a-z0-9-]+)"', src))
        dynamic |= set(re.findall(r"\.id = '([a-z0-9-]+)'", src))
    ids = set(re.findall(r'id="([^"]+)"', html))
    return sorted(wanted - ids - dynamic)


def test_every_container_js_writes_exists():
    """页面加载的 JS 里 set/put/getElementById 写入的容器,必须在该页面里存在。"""
    assert not _missing_containers(HTML), f"首页缺容器: {_missing_containers(HTML)}"
    assert not _missing_containers(ADMIN), f"后台缺容器: {_missing_containers(ADMIN)}"


def test_all_seven_dimensions_have_containers():
    for i in range(1, 8):
        assert f'id="dim{i}"' in HTML


def test_scripts_exist_on_disk():
    for html in (HTML, ADMIN):
        for src in re.findall(r'<script src="([^"]+)"', html):
            assert (ROOT / src).is_file(), f"引用了不存在的脚本 {src}"


def test_no_fabricated_demo_content_in_html():
    for fake in ("ง 143/58ก", "2569/12", "No. 8/2569", "EV 产业激励"):
        assert fake not in HTML, f"虚构演示内容回来了: {fake}"


def test_nav_speaks_plain_language():
    """导航只放有内容、看得懂的入口:没有「规划中」,没有空的脉络页,也没有只能从卡片进入的详情页。"""
    navs = re.findall(r'class="nav-item[^"]*" data-v="([^"]+)"', HTML)
    assert navs == ["today", "search", "lineage", "trends", "morph", "dims"]
    assert "规划中" not in HTML and "政策助手" not in HTML
    # 脉络页进了导航,就必须有内容(同名系列由官方标题推导,随数据自动增减)
    lineage = json.loads((ROOT / "data/site/lineage.json").read_text(encoding="utf-8"))
    assert lineage["issues"], "脉络为空时不要把它放进导航"
    assert 'href="about.html"' in HTML


def test_front_page_explains_itself_and_has_search():
    assert 'id="intro"' in HTML and "给在泰国生活、经商、投资的华人用" in HTML
    assert 'id="home-q"' in HTML and 'type="search"' in HTML and 'id="sq"' in HTML
    assert HTML.count('class="dom-btn chip') == 10
    assert "24–48" not in HTML, "做不到的时效承诺不能写在首页"
    assert "最新收录" in HTML and "今日政策" not in HTML
    assert (ROOT / "about.html").is_file()
