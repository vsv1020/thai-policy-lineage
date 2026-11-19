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
    ("ประกาศสำนักงานคณะกรรมการกลางว่าด้วยราคาสินค้าและบริการ ฉบับที่ 1 พ.ศ. 2569 เรื่อง การแก้ไขเพิ่มเติมแบบแจ้ง",
     ["ccp_office"]),
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
    assert seo.issuer_info(doc, "商品与服务安全委员会", seo.agency_th_names()) == ("发文机关", "商品与服务安全委员会")
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


def test_seo_and_enrich_share_the_same_rules():
    """页面层的名称表和数据层的词表规则是同一套(不再各自推导「委员会 / 委员会办公室」)。"""
    assert I.rules_from_names(seo.agency_th_names()) == RULES


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
        for n in [a["th"], *(a.get("th_aliases") or [])]:
            k = I.norm(n)
            assert k not in owner or owner[k] == a["id"], (n, owner.get(k), a["id"])
            owner[k] = a["id"]
            if len(k) >= I.MIN_NAME:
                for doc in ("ประกาศ", "คำสั่ง", "ระเบียบ"):
                    assert ids(f"{doc}{n} เรื่อง ทดสอบ") == [a["id"]], (doc, n)
    zh = [a["zh"] for a in V["agencies"]]
    assert len(zh) == len(set(zh)), "中文名不重复"


def test_no_alias_is_a_bare_generic_word():
    generic = {"คณะกรรมการ", "สำนักงาน", "นายทะเบียน", "กรม", "กระทรวง", "จังหวัด", "สภา", "ศาล", "ประกาศ"}
    for a in V["agencies"]:
        for n in [a["th"], *(a.get("th_aliases") or [])]:
            assert I.norm(n) not in generic, (a["id"], n)


def test_org_name_shows_ascii_abbr_only():
    from app.analytics import document_view  # noqa: F401 —— 只确认 abbr 的写法符合 org_name 的规则
    for a in V["agencies"]:
        ab = a["abbr"].replace("-", "")
        assert ab == "" or (ab.isascii() and ab.isalpha()) or a["id"] in ("cabinet", "etda", "erc", "eec"), a["id"]


def test_vocab_file_is_the_one_read():
    assert json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8")) == V
