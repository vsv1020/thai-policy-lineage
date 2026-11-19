# -*- coding: utf-8 -*-
"""从泰文标题认发文机关(app.issuer,app.enrich 与 app.seo 共用)与机关词表的完整性。

原则:宁可认不出,不要认错。认错的后果是落地页开头那句「某机关于某日在皇家公报刊登……」写成一句错话,
数据层的 agency_ids 也跟着错。"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace as NS

import pytest

from app import enrich as E, issuer as I, seo
from app.config import DATA_DIR

V = E._vocab()
RULES = I.agency_rules(V)
AG = {a["id"]: a for a in V["agencies"]}


def ids(th):
    return E.issuer_agencies(th, V)


# ─────────────────────────── 名字里含「ว่าด้วย」的委员会 ───────────────────────────

@pytest.mark.parametrize("th,want", [
    ("คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง ยกเลิกการห้ามขายสินค้า", ["ocpb_safety"]),
    ("ประกาศคณะกรรมการกลางว่าด้วยราคาสินค้าและบริการ ฉบับที่ 4 พ.ศ. 2569 เรื่อง การกำหนดสินค้าควบคุมเพิ่มเติม", ["ccp"]),
    # 办公室的名字包含委员会的名字:长名优先
    # (办公室在页面上显示自己的中文名,见 test_attached_entities_show_their_own_name)
    ("ประกาศสำนักงานคณะกรรมการกลางว่าด้วยราคาสินค้าและบริการ ฉบับที่ 1 พ.ศ. 2569 เรื่อง การแก้ไขเพิ่มเติมแบบแจ้ง",
     ["ccp"]),
    ("ประกาศคณะกรรมการว่าด้วยสัญญา เรื่อง ยกเลิกประกาศคณะกรรมการว่าด้วยสัญญา", ["ocpb_contract"]),
    # 词表里没有的「委员会 + ว่าด้วย」:照旧在 ว่าด้วย 处截断,认不出
    ("ประกาศคณะกรรมการว่าด้วยการโฆษณา เรื่อง การโฆษณาอาหาร", []),
])
def test_committee_names_containing_waduai(th, want):
    assert ids(th) == want


def test_most_clicked_page_issuer_is_the_safety_committee():
    """全站 Google 点击最多的落地页(p/th-gaz-20260219-2-2569-uvc.html)。"""
    th = "คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง ยกเลิกการห้ามขายสินค้าหรืออุปกรณ์ที่มีรังสี UVC"
    doc = NS(uid="TH-GAZ-20260219-2-2569-UVC", agencies=[NS(agency_id="ocpb_safety", seq=0)], title_th=th,
             gazette_series="ง พิเศษ", published_at=None, resolved_at=None, verified=False, sources=[])
    assert seo.issuer_info(doc, "商品与服务安全委员会") == ("发文机关", "商品与服务安全委员会", "")
    assert AG["ocpb_safety"]["zh"] == "商品与服务安全委员会"


# ─────────────────────────── 别名、府级 / 分支机构 ───────────────────────────

@pytest.mark.parametrize("th,want", [
    ("ประกาศสำนักงานที่ดินจังหวัดชลบุรี สาขาศรีราชา เรื่อง การจดทะเบียนนิติบุคคลอาคารชุด", ["dol"]),
    ("ประกาศสำนักงานที่ดินจังหวัดภูเก็ต เรื่อง การจดทะเบียนอาคารชุด", ["dol"]),
    # 曼谷土地办公室属土地厅,不是曼谷市(原先认成 bma)
    ("ประกาศสำนักงานที่ดินกรุงเทพมหานคร สาขาพระโขนง เรื่อง การจดทะเบียนอาคารชุด", ["dol"]),
    ("ประกาศสำนักงานประมงจังหวัดประจวบคีรีขันธ์ เรื่อง กำหนดห้วงเวลา", ["dof"]),
    ("ประกาศคณะกรรมการควบคุมการขนส่งทางบกประจำจังหวัดภูเก็ต ฉบับที่ 37 (พ.ศ. 2568) เรื่อง กำหนดเส้นทาง", ["ltcb"]),
    ("ประกาศสำนักงานกลางทะเบียนสมาคมการค้า ที่ 22/2568 เรื่อง อนุญาตให้จัดตั้งสมาคมการค้า", ["dbd"]),
    ("ประกาศสำนักงานทะเบียนหุ้นส่วนบริษัทกลาง เรื่อง การยื่นคำขอจดทะเบียน", ["dbd"]),
    # 委员会本身与其办公室
    ("ประกาศคณะกรรมการส่งเสริมการลงทุน ที่ 1/2569 เรื่อง มาตรการรักษาและขยายฐานการผลิต", ["boi"]),
    ("ประกาศสำนักงานคณะกรรมการส่งเสริมการลงทุน ที่ ป. 1/2569 เรื่อง", ["boi"]),
    ("ระเบียบคณะกรรมการกำกับกิจการพลังงาน ว่าด้วยการแบ่งส่วนงาน", ["erc"]),
    ("สำนักงานคณะกรรมการการเลือกตั้ง ขอแก้ไขข้อความคลาดเคลื่อน ระเบียบคณะกรรมการการเลือกตั้ง ว่าด้วย", ["ect"]),
    ("ระเบียบสำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล ว่าด้วยการตรวจสอบ", ["pdpc"]),
    ("ประกาศคณะกรรมการการนิคมอุตสาหกรรมแห่งประเทศไทย เรื่อง การจัดตั้งนิคมอุตสาหกรรม", ["ieat"]),
    # 文件类型后面的「ของ」与署名职务
    ("ข้อบังคับของคณะกรรมการการบินพลเรือน ฉบับที่ 105 ว่าด้วยการอนุญาตประกอบกิจการการบินพลเรือน", ["cab"]),
    ("คำวินิจฉัยของศาลรัฐธรรมนูญ คำวินิจฉัยที่ 3/2569 เรื่อง ประมวลกฎหมายยาเสพติด", ["ccourt"]),
    ("ประกาศอธิบดีกรมสรรพากร เกี่ยวกับภาษีเงินได้ (ฉบับที่ 467) เรื่อง กำหนดหลักเกณฑ์", ["rd"]),
    ("คำสั่งนายกรัฐมนตรี ที่ ๖/๒๕๖๙ เรื่อง กำหนดมาตรการเพื่อแก้ไขและป้องกันภาวะการขาดแคลนน้ำมันเชื้อเพลิง", ["pm"]),
    ("ประกาศสำนักนายกรัฐมนตรี เรื่อง แผนปฏิบัติการส่งเสริมวิสาหกิจขนาดกลางและขนาดย่อม", ["opm"]),
    # 空格与拆开写的「ํา」不影响
    ("ประกาศกระทรวงการอุดมศึกษา  วิทยาศาสตร์ วิจัย และนวัตกรรม เรื่อง ทักษะที่พึงประสงค์", ["mhesi"]),
    ("ประกาศคณะกรรมการกําหนดมาตรฐานด้านการตรวจสอบและรับรอง ฉบับที่ ๑ (พ.ศ. ๒๕๖๙)", ["cas_committee"]),
    # 联合发文:按标题顺序全部列出
    ("ประกาศสำนักนายกรัฐมนตรีและกระทรวงมหาดไทย เรื่อง กำหนดจำนวนคนต่างด้าว", ["opm", "moi"]),
    ("ประกาศกระทรวงยุติธรรมและกระทรวงการคลัง เรื่อง แต่งตั้งพนักงานเจ้าหน้าที่", ["moj", "mof"]),
])
def test_aliases_branches_and_joint_issuers(th, want):
    assert ids(th) == want


# ─────────────────────────── 不该认的认不出 ───────────────────────────

@pytest.mark.parametrize("th", [
    "ประกาศนายทะเบียน เรื่อง กำหนดอัตราคิดลดมูลค่าทรัพย์สิน (Haircut)",       # 哪部法律的登记官?说不清
    "คำสั่งคณะกรรมการ ที่ 1/2569 เรื่อง แต่งตั้งอนุกรรมการ",                      # 单独的「委员会」
    "ประกาศ เรื่อง การให้ประกาศและคำสั่งที่นายกรัฐมนตรีกำหนดตามประกาศสถานการณ์ฉุกเฉินที่มีความร้ายแรงยังคงมีผลใช้บังคับ",
    "ประกาศตามมาตรา ๑๑ ของพระราชกำหนดการบริหารราชการในสถานการณ์ฉุกเฉิน พ.ศ. ๒๕๔๘",
    "ประกาศคณะกรรมการประจำจังหวัดชัยนาท เรื่อง หลักเกณฑ์การออกหนังสือรับรอง",
    "ประกาศผู้อำนวยการทางหลวงท้องถิ่น เรื่อง ห้ามใช้ยานพาหนะ",
    "คำสั่งรองนายกรัฐมนตรี ที่ 1/2569 เรื่อง มอบหมายงาน",                        # 副总理不是总理
    # 词表里没有的厅局后面跟着上级部委:不把上级部委当发文者
    "ประกาศกรมสมมุติ กระทรวงสาธารณสุข เรื่อง ทดสอบ",
    # 部令、皇家法令没有发文机关段,后面出现的机关名是事由
    "กฎกระทรวงแบ่งส่วนราชการกรมวิชาการเกษตร กระทรวงเกษตรและสหกรณ์ พ.ศ. ๒๕๖๙",
    "กฎกระทรวงการอนุญาตนำสุราเข้ามาในราชอาณาจักร (ฉบับที่ 3) พ.ศ. 2569",
    "พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร (ฉบับที่ 806) พ.ศ. 2569",
    "พระราชกฤษฎีกาจัดตั้งสำนักงานเทคโนโลยีและนวัตกรรมด้านชีววิทยาศาสตร์ (องค์การมหาชน) พ.ศ. 2569",
    # 机关名出现在「เรื่อง」之后
    "ประกาศ เรื่อง ผลการกู้เงินของกระทรวงการคลัง",
    "",
])
def test_generic_or_unnamed_issuers_are_not_recognised(th):
    assert ids(th) == [] and E.issuer_agency(th, V) is None


def test_issuer_head_keeps_committee_name_whole():
    th = "คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง ยกเลิก"
    assert I.issuer_head(th, RULES) == "คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการที่2/2569"
    assert I.issuer_head("ประกาศคณะกรรมการว่าด้วยการโฆษณา เรื่อง ก", RULES) == "ประกาศคณะกรรมการ"
    assert I.issuer_head("เรื่อง ก", RULES) == "" and I.issuer_head("", RULES) == ""


def test_page_and_data_layers_share_the_same_rules():
    """页面层(analytics.attribution 读词表文件)与数据层(enrich)是同一套规则。"""
    rules, parents = I.vocab_rules(DATA_DIR / "vocab.json")
    assert rules == RULES == E.agency_rules(V)
    assert parents == {a["id"]: a["ministry"] for a in V["agencies"]}


# ─────────────────────────── fix_agency ───────────────────────────

def _rec(th, agencies, pipeline="gazette_json"):
    return {"uid": "U", "titles": {"th": th}, "agency_ids": list(agencies), "provenance": {"pipeline": pipeline}}


def test_fix_agency_sets_joint_issuers_and_keeps_extra_agencies():
    r = _rec("ประกาศสำนักนายกรัฐมนตรีและกระทรวงมหาดไทย เรื่อง ก", ["moi"])
    assert E.fix_agency(r, V) and r["agency_ids"] == ["opm", "moi"]
    r = _rec("ประกาศกรมสรรพากร เรื่อง ก", ["rd", "mof"])
    assert not E.fix_agency(r, V) and r["agency_ids"] == ["rd", "mof"], "已以发文机关开头的不动"
    r = _rec("กฎกระทรวงแบ่งส่วนราชการกรมวิชาการเกษตร กระทรวงเกษตรและสหกรณ์", ["moac"])
    assert not E.fix_agency(r, V) and r["agency_ids"] == ["moac"], "认不出的不动"
    r = _rec("คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง ก", ["cabinet"])
    assert E.fix_agency(r, V) and r["agency_ids"] == ["ocpb_safety"]


def test_new_items_get_issuer_through_apply_enrichment():
    """每日流程:模型只能在词表里选,选了上级部委或内阁;apply_enrichment 末尾的 fix_agency 按标题改正。"""
    from tests.test_enrich import GOOD, _raw
    rec = _raw(th="ประกาศคณะกรรมการกำหนดมาตรฐานด้านการตรวจสอบและรับรอง ฉบับที่ ๒ (พ.ศ. ๒๕๖๙) ออกตามความใน")
    out = E.apply_enrichment(rec, {**GOOD, "agency_ids": ["industry"]}, V, "m")
    assert out["agency_ids"] == ["cas_committee"]


def test_fix_agencies_is_rerunnable(tmp_path, monkeypatch):
    d = tmp_path / "policies"; d.mkdir()
    monkeypatch.setattr(E, "POLICIES_DIR", d)
    rows = [_rec("ประกาศสำนักงานที่ดินจังหวัดชลบุรี เรื่อง ก", ["cabinet"]),
            {**_rec("ประกาศกรมสรรพากร เรื่อง ก", ["rd"]), "uid": "U2"},
            {**_rec("ประกาศสำนักงานที่ดินจังหวัดชลบุรี เรื่อง ก", ["cabinet"], "manual"), "uid": "U3"}]
    (d / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    assert E.fix_agencies(dry_run=True) == {"changed": 1}
    assert json.loads((d / "documents.jsonl").read_text().splitlines()[0])["agency_ids"] == ["cabinet"], "dry-run 不写"
    assert E.fix_agencies() == {"changed": 1}
    assert E.fix_agencies() == {"changed": 0}, "重跑无改动"
    out = [json.loads(x) for x in (d / "documents.jsonl").read_text().splitlines()]
    assert [r["agency_ids"] for r in out] == [["dol"], ["rd"], ["cabinet"]]


# ─────────────────────────── 词表完整性 ───────────────────────────

def test_agency_ids_unique_and_parents_exist():
    all_ids = [a["id"] for a in V["agencies"]]
    assert len(all_ids) == len(set(all_ids))
    for a in V["agencies"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", a["id"]), a["id"]
        assert set(a) <= {"id", "zh", "th", "abbr", "ministry", "th_aliases"}, a["id"]
        assert a["zh"].strip() and a["th"].strip(), a["id"]
        assert a["ministry"] is None or a["ministry"] in AG, (a["id"], a["ministry"])
        assert a["ministry"] != a["id"]
        assert a["abbr"] == "" or not re.search(r"\s", a["abbr"]), a["id"]
    for a in V["agencies"]:                     # 上级链条不成环
        seen, cur = set(), a["id"]
        while cur:
            assert cur not in seen, a["id"]
            seen.add(cur)
            cur = AG[cur]["ministry"]


def test_thai_names_unique_and_never_swallowed_by_another_agency():
    """每个泰文名 / 别名只属于一个机关;把任何一个名字当发文机关写进标题,认出来的都是它自己 ——
    一个名字是另一个机关名字的开头(「คณะกรรมการกลางว่าด้วย…」与「สำนักงานคณะกรรมการกลางว่าด้วย…」、
    「คณะกรรมการการบินพลเรือน」与别的名字)时,靠长名优先挡住。"""
    owner: dict[str, str] = {}
    for a in V["agencies"]:
        for x in I.alias_entries(a):
            n, k = x["th"], I.norm(x["th"])
            assert k not in owner or owner[k] == a["id"], (n, owner.get(k), a["id"])
            owner[k] = a["id"]
            if len(k) >= I.MIN_NAME:
                for doc in ("ประกาศ", "คำสั่ง", "ระเบียบ"):
                    assert ids(f"{doc}{n} เรื่อง ทดสอบ") == [a["id"]], (doc, n)
                    if x.get("prefix"):
                        assert ids(f"{doc}{n}ภูเก็ต สาขาถลาง เรื่อง ทดสอบ") == [a["id"]], (doc, n)
    zh = [a["zh"] for a in V["agencies"]] + [x["zh"] for a in V["agencies"] for x in I.alias_entries(a) if x.get("zh")]
    assert len(zh) == len(set(zh)), "中文名(含附属实体的显示名)不重复"


def test_no_alias_is_a_bare_generic_word():
    generic = {"คณะกรรมการ", "สำนักงาน", "นายทะเบียน", "กรม", "กระทรวง", "จังหวัด", "สภา", "ศาล", "ประกาศ"}
    for a in V["agencies"]:
        for x in I.alias_entries(a):
            assert I.norm(x["th"]) not in generic, (a["id"], x)
            assert set(x) <= {"th", "zh", "prefix", "official"}, (a["id"], x)


def test_org_name_shows_ascii_abbr_only():
    from app.analytics import document_view  # noqa: F401 —— 只确认 abbr 的写法符合 org_name 的规则
    for a in V["agencies"]:
        ab = a["abbr"].replace("-", "")
        assert ab == "" or (ab.isascii() and ab.isalpha()) or a["id"] in ("cabinet", "etda", "erc", "eec"), a["id"]


def test_vocab_file_is_the_one_read():
    assert json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8")) == V


# ─────────────────────────── 第二轮审阅:边界、职务前缀、并列、写法归一 ───────────────────────────

@pytest.mark.parametrize("th", [
    # 机关名之后没有边界:是另一个(地方 / 府级)机关
    "ประกาศคณะกรรมการการเลือกตั้งประจำองค์การบริหารส่วนตำบลบ้านฝาง เรื่อง ผลการเลือกตั้ง",
    "ประกาศคณะกรรมการควบคุมโรคจากการประกอบอาชีพและโรคจากสิ่งแวดล้อมจังหวัดระยอง เรื่อง ก",
    "ประกาศคณะกรรมการว่าด้วยสัญญาณเตือนภัย เรื่อง ก",
    # 总理、内阁不接受署名职务前缀:总理秘书长、内阁秘书长是各自的秘书处
    "ประกาศเลขาธิการนายกรัฐมนตรี เรื่อง ก",
    "ประกาศเลขาธิการคณะรัฐมนตรี เรื่อง ก",
    "ประกาศผู้อำนวยการนายกรัฐมนตรี เรื่อง ก",
    # 联合发文不完整:「และ」后面认不出;三家并列不带「และ」
    "ประกาศกระทรวงการคลังและกรมสมมุติ เรื่อง ก",
    "ประกาศกระทรวงการคลัง กระทรวงพาณิชย์ และกระทรวงมหาดไทย เรื่อง ก",
])
def test_boundaries_title_prefixes_and_incomplete_joint_issuers(th):
    assert ids(th) == []


@pytest.mark.parametrize("th,want", [
    ("ประกาศกระทรวงการคลัง ฉบับที่ 3 เรื่อง ก", ["mof"]),
    ("ประกาศกระทรวงการคลัง(ฉบับที่ 3) เรื่อง ก", ["mof"]),
    ("ประกาศกระทรวงการคลังเรื่อง ก", ["mof"]),
    ("ประกาศกระทรวงการคลัง", ["mof"]),
    ("ประกาศกรมสรรพากร กระทรวงการคลัง เรื่อง ก", ["rd"]),                 # 署名带上级部委,只取厅局
    ("ประกาศกระทรวงการคลัง และกระทรวงพาณิชย์ เรื่อง ก", ["mof", "moc"]),
    ("เทศบัญญัติเทศบาลนครเชียงใหม่ เรื่อง ก", ["local"]),
    ("ประกาศผู้ว่าการการไฟฟ้าฝ่ายผลิตแห่งประเทศไทย เรื่อง ก", ["egat"]),
    # 写法归一:零宽字符、「ํา」夹声调符、「เเ」、声调符与元音的顺序
    ("ประกาศกระทรวง\u200bการ\u200cคลัง\ufeff เรื่อง ก", ["mof"]),
    ("ประกาศการประปาส่วนภูมิภาค เรื่อง ค่านํ้า", ["pwa"]),
    ("ประกาศกรมส่งเสริมวัฒนธรรม เรื่อง ก", ["dcp"]),
    ("ประกาศกรมท\u0e48\u0e35ดิน เรื่อง ก", ["dol"]),                                  # ท่ี(声调符在元音前)
    ("ประกาศกรมส\u0e48\u0e07เสริมและพัฒนาคุณภาพชีวิตคนพิการ เรื่อง ก", ["dep"]),
    ("ประกาศคณะกรรมการบริหารกองทุนเพื่อผู้ใช้\u0e40\u0e40รงงาน เรื่อง ก", ["labour_fund"]),    # เเ 代 แ
])
def test_boundary_tokens_qualifiers_and_normalisation(th, want):
    assert ids(th) == want


def test_thai_normalisation_details():
    assert I.norm("น\u0e4d\u0e49\u0e32") == "น\u0e49\u0e33", "ํ้า → ้ำ"
    assert I.norm("น\u0e49\u0e4d\u0e32") == "น\u0e49\u0e33"
    assert I.norm("\u0e40\u0e40ก") == "\u0e41ก", "เเ → แ"
    assert I.norm("ก\u0e48\u0e34") == "ก\u0e34\u0e48", "声调符在上元音之后"
    assert I.norm("ก\u0e49\u0e38") == "ก\u0e38\u0e49", "声调符在下元音之后"
    assert I.norm("ก\u200bข\u200dค\u2060ง\ufeff จ") == "กขคงจ"


def test_bare_title_only_without_cabinet_data():
    th = "สำนักงานคณะกรรมการการเลือกตั้ง ขอแก้ไขข้อความคลาดเคลื่อน ระเบียบคณะกรรมการการเลือกตั้ง ว่าด้วย"
    assert I.issuer_agencies(th, RULES) == ["ect"]
    assert I.issuer_agencies(th, RULES, allow_bare=False) == []


def test_attached_entities_show_their_own_name():
    """页面上显示的机关名与标题写的是同一个实体:委员会的办公室发的公告不显示成委员会发的,反之亦然。"""
    zh = {a["id"]: a["zh"] for a in V["agencies"]}
    cases = [
        ("ประกาศคณะกรรมการกำกับและส่งเสริมการประกอบธุรกิจประกันภัย เรื่อง ก", "oic", "保险业务监管与促进委员会"),
        ("ประกาศสำนักงานคณะกรรมการกำกับและส่งเสริมการประกอบธุรกิจประกันภัย เรื่อง ก", "oic", "保险业务监管与促进委员会办公室"),
        ("ประกาศสำนักงานคณะกรรมการการเลือกตั้ง เรื่อง ก", "ect", "选举委员会办公室"),
        ("ประกาศคณะกรรมการการเลือกตั้ง เรื่อง ก", "ect", "选举委员会"),
        ("ประกาศสำนักงานคณะกรรมการส่งเสริมการลงทุน ที่ ป. 1/2569 เรื่อง ก", "boi", "投资促进委员会办公室"),
        ("ประกาศคณะกรรมการส่งเสริมการลงทุน ที่ 1/2569 เรื่อง ก", "boi", "投资促进委员会"),
        ("ประกาศสำนักงานคณะกรรมการกลางว่าด้วยราคาสินค้าและบริการ ฉบับที่ 1 เรื่อง ก", "ccp", "商品与服务价格中央委员会办公室"),
        ("ประกาศคณะกรรมการควบคุมการขนส่งทางบกกลาง เรื่อง ก", "ltcb", "陆路运输管制中央委员会"),
        ("ประกาศคณะกรรมการจัดสรรที่ดินกลาง เรื่อง ก", "land_alloc", "土地分配中央委员会"),
        ("ประกาศสำนักงานกลางทะเบียนสมาคมการค้า ที่ 22/2568 เรื่อง ก", "dbd", "贸易协会中央登记处"),
        ("ประกาศคณะกรรมการอ้อยและน้ำตาลทราย เรื่อง ก", "ocsb", "甘蔗与砂糖委员会"),
        ("ประกาศสำนักงานศาลรัฐธรรมนูญ เรื่อง ก", "ccourt", "宪法法院办公室"),
    ]
    for th, aid, want in cases:
        assert I.attribute(th, [aid], zh, RULES, gazette=True) == ("发文机关", [want], []), th


def test_prefix_and_official_aliases_are_data_only():
    """府级 / 分支机构的前缀式别名、官员职务称谓:数据层归到所属机关,页面上只算相关机关。"""
    zh = {a["id"]: a["zh"] for a in V["agencies"]}
    for th, aid in [("ประกาศคณะกรรมการควบคุมการขนส่งทางบกประจำจังหวัดภูเก็ต ฉบับที่ 37 เรื่อง ก", "ltcb"),
                    ("ประกาศเจ้าพนักงานพิทักษ์ทรัพย์ เรื่อง คำพิพากษาให้ลูกหนี้ล้มละลาย", "led"),
                    ("ข้อบังคับหัวหน้าเจ้าพนักงานจราจรในเขตกรุงเทพมหานคร ว่าด้วยการห้ามรถ", "police"),
                    ("ประกาศสำนักงานที่ดินกรุงเทพมหานคร สาขาพระโขนง เรื่อง ก", "dol"),
                    ("ข้อบัญญัติองค์การบริหารส่วนตำบลบางพลี เรื่อง ค่าธรรมเนียม", "local")]:
        assert ids(th) == [aid], th
        assert I.attribute(th, [aid], zh, RULES, gazette=True) == ("相关机关", [], [zh[aid]]), th
    assert AG["ltcb"]["zh"].endswith("(中央及各府)") and AG["land_alloc"]["zh"].endswith("(中央及各府)")


def test_vocab_has_full_names_as_th():
    """th 是官方全称,缩写放在别名里。"""
    for aid in ("etda", "erc", "eec"):
        assert not AG[aid]["th"].endswith("."), aid
    assert AG["oag"]["abbr"] == "SAO", "国家审计署现名 State Audit Office;OAG 在泰国指总检察院"


def test_repository_data_is_a_fixed_point_of_fix_agencies():
    """事实层始终是 fix_agencies 的不动点:采集入库(collect / agency_sources)与翻译(含判为无关的)都按标题定机关。
    补了机关忘记重跑 `python3 -m app.enrich --fix-agencies` 时这里会报。"""
    from app.config import REPO_ROOT                 # 仓库里的真实数据(测试的 POLICIES_DIR 指向 fixtures)
    from app.ingest import read_jsonl
    stale = []
    for rec in read_jsonl(REPO_ROOT / "data" / "policies" / "documents.jsonl"):
        r = json.loads(json.dumps(rec))
        if E.fix_agency(r, V):
            stale.append((rec["uid"], rec["agency_ids"], r["agency_ids"]))
    assert stale == []


def test_irrelevant_items_also_get_issuer():
    from tests.test_enrich import _raw
    rec = _raw(th="ประกาศกรมป่าไม้ เรื่อง จัดตั้งป่าชุมชน")
    out = E.apply_enrichment(rec, {"relevant": False, "title_zh": "林业厅公告", "summary_zh": ""}, V, "m")
    assert out["flags"]["skip"] and out["agency_ids"] == ["rfd"]


def test_collectors_set_issuer_from_title():
    from app import agency_sources as AS, collect as C
    rec, _ = C.normalize_gazette({"title": "ประกาศกรมป่าไม้ เรื่อง จัดตั้งป่าชุมชน", "date": "01/03/2569", "series": "ง"},
                                 "2026-03-02T00:00:00+07:00")
    assert rec["agency_ids"] == ["rfd"]
    rec, _ = C.normalize_gazette({"title": "ประกาศ เรื่อง ก", "date": "01/03/2569", "series": "ง"},
                                 "2026-03-02T00:00:00+07:00")
    assert rec["agency_ids"] == ["cabinet"], "认不出的照旧挂缺省值"
    r = AS._record("TH-BOI-1-X", "คำสั่งสำนักนายกรัฐมนตรี ที่ 1/2569 เรื่อง แต่งตั้ง", "2026-01-01", "", "boi_web",
                   "2026-01-01T00:00:00+07:00", agency="boi", domain="biz", legal_form="prakat", status="in_force")
    assert r["agency_ids"] == ["opm"]
    r = AS._record("TH-BOI-1-Y", "ประกาศ สกท. ที่ ป.1/2569 เรื่อง ก", "2026-01-01", "", "boi_web",
                   "2026-01-01T00:00:00+07:00", agency="boi", domain="biz", legal_form="prakat", status="in_force")
    assert r["agency_ids"] == ["boi"]


def test_requeue_kept_does_not_bring_back_red_lined_items(tmp_path, monkeypatch):
    """必收专题的放回队列(enrich --requeue-kept)不碰因红线跳过的条目:那是留给人工判断的。"""
    d = tmp_path / "policies"; d.mkdir()
    monkeypatch.setattr(E, "POLICIES_DIR", d)
    monkeypatch.setattr(E, "_keep_patterns", lambda: ["ผังเมืองรวม"])
    base = {"titles": {"zh": "某府总体规划", "th": "กฎกระทรวงให้ใช้บังคับผังเมืองรวมเมืองตัวอย่าง"},
            "agency_ids": ["cabinet"], "provenance": {"pipeline": "gazette_json"}}
    rows = [{**base, "uid": "A", "flags": {"skip": True}, "note": "LLM 判定与在泰外籍人士/企业无关"},
            {**base, "uid": "B", "flags": {"skip": True}, "note": "译文触及红线一,不做加工,待人工处理"}]
    (d / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    assert E.requeue_kept() == ["A"]
