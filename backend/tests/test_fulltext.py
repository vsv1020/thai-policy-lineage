# -*- coding: utf-8 -*-
"""公报正文:下载与抽取的护栏;翻译时用正文写要点、推生效日;旧摘要按正文重做。模型与网络一律 mock。"""
from __future__ import annotations

import json

import httpx
import pytest

from app import enrich as E, fulltext as F
from app.ingest import join_summary, split_summary

from .test_enrich import GOOD, FakeClient, _raw

THAI = ("ประกาศกระทรวงการคลัง เรื่อง การลดอัตราภาษีเงินได้บุคคลธรรมดา ให้ผู้มีเงินได้ที่มีถิ่นที่อยู่ในประเทศไทย "
        "ยื่นแบบภายในวันที่ ๓๑ มีนาคม ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษาเป็นต้นไป ") * 2

FULL = {**GOOD, "summary_zh": "财政部下调个人所得税税率,适用于泰国税务居民。",
        "key_points": ["· 适用对象:泰国税务居民", "2. 申报截止:3 月 31 日", ""],
        "effective_rule": "day_after_publication", "effective_date": ""}


# ─────────────────────────── 抽取 ───────────────────────────

def test_normalize_maps_legacy_thai_glyphs():
    # 老式字体:声调符号在私用区;SARA AM 被拆成 ํ + า
    assert F.normalize("กา  \n\n ขํา") == "ก้า \n ขำ"


def test_quality_gate():
    assert F.good_enough(THAI)
    assert not F.good_enough("Ã Â¸ Â¡ mojibake " * 30), "乱码不能当正文"
    assert not F.good_enough("ประกาศ"), "太短"


def test_pdf_url_only_official_pdf():
    rec = {"sources": [{"role": "secondary", "url": "https://news.example/x.pdf"},
                       {"role": "official", "url": "https://example.com/y.pdf"},
                       {"role": "official", "url": "https://www.mof.go.th/page"},
                       {"role": "official", "url": "https://ratchakitcha.soc.go.th/documents/1.pdf"}]}
    assert F.pdf_url(rec) == "https://ratchakitcha.soc.go.th/documents/1.pdf"
    assert F.pdf_url({"sources": []}) == ""


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_rejects_non_pdf_and_oversize(monkeypatch):
    monkeypatch.setattr(F._throttle, "min_interval", 0)
    assert F.download("https://x.go.th/a.pdf", _client(lambda r: httpx.Response(200, content=b"<html>"))) is None
    assert F.download("https://x.go.th/a.pdf", _client(lambda r: httpx.Response(404))) is None
    ok = F.download("https://x.go.th/a.pdf", _client(lambda r: httpx.Response(200, content=b"%PDF-1.4 x")))
    assert ok == b"%PDF-1.4 x"
    monkeypatch.setattr(F, "MAX_BYTES", 10)
    assert F.download("https://x.go.th/a.pdf", _client(lambda r: httpx.Response(200, content=b"%PDF-" + b"0" * 50))) is None


def test_fetch_fulltext_prefers_text_layer_then_ocr(monkeypatch):
    rec = {"uid": "U", "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/d/1.pdf"}]}
    monkeypatch.setattr(F, "download", lambda url, c: b"%PDF-")
    monkeypatch.setattr(F, "extract_pdf_text", lambda data: THAI)
    assert F.fetch_fulltext(rec, None) == (THAI[:F.MAX_CHARS], "text")

    monkeypatch.setattr(F, "extract_pdf_text", lambda data: "????")
    monkeypatch.setattr(F, "_ocr", True)
    monkeypatch.setattr(F, "ocr_pdf", lambda data: THAI)
    assert F.fetch_fulltext(rec, None)[1] == "ocr"

    monkeypatch.setattr(F, "ocr_pdf", lambda data: "")
    assert F.fetch_fulltext(rec, None) == ("", ""), "都读不出来就退回只看标题"


def test_extract_pdf_text_reads_text_layer():
    try:
        import pypdf  # noqa: F401
    except BaseException:  # noqa: BLE001 —— 本机 cryptography 坏掉时 pyo3 会 panic
        pytest.skip("pypdf 在本机不可用")
    stream = b"BT /F1 12 Tf 72 720 Td (Royal Gazette notice) Tj ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % x for x in offs)
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
    assert "Royal Gazette notice" in F.extract_pdf_text(out)
    assert F.extract_pdf_text(b"%PDF-broken") == ""


# ─────────────────────────── 翻译:用正文 ───────────────────────────

@pytest.fixture()
def jsonl(tmp_path, monkeypatch):
    d = tmp_path / "policies"; d.mkdir()
    monkeypatch.setattr(E, "POLICIES_DIR", d)
    return d


def _write(d, *recs):
    (d / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))


def _rows(d):
    return [json.loads(x) for x in (d / "documents.jsonl").read_text().splitlines()]


def test_fulltext_goes_to_model_and_yields_points_and_effective_date(jsonl):
    _write(jsonl, _raw())
    client = FakeClient(FULL)
    res = E.run_enrichment(client=client, fetch_text=lambda rec: (THAI, "text"))
    assert res["enriched"] == 1 and res["fulltext"] == 1
    user = client.calls[0]["messages"][0]["content"]
    assert "正文(官方 PDF 抽取)" in user and THAI[:30] in user
    row = _rows(jsonl)[0]
    assert row["key_points_zh"] == ["适用对象:泰国税务居民", "申报截止:3 月 31 日"]
    assert row["dates"]["effective_from"] == "2026-09-02", "刊登次日起施行"
    assert row["provenance"]["summary_basis"] == "fulltext"
    assert "泰文原文正文" in row["note"]


def test_without_fulltext_no_points_or_dates_are_trusted(jsonl):
    _write(jsonl, _raw())
    client = FakeClient(FULL)
    E.run_enrichment(client=client, fetch_text=lambda rec: ("", ""))
    row = _rows(jsonl)[0]
    assert "正文:无" in client.calls[0]["messages"][0]["content"]
    assert row["key_points_zh"] == [] and row["dates"]["effective_from"] is None
    assert row["provenance"]["summary_basis"] == "title"


def test_old_title_only_summaries_get_upgraded(jsonl):
    old = E.apply_enrichment(_raw(uid="TH-GAZ-OLD"), GOOD, E._vocab(), "m")
    _write(jsonl, old)
    assert E.needs_fulltext_upgrade(old)
    client = FakeClient({**FULL, "relevant": False})
    res = E.run_enrichment(client=client, fetch_text=lambda rec: (THAI, "text"))
    assert res["upgraded"] == 1 and res["pending"] == 0
    row = _rows(jsonl)[0]
    assert row["provenance"]["summary_basis"] == "fulltext" and not row["flags"].get("skip"), \
        "重做只更新内容,不推翻早先的「相关」判定"
    assert not E.needs_fulltext_upgrade(row)


def test_upgrade_without_text_does_not_call_model_and_gives_up_after_limit(jsonl):
    old = E.apply_enrichment(_raw(uid="TH-GAZ-OLD"), GOOD, E._vocab(), "m")
    _write(jsonl, old)
    client = FakeClient(FULL)
    for _ in range(E.UPGRADE_MAX_ATTEMPTS):
        E.run_enrichment(client=client, fetch_text=lambda rec: ("", ""))
    assert client.calls == []
    row = _rows(jsonl)[0]
    assert row["provenance"]["fulltext_attempts"] == E.UPGRADE_MAX_ATTEMPTS
    assert not E.needs_fulltext_upgrade(row)
    assert row["summary_zh"] == GOOD["summary_zh"], "没拿到正文时原摘要保持不变"


@pytest.mark.parametrize("rule,explicit,pub,expect", [
    ("on_publication", "", "2026-09-01", "2026-09-01"),
    ("day_after_publication", "", "2026-12-31", "2027-01-01"),
    ("explicit_date", "2569-10-01", "2026-09-01", "2026-10-01"),     # 佛历自动换算
    ("explicit_date", "2035-01-01", "2026-09-01", None),             # 离刊登日太远,不采用
    ("explicit_date", "明年", "2026-09-01", None),
    ("none", "", "2026-09-01", None),
    ("day_after_publication", "", None, None),
])
def test_effective_from_rules(rule, explicit, pub, expect):
    assert E.effective_from(rule, explicit, pub) == expect


def test_validate_rejects_bad_new_fields():
    v = E._vocab()
    assert E.validate_output({**FULL, "key_points": "x"}, v)
    assert E.validate_output({**FULL, "effective_rule": "soon"}, v)
    assert E.validate_output({**FULL, "effective_rule": "explicit_date", "effective_date": "10/1"}, v)
    assert E.validate_output(FULL, v) is None
    assert E.validate_output(GOOD, v) is None, "旧格式输出(没有新字段)仍然合格"


# ─────────────────────────── 展示 ───────────────────────────

def test_summary_points_roundtrip():
    s = join_summary("概述。", ["要点一", " ", "要点二"])
    assert split_summary(s) == ("概述。", ["要点一", "要点二"])
    assert split_summary("只有摘要") == ("只有摘要", [])


def test_landing_page_and_api_show_points(session):
    from sqlalchemy import select
    from app import analytics as A, seo
    from app.models import Document
    doc = session.scalars(select(Document).order_by(Document.uid)).first()
    orig = doc.summary_zh
    doc.summary_zh = join_summary("概述。", ["适用对象:税务居民", "截止:3 月 31 日"])
    session.flush()
    v = A.document_view(session, doc, A._today(session))
    assert v["summary_zh"] == "概述。" and v["key_points"] == ["适用对象:税务居民", "截止:3 月 31 日"]
    html = seo.render_page(session, doc, A._today(session), {})
    assert '<ul class="points"><li>适用对象:税务居民</li>' in html
    doc.summary_zh = orig
    session.rollback()


def test_royal_wording_in_model_output_is_red_lined(jsonl):
    """读正文后模型可能写出「经国王御准」:整条按红线一跳过,不写入任何译文(validate.py 也会拒收)。"""
    _write(jsonl, _raw())
    E.run_enrichment(client=FakeClient({**FULL, "summary_zh": "本法令经国王御准颁布,调整个税税率。"}),
                     fetch_text=lambda rec: (THAI, "text"))
    row = _rows(jsonl)[0]
    assert row["flags"]["skip"] is True and row["titles"]["zh"] == "" and row["summary_zh"] == ""
    assert "红线一" in row["note"]
    blob = json.dumps(row, ensure_ascii=False)
    assert not any(t in blob for t in E.ROYAL_OUTPUT_TERMS if t not in rec_terms(row)), "记录里不能残留红线词"


def rec_terms(row):
    """泰文原题本身带的词(采集阶段已过滤王室标题,这里只排除原题)。"""
    return [t for t in E.ROYAL_OUTPUT_TERMS if t in (row.get("titles") or {}).get("th", "")]


def test_fulltext_misses_are_counted_by_reason(monkeypatch):
    monkeypatch.setattr(F._throttle, "min_interval", 0)
    F.reset_misses()
    rec = {"uid": "U", "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/d/1.pdf"}]}
    F.fetch_fulltext(rec, _client(lambda r: httpx.Response(403)))
    F.fetch_fulltext(rec, _client(lambda r: httpx.Response(403)))
    F.fetch_fulltext({"uid": "V", "sources": [{"role": "official", "url": "https://x.go.th/page"}]}, None)
    m = F.misses()
    assert m["HTTP 403"]["n"] == 2 and m["HTTP 403"]["example"].endswith("1.pdf")
    assert m["没有官方 PDF 链接"]["n"] == 1
    assert list(m)[0] == "HTTP 403", "按次数从多到少排"


def test_tis620_mojibake_is_repaired():
    thai = "ประกาศกระทรวงการคลัง เรื่อง ภาษีเงินได้"
    garbled = "".join(chr(ord(c) - 0x0E01 + 0xA1) if "\u0e01" <= c <= "\u0e5b" else c for c in thai)
    assert F.normalize(garbled) == thai
    assert F.normalize("Café résumé naïve") == "Café résumé naïve", "正常的西文重音字母不能被误转"


def test_english_gazette_text_is_accepted():
    eng = ("Amendments to the International Convention for the Safety of Life at Sea, 1974, "
           "chapter II-2 regulation 19 on ships carrying dangerous goods. ") * 3
    assert F.good_enough(eng)


def test_pdftotext_fallback_and_detailed_miss_reason(monkeypatch):
    rec = {"uid": "U", "sources": [{"role": "official", "url": "https://ratchakitcha.soc.go.th/d/9.pdf"}]}
    monkeypatch.setattr(F, "download", lambda url, c: b"%PDF-")
    monkeypatch.setattr(F, "extract_pdf_text", lambda data: "@@##" * 50)
    monkeypatch.setattr(F, "extract_pdftotext", lambda data: THAI)
    assert F.fetch_fulltext(rec, None) == (THAI[:F.MAX_CHARS], "text"), "pypdf 乱码时改用 pdftotext"

    F.reset_misses()
    monkeypatch.setattr(F, "extract_pdftotext", lambda data: "")
    monkeypatch.setattr(F, "_ocr", True)

    def slow_ocr(data):
        F._ocr_err.value = "超时"
        return ""
    monkeypatch.setattr(F, "ocr_pdf", slow_ocr)
    assert F.fetch_fulltext(rec, None) == ("", "")
    (why, m), = F.misses().items()
    assert why == "文字层不可读,OCR 超时"
    assert "9.pdf" in m["example"] and "pypdf 200 字" in m["example"]
