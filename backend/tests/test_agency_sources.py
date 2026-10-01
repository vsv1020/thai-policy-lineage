"""部门官网来源:税务厅 RSS「新法」、BOI 内嵌公告 JSON。样例按 2026-10-01 实测格式构造。"""
from __future__ import annotations

from datetime import date

from app import agency_sources as AS
from app import collect as C

RSS = """<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<item><guid isPermaLink="false">news-9877</guid><pubDate>Wed, 23 Dec 2026 00:00:00 +0700</pubDate>
<title>กำหนดยื่นแบบทางอินเทอร์เน็ต</title><link>/26/9877.html</link></item>
<item><pubDate>Thu, 01 Oct 2026 10:00:00 +0700</pubDate>
<title>พระราชกฤษฎีกาออกตามความในประมวลรัษฎากร ว่าด้วยการยกเว้นรัษฎากร (ฉบับที่ 806) พ.ศ. 2569</title>
<link>https://www.rd.go.th/fileadmin/user_upload/kormor/newlaw/dc806.pdf</link></item>
<item><pubDate>Wed, 23 Sep 2026 09:00:00 +0700</pubDate>
<title><![CDATA[ประกาศกระทรวงการคลัง เรื่อง กำหนดหลักเกณฑ์การเปรียบเทียบตามมาตรา 31 &amp; อื่น ๆ]]></title>
<link>https://www.rd.go.th/fileadmin/user_upload/kormor/newlaw/mofcrsm31A.pdf</link></item>
<item><pubDate>Thu, 01 Oct 2026 08:00:00 +0700</pubDate><title>กรมสรรพากรร่วมแสดงมุทิตาจิต</title>
<link>/26/12439.html</link></item>
</channel></rss>"""

BOI_HTML = """<html><div v-if="!finish" style="display:none" id="dataMasterLaws" databind="true">
{ "topic_id":139362, "topic_year":"2026", "topic_preview":"หลักเกณฑ์การเข้าสู่ระบบเร่งรัดโครงการลงทุน (Thailand FastPass)",
  "topic_name":"ประกาศ สกท.ที่ ป.11/2569", "topic_detail":"",
  "topic_source":"ยกเลิกประกาศสำนักงานคณะกรรมการส่งเสริมการลงทุน ที่ ป.1/2569", "topic_date":"2026-09-16 00:00:00.000",
  "topic_status":"", "group_id":165, "group_name":"ประกาศ ที่ ป. (POR)", "file_path":"upload/content/por11_2569_6aab52aeeedbb.pdf" },
{ "topic_id":139000, "topic_preview":"บรรทัด\tที่มีอักขระควบคุม", "topic_name":"คำชี้แจง ฉบับลงวันที่ 21 พฤษภาคม 2569",
  "topic_date":"2026-05-21 00:00:00.000", "topic_status":"", "file_path":"upload/content/c3 2569.pdf" },
{ "topic_id":100, "topic_preview":"เก่า", "topic_name":"ประกาศ กกท. ที่ 1/2547", "topic_date":"2004-01-01 00:00:00.000",
  "file_path":"upload/content/old.pdf" },
{ "topic_id":101, "topic_preview":"ไม่มีไฟล์", "topic_name":"ประกาศ", "topic_date":"2026-06-01 00:00:00.000", "file_path":"" }
</div></html>"""

RUN = "2026-10-01T07:00:00+07:00"


def test_rd_rss_keeps_only_new_laws():
    items = AS.parse_rd_rss(RSS)
    assert [x["url"].rsplit("/", 1)[-1] for x in items] == ["dc806.pdf", "mofcrsm31A.pdf"]
    assert items[0]["date"] == "2026-10-01" and "&" in items[1]["title"]
    rec, why = AS.normalize_rd(items[0], RUN)
    assert why == "" and rec["uid"] == "TH-RD-20261001-DC806"
    assert rec["legal_form_id"] == "decree" and rec["agency_ids"] == ["rd"] and rec["domain_ids"] == ["tax"]
    assert rec["sources"][0]["url"].endswith("/newlaw/dc806.pdf")
    rec2, _ = AS.normalize_rd(items[1], RUN)
    assert rec2["agency_ids"] == ["mof"] and rec2["legal_form_id"] == "prakat"
    _, why = AS.normalize_rd({"title": "ประกาศ", "url": items[0]["url"], "date": ""}, RUN)
    assert why == "无可解析日期"


def test_boi_embedded_json():
    objs = AS.parse_boi(BOI_HTML)
    assert len(objs) == 4                       # 含控制字符的那条也要解析出来
    rec, why = AS.normalize_boi(objs[0], RUN)
    assert why == "" and rec["uid"] == "TH-BOI-20260916-139362"
    assert rec["titles"]["th"].startswith("ประกาศ สกท.ที่ ป.11/2569 เรื่อง หลักเกณฑ์")
    assert rec["doc_no"] == "ป.11/2569" and rec["dates"]["published_at"] == "2026-09-16"
    assert rec["sources"][0]["url"] == "https://www.boi.go.th/upload/content/por11_2569_6aab52aeeedbb.pdf"
    assert "ยกเลิกประกาศ" in rec["note"] and rec["status_id"] == "in_force"
    rec2, _ = AS.normalize_boi(objs[1], RUN)
    assert rec2["legal_form_id"] == "guidance" and "%20" in rec2["sources"][0]["url"]
    assert AS.normalize_boi(objs[3], RUN) == (None, "没有官方 PDF")
    assert not AS.in_window(AS.normalize_boi(objs[2], RUN)[0]["dates"]["published_at"], date(2024, 10, 1))


def test_agency_record_passes_red_lines_and_validation_shape():
    rec, _ = AS.normalize_boi(AS.parse_boi(BOI_HTML)[0], RUN)
    assert rec["provenance"]["pipeline"] in C.AUTO_PIPELINES
    from app.ingest import official_sources
    assert official_sources(rec)


def test_twin_only_across_agency_and_gazette():
    agency, _ = AS.normalize_rd(AS.parse_rd_rss(RSS)[0], RUN)
    gazette = {"uid": "TH-GAZ-20261002-806", "titles": {"th": agency["titles"]["th"].replace("806", "๘๐๖")},
               "dates": {"published_at": "2026-10-02"}, "provenance": {"pipeline": "gazette_json"},
               "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/documents/1.pdf"}]}
    rows = [agency]
    assert AS.title_key(gazette["titles"]["th"]) == AS.title_key(agency["titles"]["th"])
    assert C.find_twin(rows, [0], gazette) == 0
    # 同来源、同标题(储蓄银行利率公告)是不同文件
    same_src = {**gazette, "provenance": {"pipeline": "rd_web"}}
    assert C.find_twin(rows, [0], same_src) is None
    far = {**gazette, "dates": {"published_at": "2027-06-01"}}
    assert C.find_twin(rows, [0], far) is None
