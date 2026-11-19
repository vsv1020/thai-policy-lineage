# -*- coding: utf-8 -*-
"""落地页开头那句话、标题与结构化数据只写本站核对过的事;汇总页的结构与描述;llms.txt 的索引。

背景:数据里的机关是模型从词表里选的,词表没有的机关会落到上级部委或缺省值「内阁」。Google 上点击最多的那个
落地页曾写着「内阁于 2026-02-19 在泰国皇家公报刊登《商品与服务安全委员会命令……》」—— 一句错话,
而这句正是 AI 摘答时最常引用的。"""
from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app import analytics as A, seo
from app.config import settings
from app.db import session_scope
from app.models import Document

SITE = settings.site_url
TH = seo.agency_th_names()


def _doc(uid, agencies, title_th="", gazette="", published=None, resolved=None, verified=False, sources=()):
    return NS(uid=uid, agencies=[NS(agency_id=a, seq=i) for i, a in enumerate(agencies)], title_th=title_th,
              gazette_series=gazette, published_at=published, resolved_at=resolved, verified=verified,
              sources=[NS(role="official", url=u) for u in sources])


def _lds(html: str) -> list[dict]:
    return [json.loads(x.replace("<\\/", "</"))
            for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


# ─────────────────────────── 机关一栏:能印证才叫「发文机关」 ───────────────────────────

def test_vocab_supplies_thai_agency_names():
    assert "กรมสรรพสามิต" in TH["excise"] and "คณะรัฐมนตรี" in TH["cabinet"]
    assert "เจ้าพนักงานจราจร" in TH["police"], "别名也算"
    assert all(len(n) >= 4 for names in TH.values() for n in names), "太短的缩写不用来印证"


@pytest.mark.parametrize("doc,org,want", [
    # 返回 (标签, 发文机关, 相关机关)。原先返回 (标签, 整串机关):标题只印证了其中一个时,整串都被写成发文者
    # —— 「消费税厅 · 海关厅于某日刊登《消费税厅关于……的规程》」。现在只把印证了的写成发文机关,其余另列相关机关。
    # 公报:泰文原题的发文机关段写着这个机关
    (_doc("TH-GAZ-1-A", ["excise"], "ระเบียบกรมสรรพสามิต ว่าด้วยการปฏิบัติ", "ง พิเศษ", date(2026, 4, 1)),
     "消费税厅", ("发文机关", "消费税厅", "")),
    (_doc("TH-GAZ-1-A2", ["excise", "customs"], "ระเบียบกรมสรรพสามิต ว่าด้วยการปฏิบัติ", "ง พิเศษ", date(2026, 4, 1)),
     "消费税厅 (EXCISE) · 海关厅 (CUSTOMS)", ("发文机关", "消费税厅 (EXCISE)", "海关厅 (CUSTOMS)")),
    # 公报:原题写的是别的机关(数据没重新归类),数据里落到缺省的「内阁」—— 整栏不显示
    (_doc("TH-GAZ-1-B", ["cabinet"], "คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง ยกเลิก",
          "ง พิเศษ", date(2026, 2, 19)), "内阁", ("", "", "")),
    (_doc("TH-GAZ-1-C", ["cabinet"], "คำวินิจฉัยของศาลรัฐธรรมนูญ ที่ 3/2569", "ก", date(2026, 4, 16)), "内阁", ("", "", "")),
    # 公报:归到了上级部委,原题印证不了 —— 只说是相关机关
    (_doc("TH-GAZ-1-D", ["mof"], "ประกาศกรมควบคุมโรค เรื่อง รายชื่อหน่วยงาน", "ง พิเศษ", date(2026, 3, 30)),
     "财政部", ("相关机关", "", "财政部")),
    (_doc("TH-GAZ-1-E", ["moi"], "กฎกระทรวงยกเว้นค่าธรรมเนียมการใช้ยานยนตร์บนทางหลวงพิเศษ", "ก", date(2026, 4, 1)),
     "内政部", ("相关机关", "", "内政部")),
    # 公报:第二个机关被原题印证 —— 原先整串「内政部 · 土地厅」都算发文机关;现在只有土地厅是,内政部列为相关机关
    (_doc("TH-GAZ-1-F", ["moi", "dol"], "ประกาศกรมที่ดิน เรื่อง กำหนด", "ง", date(2026, 3, 19)),
     "内政部 · 土地厅", ("发文机关", "土地厅", "内政部")),
    # 机关名出现在「เรื่อง」之后(正文里提到)不算
    (_doc("TH-GAZ-1-G", ["mof"], "ประกาศองค์การขนส่งมวลชนกรุงเทพ เรื่อง ผลการกู้เงินของกระทรวงการคลัง", "ง",
          date(2026, 2, 9)), "财政部", ("相关机关", "", "财政部")),
    # 附属实体(委员会 / 办公室)显示标题写的那一个
    (_doc("TH-GAZ-1-I", ["oic"], "ประกาศคณะกรรมการกำกับและส่งเสริมการประกอบธุรกิจประกันภัย เรื่อง ก", "ง",
          date(2026, 2, 9)), "保险业务监管与促进委员会办公室 (OIC)", ("发文机关", "保险业务监管与促进委员会", "")),
    # 官员职务称谓、前缀式别名只用于数据层归类,页面上不算标题印证的发文者
    (_doc("TH-GAZ-1-J", ["led"], "ประกาศเจ้าพนักงานพิทักษ์ทรัพย์ เรื่อง คำพิพากษาให้ลูกหนี้ล้มละลาย", "ง",
          date(2026, 3, 25)), "法律执行厅 (LED)", ("相关机关", "", "法律执行厅 (LED)")),
    (_doc("TH-GAZ-1-K", ["dol"], "ประกาศสำนักงานที่ดินจังหวัดชลบุรี สาขาศรีราชา เรื่อง การจดทะเบียนอาคารชุด", "ง",
          date(2026, 3, 25)), "土地厅 (DOL)", ("相关机关", "", "土地厅 (DOL)")),
    # 联合发文
    (_doc("TH-GAZ-1-L", ["opm", "moi"], "ประกาศสำนักนายกรัฐมนตรีและกระทรวงมหาดไทย เรื่อง ก", "ง", date(2026, 2, 26)),
     "总理府 (OPM) · 内政部 (MOI)", ("发文机关", "总理府 (OPM) · 内政部 (MOI)", "")),
    # 人工整理、没有泰文原题的条目:没有反证,第一个机关算发文者
    (_doc("TH-MOL-20250701-X", ["mol"], "", "ง", date(2025, 7, 1)), "劳工部", ("发文机关", "劳工部", "")),
    # 官网来源:第一个机关就是这个官网的机关 —— 原先整串都算,现在只有它算,其余列为相关机关
    (_doc("TH-BOI-20260715-1", ["boi", "energy"], "คำสั่ง กกท. ที่ 3/2569 เรื่อง แต่งตั้ง", "", date(2026, 7, 15)),
     "投资促进委员会 (BOI) · 能源部", ("发文机关", "投资促进委员会 (BOI)", "能源部")),
    # 官网来源:BOI 官网上转载的总理府命令,数据没重新归类(第一个机关是缺省的「内阁」)
    (_doc("TH-BOI-20260521-2", ["cabinet", "boi"], "คำสั่งสำนักนายกรัฐมนตรี ที่ 193/2569 เรื่อง แต่งตั้ง", "",
          date(2026, 5, 21)), "内阁 · 投资促进委员会 (BOI)", ("相关机关", "", "内阁 · 投资促进委员会 (BOI)")),
    # 官网来源:税务厅官网上的财政部公告,原题印证了财政部
    (_doc("TH-RD-20261029-3", ["mof"], "ประกาศกระทรวงการคลัง เรื่อง ขยายกำหนดเวลา", "", date(2026, 10, 29)),
     "财政部", ("发文机关", "财政部", "")),
    # 官网来源:税务厅官网转载的皇家法令 —— 皇家法令不是税务厅发的,不按官网机关写成发文者
    (_doc("TH-RD-20261001-DC806", ["rd"], "พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร (ฉบับที่ 806)",
          "", date(2026, 10, 1)), "税务厅 (RD)", ("相关机关", "", "税务厅 (RD)")),
    # 内阁决议:第一个机关是内阁才算,且只有内阁算发文者
    (_doc("TH-CABX-1", ["cabinet", "mof"], "ร่างกฎกระทรวง", "", None, date(2025, 3, 18)), "内阁 · 财政部",
     ("发文机关", "内阁", "财政部")),
    (_doc("TH-CABX-2", ["rd"], "ร่างกฎกระทรวง ฉบับที่ ..", "", None, date(2025, 3, 11)), "税务厅", ("相关机关", "", "税务厅")),
    # 人工复核过的条目照旧
    (_doc("TH-GAZ-1-H", ["cabinet"], "คำสั่งนายกรัฐมนตรี ที่ 2/2569", "ง", date(2026, 3, 6), verified=True),
     "内阁", ("发文机关", "内阁", "")),
])
def test_issuer_is_only_claimed_when_the_official_title_confirms_it(doc, org, want):
    assert seo.issuer_info(doc, org) == want


def test_source_site_needs_uid_and_link_domain_to_agree():
    zh = {"boi": "投资促进委员会", "rd": "税务厅"}
    boi = _doc("TH-BOI-20260521-2", ["cabinet", "boi"], sources=["https://www.boi.go.th/upload/x.pdf"])
    assert seo.source_site(boi, zh) == "投资促进委员会"
    assert seo.source_site(_doc("TH-BOI-1-X", ["boi"], sources=["https://www.rd.go.th/x.pdf"]), zh) == "", "域名对不上不说"
    assert seo.source_site(_doc("TH-BOI-1-X", ["boi"], sources=["https://evil.example/boi.go.th/x.pdf"]), zh) == ""
    assert seo.source_site(_doc("TH-RD-1-X", ["rd"], gazette="ก", sources=["https://www.rd.go.th/x.pdf"]), zh) == "", \
        "有公报卷期的条目不说「官网发布」"
    assert seo.source_site(_doc("TH-GAZ-1-X", ["rd"], sources=["https://ratchakitcha.soc.go.th/x.pdf"]), zh) == ""


# ─────────────────────────── 开头那句话 ───────────────────────────

def _view(**kw):
    v = {"org": "内阁", "title_zh": "某公告", "doc_no": "ง พิเศษ 143/47", "doc_no_label": "公报",
         "dates": {"published_at": "2026-02-19", "effective_from": "2026-02-19"}, "status_label": "已刊公报"}
    v.update(kw)
    return v


def test_lede_without_confirmed_issuer_does_not_name_one():
    title = "商品与服务安全委员会命令第2/2569号：取消销售禁令"
    s = seo._lede(_view(title_zh=title), gazetted=True, issuer=False)
    assert s == f"《{title}》(公报 ง พิเศษ 143/47)于 2026-02-19 在泰国皇家公报刊登,2026-02-19 起生效。当前状态:已刊公报。"
    assert "内阁" not in s
    s = seo._lede(_view(org="消费税厅 (EXCISE)", title_zh="消费税厅公告：某规定"), gazetted=True, issuer=True)
    assert s.startswith("消费税厅 (EXCISE) 于 2026-02-19 在泰国皇家公报刊登《消费税厅公告：某规定》")


def test_lede_for_agency_website_items():
    v = _view(org="内阁 · 投资促进委员会 (BOI)", title_zh="总理府命令第193/2569号", doc_no="",
              dates={"published_at": "2026-05-21"}, status_label="现行有效")
    assert seo._lede(v, gazetted=False, issuer=False, site="投资促进委员会") == \
        "《总理府命令第193/2569号》于 2026-05-21 在投资促进委员会官网发布。当前状态:现行有效。"
    assert seo._lede(v, gazetted=False, issuer=False) == "《总理府命令第193/2569号》于 2026-05-21 发布。当前状态:现行有效。"
    v = _view(org="税务厅 (RD)", title_zh="税务厅厅长公告", doc_no="", dates={"published_at": "2026-11-05"})
    assert seo._lede(v, gazetted=False).startswith("税务厅 (RD) 于 2026-11-05 发布《税务厅厅长公告》")


def test_lede_for_cabinet_resolution_does_not_say_passed():
    """内阁决议可能是批准,也可能只是听取报告;没读过决议正文不能写「通过」。"""
    v = _view(org="内阁 · 财政部 (MOF)", title_zh="2024年第三季度泰国经济状况与趋势报告", doc_no="412990", doc_no_label="文号",
              dates={"resolved_at": "2025-02-25"}, status_label="待刊公报")
    for issuer in (True, False):
        s = seo._lede(v, gazetted=False, issuer=issuer)
        assert s == "泰国内阁于 2025-02-25 就《2024年第三季度泰国经济状况与趋势报告》作出决议(文号 412990)。当前状态:待刊公报。"
        assert "通过" not in s and "财政部" not in s


def test_nested_book_title_marks():
    assert seo.book("最低工资公告") == "《最低工资公告》"
    assert seo.book("《清迈倡议多边化协议》(CMIM Agreement)修订版草案") == "《〈清迈倡议多边化协议〉(CMIM Agreement)修订版草案》"
    assert "《《" not in seo._lede(_view(title_zh="《证券法（修正案）》皇家法令草案"))


def test_key_points_with_clipped_beginnings_are_not_shown():
    """旧版清洗删掉了要点开头的数字(app.enrich 已改正);库里已有的那几十条在重新整理之前不展示。"""
    pts = ["年7月1日及以后建造的船舶须在证书中标注", "月11日至20日宋干节期间实施交通管制", "号线涵盖曼谷-芭提雅段",
           "级包括检查安全、制动", "级：年满15周岁", "个月定期存款年利率：自然人0.80%", "年 9 月 1 日起提交的申请适用本公告"]
    assert seo.sound_points(pts) == []
    ok = ["年利率0.85%，存款满5个月后本息转入", "月均须达标", "年度交易额占比超10%即触发", "2026年7月1日起施行",
          "7号线免收通行费", "个人存款不代扣所得税", "级别变更须在30日内完成", "年产值5亿泰铢以上的纳入适用范围"]
    assert seo.sound_points(ok) == ok
    assert seo.sound_points([]) == [] and seo.sound_points(None) == []


# ─────────────────────────── <title>:「泰国」写在最前面 ───────────────────────────

@pytest.mark.parametrize("title,cabinet,lead", [
    ("工业部公告：规定工业产品标准", False, "泰国"),
    ("关于收受和给予贿赂情形的反腐败措施", True, "泰国内阁决议:"),
    ("《清迈倡议多边化协议》(CMIM Agreement)修订版草案", True, "泰国内阁决议:"),
    ("泰国央行第18/2569号公告：金融机构客户金融服务使用风险管理准则", False, ""),
    ("泰王国政府与尼泊尔政府关于旅游合作的谅解备忘录", True, "泰国内阁决议:"),
    ("内阁决议复议：2025年4月8日内阁决议", True, "泰国"),
    ("内阁决议:终止 60 天免签", True, "泰国"),
    ("泰国中小企业发展银行贷款项目", True, "泰国内阁决议:"),
    ("2569年关于某些水生动物进口的部令", False, "泰国 "),
    ("BOI 新一轮投资促进措施", False, "泰国 "),
])
def test_title_lead(title, cabinet, lead):
    assert seo.title_lead(title, cabinet) == lead


def test_page_title_keeps_length_with_lead_and_date():
    t = seo.page_title("很" * 90, "2026-03-02", "泰国内阁决议:")
    assert t.startswith("泰国内阁决议:很") and t.endswith("…(2026-03-02) | 泰国政策") and len(t) <= 56
    assert seo.page_title("工业部公告", lead="泰国") == "泰国工业部公告 | 泰国政策"


# ─────────────────────────── 结构化数据:是否有效 ───────────────────────────

@pytest.mark.parametrize("status,in_force,eff,eff_to,want", [
    ("in_force", True, None, None, "InForce"),
    ("gazetted", False, date(2026, 2, 19), None, "InForce"),        # 已刊公报、生效日已到:页面写着「某日起生效」
    ("gazetted", False, date(2027, 1, 1), None, "NotInForce"),      # 还没到生效日
    ("gazetted", False, None, None, None),                          # 没有生效日:不声明
    ("gazetted", False, date(2026, 1, 1), date(2026, 6, 30), "NotInForce"),   # 过了失效日
    ("pending_gazette", False, None, None, "NotInForce"),
    ("draft", False, None, None, "NotInForce"),
    ("superseded", False, date(2025, 1, 1), None, "NotInForce"),
    ("repealed", False, date(2025, 1, 1), None, "NotInForce"),
])
def test_legal_force_follows_what_the_page_says(status, in_force, eff, eff_to, want):
    doc = NS(status_id=status, status=NS(in_force=in_force), effective_from=eff, effective_to=eff_to)
    assert seo.legal_force(doc, date(2026, 11, 18)) == want


# ─────────────────────────── 成品 ───────────────────────────

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("acc")
    (root / "data" / "site").mkdir(parents=True)
    mp = pytest.MonkeyPatch()
    mp.setattr(seo, "PAGES_DIR", root / "p")
    mp.setattr(seo, "REPO_ROOT", root)
    mp.setattr(seo, "SITE_DIR", root / "data" / "site")
    mp.setattr(seo, "ADS_CONFIG", root / "none.json")
    with session_scope() as s:
        seo.build(s)
    yield root
    mp.undo()


def test_unconfirmed_issuer_on_landing_page(site):
    """测试数据里的 TH-GAZ-20260401-2569:泰文原题是「กฎกระทรวง……」(没写机关),数据里归到财政部。"""
    for base, lede_tail, label, site_name in ((site / "p", "在泰国皇家公报刊登", "相关机关", "泰国政策"),
                                              (site / "zh-hant" / "p", "在泰國皇家公報刊登", "相關機關", "泰國政策")):
        html = (base / "th-gaz-20260401-2569.html").read_text(encoding="utf-8")
        lede = re.search(r'<p class="lede">(.*?)</p>', html).group(1)
        assert lede.startswith("《") and lede.endswith("。") and f" 2026-04-01 {lede_tail}" in lede, lede
        assert f'<div class="k">{label}</div>' in html and f"<dt>{label}</dt>" in html
        assert '<div class="k">发文机关</div>' not in html and '<div class="k">發文機關</div>' not in html
        leg = next(x for x in _lds(html) if x["@type"] == "Legislation")
        assert "legislationPassedBy" not in leg, "印证不了的机关不写进结构化数据"
        assert "legislationLegalForce" not in leg, "已刊公报但没有生效日:不声明是否有效"
        assert re.search(r"<title>泰[国國]", html) and site_name in html
    # 原题印证了机关的条目照旧
    html = (site / "p" / "th-gaz-20260401-2-2569.html").read_text(encoding="utf-8")
    assert "消费税厅 (EXCISE) 于 2026-04-01 在泰国皇家公报刊登《" in html and '<div class="k">发文机关</div>' in html
    leg = next(x for x in _lds(html) if x["@type"] == "Legislation")
    assert leg["legislationPassedBy"]["name"] == "消费税厅 (EXCISE)"


def test_cabinet_resolution_landing_page(site):
    html = (site / "p" / "th-cab-20260519-visafree-30d.html").read_text(encoding="utf-8")
    assert "<title>泰国内阁决议:终止" in html, "标题本身以「内阁决议」开头,只补「泰国」"
    lede = re.search(r'<p class="lede">(.*?)</p>', html).group(1)
    assert lede.startswith("泰国内阁于 2026-05-19 就《内阁决议:终止") and "作出决议" in lede and "经内阁决议通过" not in html
    leg = next(x for x in _lds(html) if x["@type"] == "Legislation")
    assert leg["legislationLegalForce"] == "NotInForce" and leg["legislationPassedBy"]["name"].startswith("内阁")


def test_every_landing_title_leads_with_thailand(site):
    for base, word in ((site / "p", "泰国"), (site / "zh-hant" / "p", "泰國")):
        pages = [p for p in base.glob("th-*.html")]
        assert pages
        for p in pages:
            title = re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8")).group(1)
            assert title.startswith(word), (p.name, title)
    with session_scope() as s:
        zh = s.scalars(select(Document).where(Document.uid == "TH-MOL-20250701-MINWAGE-14")).one().title_zh
    h = (site / "p" / "th-mol-20250701-minwage-14.html").read_text(encoding="utf-8")
    assert f'<h1 class="d-title">{seo.e(zh)}</h1>' in h and not zh.startswith("泰国"), "H1 是标题原样,不加限定语"


def test_legal_force_in_structured_data_matches_page(site):
    """现行有效或已到生效日的写 InForce;页面正文说「某日起生效」而结构化数据说 NotInForce 就是自相矛盾。"""
    with session_scope() as s:
        today = A._today(s)
        docs = {d.uid.lower(): (d.status_id, d.status.in_force, d.effective_from, d.effective_to)
                for d in s.scalars(select(Document)).all()}
    seen = set()
    for p in (site / "p").glob("th-*.html"):
        leg = next(x for x in _lds(p.read_text(encoding="utf-8")) if x["@type"] == "Legislation")
        st, in_force, eff, eff_to = docs[p.stem]
        force = leg.get("legislationLegalForce")
        seen.add(force)
        if in_force and not (eff_to and eff_to < today):
            assert force == "InForce", p.name
        if st == "gazetted" and not eff:
            assert force is None, p.name
    assert "InForce" in seen


# ─────────────────────────── 汇总页:最新若干条带摘要,其余列标题 ───────────────────────────

def _items(n: int, party: str = "") -> list[dict]:
    return [{"uid": f"TH-GAZ-2026{i // 28 + 1:02d}{i % 28 + 1:02d}-X{i}" if i < 40 else f"TH-GAZ-20250101-X{i}",
             "title": f"标题{i}", "date": f"2026-{i // 28 + 1:02d}-{i % 28 + 1:02d}" if i < 40 else "2025-01-01",
             "org": "工业部" if i % 2 else "", "doc_no": f"ง 143/{i}", "summary": f"摘要{i}。",
             "points": [f"要点{i}"], "official": f"https://ratchakitcha.soc.go.th/documents/{i}.pdf",
             "url": f"{SITE}/p/x{i}.html", "parties": [{"id": party, "stance": "constrain"}] if party else []}
            for i in range(n)]


def test_large_collection_page_is_split():
    n = seo.COLL_LATEST + seo.COLL_KEEP_WHOLE + 25
    html = seo.render_collection(f"{SITE}/p/who/x.html", "影响某某的泰国政策汇总 | 站", "影响「某某」的泰国政策",
                                 "收录本站标注为影响「某某」的公报与决议(含约束与利好)。", _items(n, "x"), "影响对象 / 某某",
                                 party="x", desc_lead="影响某某的泰国政策汇总:")
    assert html.count('class="coll-item"') == seo.COLL_LATEST, "只有最新若干条带摘要"
    assert html.count("泰文原文 ↗") == seo.COLL_LATEST
    assert f"更早的 {n - seo.COLL_LATEST} 条" in html and html.count('class="lib-row"') == n - seo.COLL_LATEST
    assert '<h3 class="coll-title">' in html and '<h2 class="coll-title">' not in html, "分了节,条目标题降一级"
    assert 'id="y2026"' in html and 'id="y2025"' in html and 'href="#y2025"' in html
    for i in range(n):                       # 每一条都还在页面上,链到自己的落地页
        assert html.count(f">标题{i}</a>") == 1, i
    assert html.count('<span class="party constrain">约束</span>') == n, "目录里也标出约束 / 利好"
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert desc.startswith("影响某某的泰国政策汇总:收录") and f"共 {n} 条" in desc and "。 共" not in desc
    assert "· ·" not in html and " ·  · " not in html, "没有机关的条目不留空的分隔符"
    ld = _lds(html)[0]
    assert ld["mainEntity"]["numberOfItems"] == n


def test_small_collection_page_stays_whole():
    n = seo.COLL_LATEST + seo.COLL_KEEP_WHOLE
    html = seo.render_collection(f"{SITE}/p/t/x.html", "泰国某专题:历次公报汇总 | 站", "泰国某专题:历次公报汇总",
                                 "收录标题涉及某某的公报。", _items(n), "专题 / 某专题", desc_lead="泰国某专题:")
    assert html.count('class="coll-item"') == n and "更早的" not in html and 'class="lib-row"' not in html
    assert '<h2 class="coll-title">' in html and "以下逐条摘录本站已收录条目的中文摘要" in html
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert desc.startswith("泰国某专题:收录标题涉及某某的公报。共 ")


def test_collection_descriptions_name_thailand_and_topic(site):
    coll = json.loads((site / "data" / "site" / "collections.json").read_text(encoding="utf-8"))
    assert coll["who"]
    for x in coll["who"]:
        html = (site / x["href"]).read_text(encoding="utf-8")
        desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        assert desc.startswith(f"影响{x['zh']}的泰国政策汇总:"), desc


def test_hub_pages_with_visible_breadcrumbs_declare_them(site):
    """专题页、影响对象页、周汇总页面上都有面包屑,结构化数据里也写上(领域页、落地页、指南页原来就有)。"""
    coll = json.loads((site / "data" / "site" / "collections.json").read_text(encoding="utf-8"))
    week = next(p for p in (site / "p" / "week").glob("2*.html"))
    pages = [(site / coll["who"][0]["href"], 3), (week, 4), (site / "p" / "week" / "index.html", 3)]
    for root, prefix in ((site, SITE), (site / "zh-hant", f"{SITE}/zh-hant")):
        for path, depth in pages:
            f = root / path.relative_to(site)
            html = f.read_text(encoding="utf-8")
            assert '<div class="crumb">' in html
            bc = next(x for x in _lds(html) if x["@type"] == "BreadcrumbList")["itemListElement"]
            assert [x["position"] for x in bc] == list(range(1, depth + 1))
            assert bc[0]["item"] == f"{prefix}/" and bc[1]["item"] == f"{prefix}/p/index.html"
            canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
            assert bc[-1]["item"] == canonical and all(x["item"].startswith(prefix) for x in bc)
            page = next(x for x in _lds(html) if x["@type"] == "CollectionPage")
            assert page["url"] == canonical


# ─────────────────────────── llms.txt ───────────────────────────

def test_llms_index_says_what_each_hub_page_covers(site):
    llms = (site / "llms.txt").read_text(encoding="utf-8")
    line = next(x for x in llms.splitlines() if "/p/topic/tax.html" in x)
    assert seo.DOMAIN_SCOPE["tax"] in line and re.search(r"\d+ 条,最新 \d{4}-\d\d-\d\d$", line), line
    who = next(x for x in llms.splitlines() if "/p/who/" in x)
    assert "含约束与利好" in who and "最新 " in who
    assert "- 怎么找:" in llms and "llms-full.txt" in llms


def test_llms_latest_entries_are_cut_at_sentence_end():
    long = "第一句话写得比较长" * 6 + "。" + "第二句话" * 30 + "。"
    e = {"uid": "U", "title": "标题", "title_th": "", "url": f"{SITE}/p/u.html", "date": "2026-01-01", "domain": "税务",
         "domain_id": "tax", "parties": [], "doc_no": "", "summary": long, "points": [], "status": "已刊公报",
         "official": "https://www.rd.go.th/x.pdf", "effective": "", "parties_zh": [], "org": "", "org_label": ""}
    llms = seo.render_llms([e], [("tax", "税务", 1)])
    line = next(x for x in llms.splitlines() if "/p/u.html" in x)
    assert line.endswith("第一句话写得比较长" * 6 + "。"), "停在句末,不拦腰截断"


def test_llms_full_uses_the_same_agency_label():
    base = {"uid": "U", "title": "标题", "title_th": "", "url": f"{SITE}/p/u.html", "date": "2026-01-01", "domain": "税务",
            "domain_id": "tax", "parties": [], "doc_no": "", "summary": "摘要。", "points": [], "status": "已刊公报",
            "official": "https://www.rd.go.th/x.pdf", "effective": "", "parties_zh": []}
    full = seo.render_llms([{**base, "org": "财政部", "org_label": "相关机关"}], [], full=True)
    assert "- 相关机关:财政部" in full and "- 发文机关:" not in full
    full = seo.render_llms([{**base, "org": "", "org_label": ""}], [], full=True)
    assert "机关:" not in full
