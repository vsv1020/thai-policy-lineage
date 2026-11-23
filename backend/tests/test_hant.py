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

# 每条覆盖规则至少一个例句:(简体原文, 繁体里应出现的, 不应出现的)。
# 大多摘自站内页面;标 * 的是本领域高概率出现、现语料暂无的写法(审阅时用转换器确认过 s2tw 会错)
RULE_CASES = [
    ("关于干辣椒的进口检疫要求", "乾辣椒", "幹辣椒"),                  # *
    ("进口干木耳与干香菇", "乾木耳與乾香菇", "幹"),                     # *
    ("按干物质计", "乾物質", "幹物質"),                                # *
    ("辣椒干与香菇干", "辣椒乾與香菇乾", "幹"),                         # *
    ("可用于经调湿的干态或湿态试样", "乾態", "幹態"),
    ("按干基计算", "乾基", "幹基"),
    ("沙没巴干府", "沙沒巴干府", "巴幹"),
    ("汶干府土地办公室", "汶干府", "汶幹"),                            # *
    ("关于在干乍那武里府实施城市规划", "干乍那武里府", "幹乍那"),
    ("甘烹碧府占提玛镇的城市规划", "占提瑪鎮", "佔提"),
    ("呵叻府巴冲县土地整理项目", "巴沖縣", "巴衝"),                    # *
    ("采用分布式能源系统", "分布式", "分佈式"),
    ("清单编制及送达纳税人", "清單編製及送達", "清單編制"),
    ("府自治组织编制土地与建筑物税清单", "組織編製土地", "組織編制"),
    ("市政应编制预算", "應編製預算", "編制預算"),
    ("持落地签入境的旅客", "落地簽", "落地籤"),                         # *
    ("申请工作签与电子签", "工作簽與電子簽", "籤"),                     # *
    ("免签与旅游签、学生签", "免簽與旅遊簽、學生簽", "籤"),             # *
    ("养老签、退休签与精英签", "養老簽、退休簽與精英簽", "籤"),         # *
    ("过境签、投资签、长期签与返签", "過境簽、投資簽、長期簽與返簽", "籤"),  # *
    ("部门负责编制人员名单", "負責編製人員名單", "編制"),               # *
    ("从台湾进口的数字平台", "台灣", "臺"),
    ("道路与公共设施布局及环境", "公共設施布局", "佈局"),
    ("由能源部部长发布,将罗勇府", "部長發布", "長髮"),
    ("该命令由曼谷市长发布", "市長發布", "長髮"),
    ("由交通警察总长发布", "總長發布", "長髮"),
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
    ("南奔府里县土地办公室", "南奔府里縣", "裡縣"),                    # *
    ("乙哌立松口服制剂的适应症", "乙哌立松口服製劑", "立鬆"),
    ("货斗长度不少于", "貨斗長度", "貨鬥"),
    ("散装固体货物船舶检验及证书签发标准", "證書簽發", "籤發"),
    ("飞行签派员执照", "簽派員", "籤派"),
    ("关于网络安全要求的议定书签署事宜", "議定書簽署", "籤署"),         # 2026-11-22 日报 TH-CABX-20251104
    ("并更新法令附图中签署人姓名", "圖中簽署人", "籤署"),               # 2026-11-22 日报 TH-CABX-20241217
    ("条规定的旧表格,改用", "舊表格", "錶格"),
    ("有足够空间和通风采光", "通風採光", "風采光"),
    ("及水价规定制定", "規定制定", "製定"),
    ("重新规定制动系统与底盘型式认证要求", "規定制動", "製動"),
    ("2022年版协调制度(HS)", "協調制度", "製度"),
    ("内阁决议复议:2025年4月8日", "決議復議", "複議"),
    ("对差额进行复核,计算", "進行複核", "復核"),
    ("海关人员怀疑托运行李", "懷疑託運行李", "托運"),
    ("广告商及其合作伙伴可能使用 Cookie", "合作夥伴", "伙伴"),
    ("须在海关放行前提交并缴税", "提交並繳稅", "交併"),
    ("成员国原产并发送的种子", "原產並發送", "併發"),
    ("部长制定并发布规定", "制定並發布", "併發"),                       # *
    ("委员会审议并发放许可", "審議並發放", "併發"),                     # *
    ("完成登记并发证", "登記並發證", "併發"),                           # *
    ("以促进储蓄并为公众提供更多储蓄产品", "儲蓄並為", "儲蓄併"),
    ("在期限内办理,并到办公室领取", "並到辦公室", "併到辦公室"),
    ("并要求专家具备至少5年经验", "專家具備", "傢俱"),
    ("国家具有管辖权", "國家具有", "傢俱"),                             # *
    ("由国家具体规定", "國家具體", "傢俱"),                             # *
    ("对箱包、家具、印刷品", "家具", "傢俱"),
    ("撤销此前授予一家私人检验公司的许可", "一家私人檢驗公司", "傢俬"),   # 2026-11-19 采集的 TH-BOI-20261117-139685
    ("国家私有化计划", "國家私有化", "傢俬"),                             # *
    ("泰国受邀请成为金砖国家伙伴国", "金磚國家夥伴國", "傢"),          # 2026-11-22 日报 TH-CABX-20241224
    ("公告列明了生产、进口的条件", "列明了", "明瞭"),
    ("公告载明了适用范围", "載明了", "明瞭"),                           # *
    ("附表标明了税率", "標明了", "明瞭"),                               # *
    ("说明书阐明了用途", "闡明了", "明瞭"),                             # *
    ("不得与其他业务冲抵", "沖抵", "衝抵"),
    ("可冲减应纳税额", "沖減", "衝減"),                                 # *
    ("按规定冲账并冲回", "沖賬並沖回", "衝"),                           # *
    ("折合泰铢计算", "折合泰銖", "摺合"),                               # *
    ("不准进口", "不准進口", "不準"),                                   # *
    ("经御准后公布", "御准", "御準"),                                   # *
    ("呈报内阁照准", "照准", "照準"),                                   # *
    ("本规定系根据第5条制定", "係根據", "系根據"),                      # *
    ("本公告系由投资促进委员会发布", "係由", "系由"),                   # *
    ("泰国政策周汇总", "週彙總", "周彙總"),
    ("按泰国皇家公报刊登日分周整理", "分週整理", "分周"),
    ("新内容会补进对应的周。", "對應的週", "對應的周"),
    ("2026 年第 17 周(04-20 至 04-26)", "第 17 週", "17 周"),
    ("连续用药超过2周须在医生监督下进行", "2週須", "2周"),
    # 用词(不是字形):只收无歧义、且目前只出现在本站说明文字里的两个词
    ("泰国政策中文数据库:皇家公报与内阁决议", "中文資料庫", "數據庫"),
    ("每条附中文摘要与泰文原文链接。", "泰文原文連結", "鏈接"),
]

# 规则不能误伤的正确用法:(简体原文, 繁体里应出现的)
KEEP_CASES = [
    ("SGLT2抑制剂", "抑制劑"), ("限制剂量", "限制劑量"), ("控制剂量", "控制劑量"), ("管制剂型", "管制劑型"),
    ("曼谷部分周边府", "部分周邊府"), ("十分周到", "十分周到"), ("曼谷及周边地区", "周邊"),
    ("长发须束起", "長髮須束起"), ("换发型", "換髮型"),
    ("天后宫", "天后宮"), ("三十天后生效", "三十天後生效"),
    ("书签与标签", "書籤與標籤"), ("抽签决定", "抽籤決定"), ("免签入境", "免簽入境"), ("续签", "續簽"),
    ("人员编制", "人員編制"), ("编制内人员", "編制內"), ("编制员额", "編制員額"), ("编制外聘用", "編制外"),
    ("机构编制", "機構編制"), ("核定编制", "核定編制"), ("扩大编制", "擴大編制"), ("编制名额", "編制名額"),
    ("编制数不变", "編制數"), ("便签", "便籤"), ("牙签", "牙籤"), ("中签", "中籤"), ("这家伙", "傢伙"), ("中签名单", "中籤名單"), ("容器封签样品", "封籤"),
    ("巴冲突", "巴衝突"), ("占领", "佔領"),
    ("王后", "王后"), ("皇后", "皇后"), ("太后殿", "太后殿"), ("陛下", "陛下"), ("殿下", "殿下"),
    ("了解", "瞭解"), ("简单明了", "簡單明瞭"), ("冲突", "衝突"), ("冲击", "衝擊"), ("冲洗", "沖洗"),
    ("并发症", "併發症"), ("一并发布", "一併發布"), ("合并发布", "合併發布"), ("合并后", "合併後"),
    ("申请并网", "申請併網"), ("不准确", "不準確"), ("标准", "標準"), ("批准", "批准"),
    ("系统由三部分组成", "系統由"), ("体系由", "體系由"), ("恢复核电", "恢復核電"),
    ("最后一天", "最後一天"), ("复苏", "復甦"), ("一并废止", "一併廢止"), ("外汇", "外匯"),
    ("周岁", "週歲"), ("生命周期", "生命週期"), ("若干莱土地", "若干萊"), ("宋干节", "宋干節"),
    ("主干道", "主幹道"), ("干部", "幹部"),
    # 「某某链 + 接…」不是「链接」
    ("须提供供应链接入方案", "供應鏈接入"), ("区块链接口标准", "區塊鏈接口"), ("与全球产业链接轨", "產業鏈接軌"),
    ("冷链接驳点", "冷鏈接駁"), ("价值链接续", "價值鏈接續"),
    # 词汇不整体换成台湾用语:法律文本里的「发布、文件、程序、项目、信息」保持原词
    ("发布公告", "發布公告"), ("申请文件", "申請文件"), ("行政程序", "行政程序"), ("投资项目", "投資項目"),
    ("信息交换", "信息交換"), ("网络安全", "網絡安全"), ("数据保护", "數據保護"),
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


@pytest.mark.parametrize("src,good", KEEP_CASES)
def test_rules_do_not_touch_correct_words(conv, src, good):
    """规则只改错处:同字的正确用法(含王室称谓)不受影响。"""
    assert good in conv.text(src), conv.text(src)


def test_suspicious_patterns_flag_known_errors_and_spare_correct_words(conv):
    """可疑字形清单:未修正的 s2tw 输出都会被标出;正确用法与修正后的输出都不命中。"""
    pats = hant.load_suspicious()
    assert pats, "config/hant.json 要有 suspicious 清单"
    plain = hant.Converter(rules=[])
    hit = lambda t: [n for rx, n in pats if rx.search(t)]  # noqa: E731
    for src, good, bad in RULE_CASES:
        assert not hit(conv.text(src)), (src, conv.text(src), hit(conv.text(src)))
    for src in ("专家具备", "列明了", "冲抵", "折合", "制定并发布", "干木耳", "汶干府", "南奔府里县", "御准", "不准进口"):
        assert hit(plain.text(src)), src
    for src, good in KEEP_CASES:
        assert not hit(conv.text(src)), (src, hit(conv.text(src)))


def test_scan_and_cli(tmp_path, capsys):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "a.html").write_text("<p>要求專傢俱備至少5年</p>", encoding="utf-8")
    (tmp_path / "ok.html").write_text("<p>要求專家具備至少5年</p>", encoding="utf-8")
    hits = hant.scan(tmp_path)
    assert [h[0] for h in hits] == ["p/a.html"] and "傢俱" in hits[0][2]
    assert hant.main(["--check", str(tmp_path)]) == 1 and "p/a.html" in capsys.readouterr().out
    (tmp_path / "p" / "a.html").unlink()
    assert hant.main(["--check", str(tmp_path)]) == 0


def test_real_hant_output_has_no_suspicious_forms():
    """仓库里导出的繁体成品必须零命中(命中说明出现了覆盖表没盖住的新语境)。"""
    root = Path(__file__).resolve().parents[2] / "zh-hant"
    if not root.is_dir():
        pytest.skip("仓库里还没有导出的 zh-hant/")
    assert hant.scan(root) == []


def test_stray_keep_markers_are_rejected(conv):
    with pytest.raises(ValueError):
        conv.text("税务" + hant._K0 + "残缺")
    with pytest.raises(ValueError):
        hant.keep("a" + hant._K1)


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
<main style="max-width:780px;margin:0 auto;padding:32px 20px">
<h1>{t}</h1><p><a href="index.html">首页</a> · <a href="p/index.html">全部政策</a> · <a href="feed.xml">订阅</a></p>
</main>
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
        # 繁体页多一层侧栏外壳(.layout + aside),其余结构与简体页逐个相同
        assert '<div class="layout"><aside' in t, f"{rel}:繁体页都带左侧导航"
        body = re.sub(r'<div class="layout"><aside\b.*?</aside>', "", t, count=1, flags=re.S)
        assert cls.findall(s) == cls.findall(body), rel
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
    assert t.count("<h1") == 1 and "泰國政策中文資料庫" in t, "「数据库」在繁体页作「資料庫」"
    head = t.split("</head>")[0]
    desc = re.search(r'<meta name="description" content="([^"]*)"', head).group(1)
    # 门户页没有七维分析与趋势看板,描述与开场白不能许诺页面上没有的功能
    for absent in ("七維", "趨勢看板", "數據庫", "鏈接"):
        assert absent not in desc and absent not in t.split("<main")[1].split("<nav")[0], absent
    assert desc.startswith("泰國皇家公報") and "泰文原文連結" in desc
    assert M.audit_html(f"{HANT}/", t, {})["problems"] == []
    for href in ('href="p/topic/', 'href="p/t/', 'href="p/who/', 'href="p/guide/royal-gazette.html"',
                 'href="p/week/index.html"', 'href="feed.xml"', 'href="feed/', 'href="about.html"'):
        assert href in t, href
    n_entries = len([p for p in (root / "p").glob("*.html") if p.name not in ("index.html", "404.html")])
    assert t.count('class="coll-item"') == min(seo.HANT_LATEST, n_entries)
    assert re.search(r'<a href="\.\./" hreflang="zh-Hans">簡體版首頁</a>', t), "注明互动检索在简体版并给链接"
    # 左侧导航:与简体首页同一套 .layout / aside(桌面左栏、手机顶部标签),但只链繁体版自己的页面:
    # 门户页不加载 app.js,所以是普通链接;不能有掉进简体版的入口(语言切换在页头,不在侧栏)
    assert '<div class="layout"><aside' in t and t.index("</aside>") < t.index("<main"), "侧栏在正文之前,版式与简体首页一致"
    aside = t.split("<aside", 1)[1].split("</aside>", 1)[0]
    assert "data-v=" not in aside and "zh-Hans" not in aside and 'href="../' not in aside, "侧栏不链简体版"
    assert re.search(r'<a class="nav-item active" href="index.html" aria-current="page">.*最新收錄</a>', aside)
    for href in ('href="p/index.html"', 'href="p/week/index.html"', 'href="p/guide/royal-gazette.html"',
                 'href="about.html"', 'href="privacy.html"'):
        assert href in aside, href
    for anchor in ("by-domain", "by-topic", "by-party"):
        assert f'href="#{anchor}"' in aside and f'id="{anchor}"' in t, f"侧栏锚点 #{anchor} 在正文里有对应分组"
    assert "週彙總" in aside and "專題彙總" in aside and "周汇总" not in aside, "侧栏文字同样转成繁体"
    assert t.rstrip().count("</main></div>") == 1
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
    from app import analytics as A
    with session_scope() as s:
        featured = [p for p in A.overview(s)["policies"] if p.get("featured")]
    assert featured and block.count('<div class="card policy-card">') == len(featured)
    assert "政策加载中" not in block
    for p in featured:
        assert f'<a class="pc-title" href="p/{p["uid"].lower()}.html">' in block
    for cls in ("pc-top", "chip", "pc-title", "pc-sum", "pc-meta"):
        assert f'class="{cls}' in block, cls
    assert "onclick=\"openDetail" not in block, "脚本加载前点标题直接去落地页"


def test_policy_card_branches():
    """render_policy_card 的各个分支(与 js/data.js 逐条比对见 test_home_prerender.py,用 node 真跑前端)。"""
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

def test_zh_hant_redirect_404_and_cache():
    """真实挂载:/zh-hant 301;/zh-hant/ 下不存在的页面由 StaticFiles 给 zh-hant/404.html(状态码 404)。
    目录里没有 404.html 时的兜底分支见 test_not_found_handler_uses_hant_page_for_zh_hant_paths。"""
    from app import main
    assert "/zh-hant" in main.PUBLIC_DIRS
    with TestClient(main.app) as c:
        r = c.get("/zh-hant", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/zh-hant/"
        assert c.get("/p/no-such-page.html").status_code == 404
        if (main.REPO_ROOT / "zh-hant" / "index.html").is_file():     # 仓库里已有导出的繁体页
            r = c.get("/zh-hant/p/no-such-page.html")
            assert r.status_code == 404 and '<html lang="zh-Hant">' in r.text and "頁面不存在" in r.text
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


# ─────────────────────────── 失败模式:先渲染、后写盘;非严格模式 ───────────────────────────

def _fresh_site(root: Path, mp: pytest.MonkeyPatch) -> Path:
    (root / "data" / "site").mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    for f, t in (("about.html", "怎么用本站"), ("privacy.html", "隐私政策")):
        (root / f).write_text(STATIC.format(t=t, f=f), encoding="utf-8")
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    return root


def _snap(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and not str(p.relative_to(root)).startswith("data")}


def _boom_after(n: int):
    real = hant.Converter.html
    calls = {"n": 0}

    def html(self, s):
        calls["n"] += 1
        if calls["n"] > n:
            raise RuntimeError("模拟转换中途出错")
        return real(self, s)
    return html


def test_failed_hant_conversion_leaves_all_old_files(tmp_path, monkeypatch):
    """严格模式(默认):转换中途出错照常抛错,但简繁两套旧文件、sitemap 一个字节都不动。"""
    root = _fresh_site(tmp_path, monkeypatch)
    monkeypatch.delenv("HANT_STRICT", raising=False)
    with session_scope() as s:
        seo.build(s)
    before = _snap(root)
    monkeypatch.setattr(hant.Converter, "html", _boom_after(5))
    with session_scope() as s, pytest.raises(RuntimeError):
        seo.build(s)
    assert _snap(root) == before


def test_non_strict_keeps_old_hant_and_only_links_existing_pages(tmp_path, monkeypatch):
    """HANT_STRICT=0:繁体失败只记日志,旧 zh-hant/ 原样保留,简体照常导出;
    简体页与 sitemap 只引用旧 zh-hant/ 里确实存在的繁体页。"""
    root = _fresh_site(tmp_path, monkeypatch)
    with session_scope() as s:
        seo.build(s)
    (root / "zh-hant" / "p" / LANDING).unlink()              # 旧繁体版里缺这一页
    (root / "p" / "index.html").unlink()                     # 简体要照常重新生成
    old_hant = {k: v for k, v in _snap(root).items() if k.startswith("zh-hant/")}
    monkeypatch.setenv("HANT_STRICT", "0")
    monkeypatch.setattr(hant.Converter, "html", _boom_after(0))
    with session_scope() as s:
        stats = seo.build(s)
    assert stats["hant_ok"] is False
    assert {k: v for k, v in _snap(root).items() if k.startswith("zh-hant/")} == old_hant
    assert (root / "p" / "index.html").is_file()
    sm = M.parse_sitemap((root / "sitemap.xml").read_text(encoding="utf-8"))
    assert f"{HANT}/p/{LANDING}" not in sm and f"{HANT}/p/index.html" in sm
    t = (root / "p" / LANDING).read_text(encoding="utf-8")
    assert 'hreflang="zh-Hant"' not in t and "lang-switch" not in t
    assert 'hreflang="zh-Hant"' in (root / "p" / "index.html").read_text(encoding="utf-8")


def test_non_strict_without_old_hant_references_no_hant_pages(tmp_path, monkeypatch):
    root = _fresh_site(tmp_path, monkeypatch)
    monkeypatch.setenv("HANT_STRICT", "0")
    monkeypatch.setattr(hant.Converter, "html", _boom_after(0))
    with session_scope() as s:
        seo.build(s)
    assert not any((root / "zh-hant").rglob("*.html"))
    assert "zh-hant" not in (root / "sitemap.xml").read_text(encoding="utf-8")
    for p in (root / "p").rglob("*.html"):
        t = p.read_text(encoding="utf-8")
        assert "hreflang=" not in t and "lang-switch" not in t, p
    idx = (root / "index.html").read_text(encoding="utf-8").split("<!-- /seo:head -->")[0]
    assert "hreflang=" not in idx


def test_strict_flag_parsing(monkeypatch):
    for v, want in (("1", True), ("", True), ("0", False), ("false", False), ("no", False)):
        monkeypatch.setenv("HANT_STRICT", v)
        assert seo.hant_strict() is want, v
    monkeypatch.delenv("HANT_STRICT")
    assert seo.hant_strict() is True
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "HANT_STRICT: ${HANT_STRICT:-0}" in compose, "生产配置为非严格"


# ─────────────────────────── 字形状态、静态页改写、404 分支 ───────────────────────────

def test_variant_resets_on_exception_and_is_per_context():
    import threading
    assert seo.page_url("TH-X-1") == f"{SITE}/p/th-x-1.html"
    with pytest.raises(KeyError):
        with seo._variant(True):
            assert seo.page_url("TH-X-1") == f"{HANT}/p/th-x-1.html"
            raise KeyError("x")
    assert seo.page_url("TH-X-1") == f"{SITE}/p/th-x-1.html", "异常退出后复位"
    seen = {}
    with seo._variant(True):
        t = threading.Thread(target=lambda: seen.setdefault("url", seo.page_url("TH-X-1")))
        t.start()
        t.join()
    assert seen["url"] == f"{SITE}/p/th-x-1.html", "别的线程不读到繁体状态"


def test_render_hant_static_rewrites_data_base_and_requires_lang():
    src = ('<!DOCTYPE html>\n<html class="x" lang="zh-CN" dir="ltr"><head>\n<!-- seo:head x -->\n<!-- /seo:head -->\n'
           '<title>隐私政策</title></head><body><a class="lang-switch" href="zh-hant/privacy.html">繁體中文</a>'
           '<script src="js/track.js" data-base=""></script><script src="js/ads.js" data-base="./"></script>'
           '<main style="max-width:780px;margin:0 auto;padding:32px 20px"><a href="index.html">首页</a></main>'
           '</body></html>')
    with seo._variant(True):
        out = seo.render_hant_static(src, "privacy.html", "隐私政策", "WebPage")
    assert '<div class="layout"><aside' in out and '<main><div style="max-width:780px">' in out
    assert out.count("</div></main></div>") == 1
    assert '<a class="nav-item side-extra active" href="privacy.html" aria-current="page">' in out
    assert '<html class="x" lang="zh-Hant" dir="ltr">' in out
    assert 'src="../js/track.js" data-base="../"' in out and 'data-base=".././"' in out
    assert 'href="index.html"' in out and 'href="../privacy.html"' in out
    with seo._variant(True), pytest.raises(ValueError):
        seo.render_hant_static(src.replace('lang="zh-CN"', 'lang="zh"'), "privacy.html", "隐私政策", "WebPage")


def test_hant_about_explains_where_search_lives(site):
    root, _ = site
    (root / "about.html").write_text(STATIC.format(t="怎么用本站", f="about.html").replace(
        "<h1>", '<!-- seo:hant-note x -->\n<!-- /seo:hant-note -->\n<h1>'), encoding="utf-8")
    with session_scope() as s:
        seo.build(s)
    h = (root / "zh-hant" / "about.html").read_text(encoding="utf-8")
    assert 'class="hant-note"' in h and '<a href="../" hreflang="zh-Hans">簡體版首頁</a>' in h
    assert 'class="hant-note"' not in (root / "about.html").read_text(encoding="utf-8"), "简体页留空"
    real = (Path(__file__).resolve().parents[2] / "about.html").read_text(encoding="utf-8")
    assert "<!-- seo:hant-note " in real


def test_not_found_handler_uses_hant_page_for_zh_hant_paths(tmp_path, monkeypatch):
    """StaticFiles 目录里没有 404.html 时由异常处理器兜底:/zh-hant/ 下给繁体 404 页,其余给简体。"""
    import asyncio
    from starlette.exceptions import HTTPException as SE
    from starlette.requests import Request
    from app import main
    hp, sp = tmp_path / "h404.html", tmp_path / "s404.html"
    hp.write_text("繁體 404", encoding="utf-8")
    sp.write_text("简体 404", encoding="utf-8")
    monkeypatch.setattr(main, "NOT_FOUND_PAGE_HANT", hp)
    monkeypatch.setattr(main, "NOT_FOUND_PAGE", sp)

    def call(path):
        req = Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})
        return asyncio.run(main.not_found(req, SE(404)))
    r = call("/zh-hant/p/gone.html")
    assert r.status_code == 404 and Path(r.path) == hp and r.headers["x-robots-tag"] == "noindex"
    assert Path(call("/p/gone.html").path) == sp
    assert Path(call("/zh-hantx/gone.html").path) == sp


def test_every_hant_page_keeps_the_sidebar(site):
    """站长反馈:从繁体首页点「全部政策 / 周汇总 / 指南 / 关于 / 隐私」后左侧导航不见了。
    每个繁体页都要有侧栏,链接按页面层级换算、都指向存在的繁体页,当前页高亮,且不链简体版。"""
    import posixpath
    root, _ = site
    hant = root / "zh-hant"
    want = {"index.html": "最新收錄", "p/index.html": "全部政策", "p/week/index.html": "週彙總",
            "about.html": "怎麼用本站", "privacy.html": "隱私政策", "p/guide/royal-gazette.html": "皇家公報指南"}
    for f in hant.rglob("*.html"):
        rel = f.relative_to(hant).as_posix()
        t = f.read_text(encoding="utf-8")
        assert t.count("<aside") == 1 and t.count('<div class="layout">') == 1, rel
        aside = t.split("<aside", 1)[1].split("</aside>", 1)[0]
        assert "zh-Hans" not in aside, rel
        for href in re.findall(r'href="([^"]*)"', aside):
            target, _, anchor = href.partition("#")
            if not target:                                   # 本页锚点只出现在首页
                assert rel == "index.html" and f'id="{anchor}"' in t, (rel, href)
                continue
            if target.startswith("/"):                       # 404 页在任意深度的地址返回,用站内绝对路径
                assert target.startswith("/zh-hant/"), (rel, href)
                path = target.removeprefix("/zh-hant/")
            else:
                path = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
            assert not path.startswith(".."), (rel, href)
            assert (hant / path).is_file(), (rel, href)
            if anchor:
                assert f'id="{anchor}"' in (hant / path).read_text(encoding="utf-8"), (rel, href)
        active = re.findall(r'class="nav-item[^"]*active"[^>]*><span class="glyph">.</span>([^<]*)<', aside)
        if rel in want:
            assert active == [want[rel]], (rel, active)
        elif rel.startswith("p/week/"):
            assert active == ["週彙總"], (rel, active)
        else:
            assert active == [], (rel, active)
