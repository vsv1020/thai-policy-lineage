# -*- coding: utf-8 -*-
"""前端结构回归:index.html 被脚本批量编辑过多次,曾经一次删按钮的切片切多了,
把「演进脉络」和「政策维度」两个整视图删掉 —— 测试全绿、没人发现。这组测试防它再来。"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
JS = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "js").glob("*.js")}


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
    for v in ("today", "search", "detail", "lineage", "dims", "trends", "ops"):
        assert f'id="v-{v}"' in HTML, f"视图 v-{v} 丢失"


def test_every_container_js_writes_exists():
    """JS 里 set('xxx', ...) / put('xxx', ...) / getElementById('xxx') 写入的容器必须在页面里。"""
    wanted, dynamic = set(), set()
    for src in JS.values():
        # 只认我们自己的 set/put/setEl(前面不能是「.」—— 排除 URLSearchParams.set 之类)
        wanted |= set(re.findall(r"(?<![.\w])(?:set|put|setEl)\('([a-z0-9-]+)'", src))
        wanted |= set(re.findall(r"getElementById\('([a-z0-9-]+)'\)", src))
        # JS 模板里自己生成的元素(如分面里的输入框)不要求出现在静态 HTML 中
        dynamic |= set(re.findall(r'id="([a-z0-9-]+)"', src))
        dynamic |= set(re.findall(r"\.id = '([a-z0-9-]+)'", src))
    ids = set(re.findall(r'id="([^"]+)"', HTML))
    missing = sorted(wanted - ids - dynamic)
    assert not missing, f"JS 写入但页面里不存在的容器: {missing}"


def test_all_seven_dimensions_have_containers():
    for i in range(1, 8):
        assert f'id="dim{i}"' in HTML


def test_scripts_exist_on_disk():
    for src in re.findall(r'<script src="([^"]+)"', HTML):
        assert (ROOT / src).is_file(), f"引用了不存在的脚本 {src}"


def test_no_fabricated_demo_content_in_html():
    for fake in ("ง 143/58ก", "2569/12", "No. 8/2569", "EV 产业激励"):
        assert fake not in HTML, f"虚构演示内容回来了: {fake}"
