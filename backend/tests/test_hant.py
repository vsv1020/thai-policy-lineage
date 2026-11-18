# -*- coding: utf-8 -*-
"""繁体版(/zh-hant/):字形转换与覆盖表、页面镜像、语言标记与 hreflang、站内链接不出 /zh-hant/、
资源从站点根目录取、泰文与官方链接不被转换、繁体首页、服务端跳转与 404;
以及同一轮的首页「最新收录」预渲染、监控的繁体薄内容识别、IndexNow 整站重新提交。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import hant, seo, seo_monitor as M, seo_track as T
from app.config import settings
from app.db import session_scope

SITE = settings.site_url
HANT = f"{SITE}/zh-hant"
LANDING = "th-mol-20250701-minwage-14.html"


# ─────────────────────────── 转换器与覆盖表 ───────────────────────────

# 每条覆盖规则一个真实例句(除「干辣椒」外都摘自站内页面):(简体原文, 繁体里应出现的, 不应出现的)
RULE_CASES = [
    ("关于干辣椒的进口检疫要求", "乾辣椒", "幹辣椒"),
    ("可用于经调湿的干态或湿态试样", "乾態", "幹態"),
    ("按干基计算", "乾基", "幹基"),
    ("沙没巴干府", "沙沒巴干府", "巴幹"),
    ("从台湾进口的数字平台", "台灣", "臺"),
    ("由能源部部长发布,将罗勇府", "部長發布", "長髮"),
    ("税务厅发布公告", "稅務廳發布", "發佈"),
    ("公布名单", "公布名單", "公佈"),
    ("依法颁布的", "頒布的", "頒佈"),
    ("宣布灾区", "宣布災區", "宣佈"),
    ("公积金和外国基金发售", "基金發售", "髮售"),
    ("不适用于为自身业务向消费者发卡的企业", "消費者發卡", "髮卡"),
    ("续期/换发规则", "換發規則", "換髮"),
    ("支出须发生于2026年", "支出須發生於", "鬚髮"),
    ("央行职能包括发钞、货币", "包括發鈔", "括髮"),
    ("自刊登次日起60天后生效", "60天後生效", "天后"),
    ("其中暖武里府登记员批准", "暖武里府", "武裡"),
    ("区税务办公室下辖的董里、沙敦", "董里、沙敦", "董裡"),
    ("封闭范围为沙里帕萨旺路口", "沙里帕薩旺", "沙裡"),
    ("班洪、巴桑、湄塔、里、班提五个分支", "湄塔、里、班提", "、裡、"),
    ("乙哌立松口服制剂的适应症", "乙哌立松口服製劑", "立鬆"),
    ("货斗长度不少于", "貨斗長度", "貨鬥"),
    ("散装固体货物船舶检验及证书签发标准", "證書簽發", "籤發"),
    ("飞行签派员执照", "簽派員", "籤派"),
    ("条规定的旧表格,改用", "舊表格", "錶格"),
    ("有足够空间和通风采光", "通風採光", "風采光"),
    ("及水价规定制定", "規定制定", "製定"),
    ("重新规定制动系统与底盘型式认证要求", "規定制動", "製動"),
    ("2022年版协调制度(HS)", "協調制度", "製度"),
    ("内阁决议复议:2025年4月8日", "決議復議", "複議"),
    ("须在海关放行前提交并缴税", "提交並繳稅", "交併"),
    ("成员国原产并发送的种子", "原產並發送", "併發送"),
    ("以促进储蓄并为公众提供更多储蓄产品", "儲蓄並為", "儲蓄併"),
    ("在期限内办理,并到办公室领取", "並到辦公室", "併到辦公室"),
    ("泰国政策周汇总", "週彙總", "周彙總"),
    ("按泰国皇家公报刊登日分周整理", "分週整理", "分周"),
    ("新内容会补进对应的周。", "對應的週", "對應的周"),
    ("2026 年第 17 周(04-20 至 04-26)", "第 17 週", "17 周"),
    ("连续用药超过2周须在医生监督下进行", "2週須", "2周"),
]


@pytest.fixture(scope="module")
def conv():
    return hant.Converter()


@pytest.mark.parametrize("src,good,bad", RULE_CASES)
def test_override_rules_fix_real_sentences(conv, src, good, bad):
    out = conv.text(src)
    assert good in out and bad not in out, out


def test_every_override_rule_has_an_example(conv):
    """覆盖表里每一条规则都要被上面的例句用到(新增规则时补例句)。"""
    rules = json.loads(hant.CONFIG.read_text(encoding="utf-8"))["rules"]
    plain = hant.Converter(rules=[])
    for r in rules:
        hit = any((re.search(r[0][3:], plain.text(src)) if r[0].startswith("re:") else r[0] in plain.text(src))
                  for src, _, _ in RULE_CASES)
        assert hit, f"覆盖规则 {r[0]} 没有对应的例句"
        assert len(r) == 3 and r[2], "每条规则写明原因"


def test_rules_do_not_touch_correct_words(conv):
    """规则只改错处:同字的正确用法不受影响。"""
    out = conv.text("曼谷及周边地区;太后殿;最后一天;复苏;一并废止;合并后;外汇;周岁;生命周期;若干莱土地;宋干节")
    for w in ("周邊", "太后殿", "最後一天", "復甦", "一併廢止", "合併後", "外匯", "週歲", "生命週期", "若干萊", "宋干節"):
        assert w in out, w


def test_s2tw_mode_keeps_legal_vocabulary(conv):
    """只换字形不换词汇:s2twp 会把「发布公告→釋出公告」「申请文件→申請檔案」「项目→專案」。"""
    out = conv.text("发布公告 申请文件 行政程序 投资项目 支持措施 佛历 内阁 征收 汇总")
    assert out == "發布公告 申請文件 行政程序 投資項目 支持措施 佛曆 內閣 徵收 彙總"


def test_keep_protects_text_and_non_han_is_untouched(conv):
    src = ('<a class="lang-switch" href="../p/th-x.html">' + hant.keep("简体中文") + '</a>'
           '<span lang="th">ราชกิจจานุเบกษา เล่ม 143</span> https://www.rd.go.th/a_b.pdf class="pc-sum" 税务')
    out = conv.html(src)
    assert "简体中文" in out and "稅務" in out and hant._K0 not in out
    assert "ราชกิจจานุเบกษา เล่ม 143" in out and "https://www.rd.go.th/a_b.pdf" in out


def test_guard_rejects_rules_that_change_non_han(conv):
    bad = hant.Converter(rules=[("稅", "tax")])
    with pytest.raises(ValueError):
        bad.html("<p>税务</p>")


def test_opencc_version_is_pinned():
    req = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^OpenCC==\d+\.\d+\.\d+", req, re.M), "词典随版本变,必须钉死版本"
    assert "opencc-python-reimplemented" not in req


# ─────────────────────────── 导出的繁体页 ───────────────────────────

INDEX = """<!DOCTYPE html>
<html lang="zh-CN">
<head><title>政策脉络 · 泰国</title><meta name="description" content="泰国政策中文数据库泰国政策中文数据库泰国政策中文数据库泰国政策中文数据库">
<!-- seo:head x -->
OLD
<!-- /seo:head -->
</head><body><header><div class="header-right"><a class="lang-switch" href="zh-hant/" hreflang="zh-Hant" lang="zh-Hant">繁體中文</a></div></header>
<h1>t</h1><div id="feed">
<!-- seo:feed x -->
<div class="card"><div class="pc-sum">政策加载中……</div></div>
<!-- /seo:feed -->
</div><footer>
<!-- seo:links x -->
<!-- /seo:links -->
</footer></body></html>
"""

STATIC = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<title>{t} | 政策脉络 · 泰国</title>
<meta name="description" content="{t}:本站的说明文字,足够长足够长足够长足够长足够长足够长足够长。">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="css/main.css">
<!-- seo:head x -->
<!-- /seo:head -->
</head><body><header><div class="header-right"><a class="lang-switch" href="zh-hant/{f}" hreflang="zh-Hant" lang="zh-Hant">繁體中文</a></div></header>
<h1>{t}</h1><p><a href="index.html">首页</a> · <a href="p/index.html">全部政策</a> · <a href="feed.xml">订阅</a></p>
</body></html>
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("hant")
    (root / "data" / "site").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    for f, t in (("about.html", "怎么用本站"), ("privacy.html", "隐私政策")):
        (root / f).write_text(STATIC.format(t=t, f=f), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    with session_scope() as s:
        stats = seo.build(s)
    yield root, stats
    mp.undo()


def _pages(root: Path, sub: str = "") -> dict[str, Path]:
    base = root / sub if sub else root
    out = {str(p.relative_to(base)): p for p in (base / "p").rglob("*.html") if p.name != "404.html"}
    for f in ("about.html", "privacy.html"):
        if (base / f).exists():
            out[f] = base / f
    return out


def _url(rel: str, hant_: bool) -> str:
    rel = "" if rel == "index.html" and not hant_ else rel
    return f"{HANT if hant_ else SITE}/{rel}"


def _lds(text: str) -> list[dict]:
    return [json.loads(x.replace("<\\/", "</"))
            for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)]


def test_every_page_is_mirrored(site):
    root, stats = site
    hans, hant_ = _pages(root), _pages(root, "zh-hant")
    assert set(hans) == set(hant_), set(hans) ^ set(hant_)
    assert (root / "zh-hant" / "index.html").is_file() and (root / "zh-hant" / "404.html").is_file()
    assert (root / "zh-hant" / "feed.xml").is_file()
    assert sorted(p.name for p in (root / "feed").glob("*.xml")) == \
        sorted(p.name for p in (root / "zh-hant" / "feed").glob("*.xml"))
    assert stats["hant_pages"] == len(hant_) + 2           # 外加繁体首页与 404


def test_language_markup_canonical_and_hreflang(site):
    root, _ = site
    for rel, path in _pages(root, "zh-hant").items():
        t = path.read_text(encoding="utf-8")
        hans_url = f"{SITE}/{rel}"
        hant_url = f"{HANT}/{rel}"
        assert '<html lang="zh-Hant">' in t, rel
        assert f'<link rel="canonical" href="{hant_url}">' in t, rel
        assert '<meta property="og:locale" content="zh_TW">' in t, rel
        assert f"{SITE}/assets/og-hant.png" in t and "assets/og.png" not in t, rel
        for lang, u in (("zh-Hans", hans_url), ("zh-Hant", hant_url), ("x-default", hans_url)):
            assert f'<link rel="alternate" hreflang="{lang}" href="{u}">' in t, (rel, lang)
        for ld in _lds(t):
            if "inLanguage" in ld:
                assert ld["inLanguage"] == "zh-Hant", rel
        # 简体对应页:语言标记不变,hreflang 互指
        s = (root / rel).read_text(encoding="utf-8")
        assert '<html lang="zh-CN">' in s and f'<link rel="canonical" href="{hans_url}">' in s, rel
        assert f'<link rel="alternate" hreflang="zh-Hant" href="{hant_url}">' in s, rel
        assert "zh_TW" not in s and "og-hant" not in s, rel
        assert all(ld.get("inLanguage", "zh-CN") == "zh-CN" for ld in _lds(s)), rel


def test_home_pages_point_to_each_other(site):
    root, _ = site
    idx = (root / "index.html").read_text(encoding="utf-8")
    h = (root / "zh-hant" / "index.html").read_text(encoding="utf-8")
    for t in (idx, h):
        assert f'<link rel="alternate" hreflang="zh-Hans" href="{SITE}/">' in t
        assert f'<link rel="alternate" hreflang="zh-Hant" href="{HANT}/">' in t
        assert f'<link rel="alternate" hreflang="x-default" href="{SITE}/">' in t
    assert f'<link rel="canonical" href="{HANT}/">' in h


def test_language_switch_links(site):
    root, _ = site
    for rel, path in _pages(root, "zh-hant").items():
        t = path.read_text(encoding="utf-8")
        m = re.search(r'<a class="lang-switch" href="([^"]+)" hreflang="zh-Hans" lang="zh-Hans">简体中文</a>', t)
        assert m, rel
        assert urljoin(f"{HANT}/{rel}", m.group(1)) == f"{SITE}/{rel}", rel
        s = (root / rel).read_text(encoding="utf-8")
        m = re.search(r'<a class="lang-switch" href="([^"]+)" hreflang="zh-Hant" lang="zh-Hant">繁體中文</a>', s)
        assert m, rel
        assert urljoin(f"{SITE}/{rel}", m.group(1)) == f"{HANT}/{rel}", rel
    h = (root / "zh-hant" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'class="lang-switch" href="\.\./"[^>]*>简体中文<', h)


def _links(t: str) -> list[tuple[str, str]]:
    """(href/src 值, 整个标签)"""
    return [(m.group(2), m.group(0)) for m in re.finditer(r'<[^>]+?\b(href|src)="([^"]*)"[^>]*>', t)]


ASSET = re.compile(r"^/(css|js|assets)/|^/favicon\.svg$")


def test_internal_links_stay_in_hant_and_assets_come_from_root(site):
    root, _ = site
    pages = dict(_pages(root, "zh-hant"), **{"index.html": root / "zh-hant" / "index.html"})
    for rel, path in pages.items():
        t = path.read_text(encoding="utf-8")
        here = f"{HANT}/{rel}"
        for href, tag in _links(t):
            if href.startswith("#") or (href.startswith("http") and not href.startswith(SITE)):
                continue
            target = urlsplit(urljoin(here, href)).path
            if ASSET.search(target):
                assert not target.startswith("/zh-hant/"), (rel, href)
                continue
            if 'hreflang="zh-Hans"' in tag:          # 切换链接与「检索在简体版」的说明链接
                assert not target.startswith("/zh-hant"), (rel, href)
                continue
            if 'rel="canonical"' in tag or "hreflang=" in tag:
                continue
            assert target.startswith("/zh-hant/"), (rel, href, target)
        for base in re.findall(r'data-base="([^"]*)"', t):
            assert urlsplit(urljoin(here, base)).path == "/", (rel, base)
        for css in re.findall(r'href="([^"]*css/main\.css)"', t):
            assert urlsplit(urljoin(here, css)).path == "/css/main.css", rel


def test_thai_text_and_official_links_unchanged(site):
    root, _ = site
    for rel, path in _pages(root).items():
        s = path.read_text(encoding="utf-8")
        t = (root / "zh-hant" / rel).read_text(encoding="utf-8")
        thai = re.compile("[\u0e00-\u0e7f][\u0e00-\u0e7f0-9 .()/,-]*")
        assert thai.findall(s) == thai.findall(t), rel
        gov = re.compile(r'https?://[A-Za-z0-9.-]+\.go\.th/[^"\s<()]*')
        assert gov.findall(s) == gov.findall(t), rel
        cls = re.compile(r'class="([^"]*)"')
        assert cls.findall(s) == cls.findall(t), rel
        for ld in _lds(t):                        # 仍是合法 JSON(_lds 解析失败会抛错)
            assert ld["@context"] == "https://schema.org"


def test_text_is_converted(site):
    root, _ = site
    t = (root / "zh-hant" / "p" / LANDING).read_text(encoding="utf-8")
    assert "泰國" in t and "免責聲明" in t and "非官方翻譯" in t
    assert "泰国" not in re.sub(r"<[^>]+>", "", t.split("</head>")[1]).replace("简体中文", "")


def test_hant_home_portal(site):
    root, _ = site
    t = (root / "zh-hant" / "index.html").read_text(encoding="utf-8")
    assert t.count("<h1") == 1 and "泰國政策中文數據庫" in t
    assert M.audit_html(f"{HANT}/", t, {})["problems"] == []
    for href in ('href="p/topic/', 'href="p/t/', 'href="p/who/', 'href="p/guide/royal-gazette.html"',
                 'href="p/week/index.html"', 'href="feed.xml"', 'href="feed/', 'href="about.html"'):
        assert href in t, href
    n_entries = len([p for p in (root / "p").glob("*.html") if p.name not in ("index.html", "404.html")])
    assert t.count('class="coll-item"') == min(seo.HANT_LATEST, n_entries)
    assert re.search(r'<a href="\.\./" hreflang="zh-Hans">簡體版首頁</a>', t), "注明互动检索在简体版并给链接"
    lds = {x["@type"]: x for x in _lds(t)}
    assert lds["WebSite"]["inLanguage"] == "zh-Hant" and lds["WebSite"]["url"] == f"{HANT}/"
    assert lds["CollectionPage"]["mainEntity"]["itemListElement"][0]["url"].startswith(f"{HANT}/p/")


def test_hant_static_pages(site):
    root, _ = site
    for f in ("about.html", "privacy.html"):
        t = (root / "zh-hant" / f).read_text(encoding="utf-8")
        assert '<html lang="zh-Hant">' in t and 'href="../css/main.css"' in t and 'href="../favicon.svg"' in t
        assert 'href="index.html"' in t and 'href="p/index.html"' in t, "其余相对链接留在 /zh-hant/ 内"
        assert f'<link rel="canonical" href="{HANT}/{f}">' in t and "OLD" not in t
        assert re.search(r'class="lang-switch" href="\.\./' + f + '"', t)
    assert "怎麼用本站" in (root / "zh-hant" / "about.html").read_text(encoding="utf-8")


def test_sitemap_and_noindex_weeks(site):
    root, stats = site
    sm = M.parse_sitemap((root / "sitemap.xml").read_text(encoding="utf-8"))
    hans = {u for u in sm if not u.startswith(HANT)}
    hant_ = {u for u in sm if u.startswith(HANT)}
    assert {u.replace(HANT, SITE, 1) for u in hant_} | {f"{SITE}/"} == hans | {f"{SITE}/"}
    assert f"{HANT}/" in hant_ and len(hans) == len(hant_)
    assert len(sm) == stats["sitemap_urls"]
    for w in (root / "zh-hant" / "p" / "week").glob("2*.html"):
        t = w.read_text(encoding="utf-8")
        listed = f"{HANT}/p/week/{w.name}" in sm
        assert listed == ('content="noindex, follow"' not in t), w.name
        assert listed == (f"{SITE}/p/week/{w.name}" in sm)


def test_hant_feed(site):
    import xml.etree.ElementTree as ET
    root, _ = site
    raw = (root / "zh-hant" / "feed.xml").read_text(encoding="utf-8")
    feed = ET.fromstring(raw)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert 'xml:lang="zh-Hant"' in raw and "政策脈絡" in raw
    assert feed.find("a:entry", ns).find("a:link", ns).get("href").startswith(f"{HANT}/p/")
    assert feed.find("a:link[@rel='self']", ns).get("href") == f"{HANT}/feed.xml"


def test_hant_404_page(site):
    root, _ = site
    t = (root / "zh-hant" / "404.html").read_text(encoding="utf-8")
    assert '<html lang="zh-Hant">' in t and 'content="noindex, follow"' in t and "頁面不存在" in t
    assert 'href="/zh-hant/p/index.html"' in t and 'href="/css/main.css"' in t
    assert 'rel="canonical"' not in t


def test_build_is_reproducible_and_rebuilds_hant_dir(site):
    root, _ = site
    hdir = root / "zh-hant"
    snap = lambda: {str(p.relative_to(root)): p.read_bytes() for p in hdir.rglob("*") if p.is_file()}  # noqa: E731
    before = snap()
    stale = hdir / "p" / "th-deleted-1.html"
    stale.write_text("old", encoding="utf-8")
    ino = hdir.stat().st_ino
    with session_scope() as s:
        seo.build(s)
    assert not stale.exists(), "已删除条目的繁体页也要消失"
    assert hdir.stat().st_ino == ino, "只清空目录内容,不删目录本身"
    assert snap() == before, "两次导出逐字节一致"


def test_llms_txt_explains_hant_urls(site):
    root, _ = site
    llms = (root / "llms.txt").read_text(encoding="utf-8")
    assert "## 繁体中文版" in llms and f"{HANT}/" in llms and f"{HANT}/p/<uid>.html" in llms
    assert not (root / "zh-hant" / "llms.txt").exists()


# ─────────────────────────── 首页「最新收录」预渲染 ───────────────────────────

def test_home_feed_prerendered_like_policy_card(site):
    root, _ = site
    t = (root / "index.html").read_text(encoding="utf-8")
    block = t.split("<!-- seo:feed x -->")[1].split("<!-- /seo:feed -->")[0]
    pol = json.loads((root / "data" / "site" / "policies.json").read_text(encoding="utf-8")) \
        if (root / "data" / "site" / "policies.json").exists() else None
    from app import analytics as A
    with session_scope() as s:
        featured = [p for p in A.overview(s)["policies"] if p.get("featured")]
    assert pol is None or pol
    assert featured and block.count('<div class="card policy-card">') == len(featured)
    assert "政策加载中" not in block
    for p in featured:
        assert f'<a class="pc-title" href="p/{p["uid"].lower()}.html">' in block
    for cls in ("pc-top", "chip", "pc-title", "pc-sum", "pc-meta"):
        assert f'class="{cls}' in block, cls
    assert "onclick=\"openDetail" not in block, "脚本加载前点标题直接去落地页"


def test_policy_card_matches_frontend_template():
    """与 js/data.js 的 policyCard 逐项对照:类名、方向与影响对象标签、动词、要点 / 薄摘要两种分支。"""
    js = (Path(__file__).resolve().parents[2] / "js" / "data.js").read_text(encoding="utf-8")
    for cls in ("card policy-card", "pc-top", "pc-title", "pc-sum", "pc-points", "pc-meta", "thin-tag"):
        assert cls in js, cls
    p = {"uid": "TH-X-1", "domain": "tax", "domain_label": "税务", "direction": "loose", "title_zh": "标题<b>",
         "summary_zh": "摘" * 100, "key_points": [], "org": "税务厅", "doc_no": "ง 143/52", "doc_no_label": "公报",
         "dates": {"published_at": "2026-01-02"}, "source_url": "https://www.rd.go.th/x.pdf", "verified": True,
         "parties": [{"stance": "support", "label": "中小企业"}, {"stance": "neutral", "label": "消费者"},
                     {"stance": "constrain", "label": "多余"}]}
    h = seo.render_policy_card(p)
    assert '<span class="dir loose">▼ 放宽</span>' in h and "利好 · 中小企业" in h and "多余" not in h
    assert "标题&lt;b&gt;" in h and '<span class="thin-tag">摘要仅据标题</span>' + "摘" * 90 + "…" in h
    assert "<span>刊登 2026-01-02</span>" in h and "<span>公报 <b>ง 143/52</b></span>" in h
    assert '<span class="verified">已人工复核</span>' in h and 'href="https://www.rd.go.th/x.pdf"' in h
    h2 = seo.render_policy_card(dict(p, key_points=["一", "二", "三"], doc_no_label="文号", direction="neutral"))
    assert '<ul class="pc-points"><li>一</li><li>二</li></ul>' in h2 and "<span>发布 2026-01-02</span>" in h2
    assert 'class="dir' not in h2


def test_home_feed_block_idempotent(site):
    root, _ = site
    before = (root / "index.html").read_text(encoding="utf-8")
    with session_scope() as s:
        seo.build(s)
        seo.build(s)
    assert (root / "index.html").read_text(encoding="utf-8") == before
    assert before.count("<!-- seo:feed x -->") == 1 and before.count("<!-- /seo:feed -->") == 1


def test_real_index_has_feed_block_and_switch():
    root = Path(__file__).resolve().parents[2]
    t = (root / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<div id="feed">\s*<!-- seo:feed ', t), "预渲染区块在 #feed 里,前端 set(\'feed\') 会整体替换它"
    assert 'class="lang-switch" href="zh-hant/"' in t
    for f in ("about.html", "privacy.html"):
        assert f'class="lang-switch" href="zh-hant/{f}"' in (root / f).read_text(encoding="utf-8")


# ─────────────────────────── 服务端 ───────────────────────────

def test_zh_hant_redirect_404_and_cache(tmp_path, monkeypatch):
    from app import main
    page = tmp_path / "404.html"
    page.write_text('<html lang="zh-Hant"><body><h1>頁面不存在</h1></body></html>', encoding="utf-8")
    monkeypatch.setattr(main, "NOT_FOUND_PAGE_HANT", page)
    assert "/zh-hant" in main.PUBLIC_DIRS
    with TestClient(main.app) as c:
        r = c.get("/zh-hant", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/zh-hant/"
        r = c.get("/zh-hant/p/no-such-page.html")
        assert r.status_code == 404 and "頁面不存在" in r.text
        assert c.get("/p/no-such-page.html").status_code == 404
        if (main.REPO_ROOT / "zh-hant" / "index.html").is_file():     # 仓库里已有导出的繁体页
            r = c.get("/zh-hant/")
            assert r.status_code == 200 and '<html lang="zh-Hant">' in r.text
            assert r.headers["cache-control"] == "public, max-age=600"
    assert ("/zh-hant/", 600) in main.CACHE_SECONDS


# ─────────────────────────── 监控与统计 ───────────────────────────

def test_monitor_recognises_hant_thin_summary():
    head = ('<title>t</title><link rel="canonical" href="{u}"><h1>x</h1>'
            '<a href="https://www.rd.go.th/x.pdf">原文</a>')
    for u, summary in ((f"{HANT}/p/th-x-1.html", "據標題,本公告涉及某事項,具體條款待原文核對。"),
                       (f"{SITE}/p/th-x-1.html", "据标题,本公告涉及某事项,具体条款待原文核对。")):
        h = head.format(u=u) + f'<h2 style="font-size:15px">中文摘要</h2><p>{summary * 3}</p>'
        assert M.audit_html(u, h, {})["thin"], u
    assert M.THIN_RE.search("待原文核對") and M.THIN_RE.search("據標題")


def test_hant_landing_pages_audited_like_simplified(site):
    root, _ = site
    t = (root / "zh-hant" / "p" / LANDING).read_text(encoding="utf-8")
    a = M.audit_html(f"{HANT}/p/{LANDING}", t, {})
    assert a["problems"] == [], a["problems"]
    assert not M._is_foreign_404("/zh-hant/p/gone.html")


def test_crawl_coverage_counts_hant_separately(monkeypatch, tmp_path):
    """主覆盖率只算简体落地页(分子分母同口径,与历史可比);繁体落地页单列。"""
    assert T._is_landing("/p/th-x.html") and not T._is_landing("/zh-hant/p/th-x.html")
    assert T._is_landing("/zh-hant/p/th-x.html", hant=True) and not T._is_landing("/zh-hant/p/index.html", hant=True)
    sm = tmp_path / "sitemap.xml"
    sm.write_text("".join(f"<loc>{u}</loc>" for u in (
        f"{SITE}/p/a.html", f"{SITE}/p/b.html", f"{HANT}/p/a.html", f"{HANT}/p/b.html", f"{HANT}/")), encoding="utf-8")
    from app import config
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    assert T._sitemap_paths() == {"/p/a.html", "/p/b.html"}
    assert T._sitemap_paths(hant=True) == {"/zh-hant/p/a.html", "/zh-hant/p/b.html"}


# ─────────────────────────── 指南页措辞 ───────────────────────────

def test_guide_hant(site):
    root, _ = site
    h = (root / "zh-hant" / "p" / "guide" / "royal-gazette.html").read_text(encoding="utf-8")
    assert "本站不收錄" in h and "ฉบับทะเบียนฐานันดร" in h and "泰國皇家公報" in h
