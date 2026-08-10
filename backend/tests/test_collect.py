# -*- coding: utf-8 -*-
"""采集层:佛历换算、红线拦截、失败降级、uid 可复现。

网络一律 mock —— 定时任务的正确性不能依赖泰国政府站点当下是否可达。
"""
from __future__ import annotations

import httpx
import pytest

from app import collect as C


# ── 日期与佛历 ──

@pytest.mark.parametrize("raw,expected", [
    ("25/07/2569", "2026-07-25"),     # 佛历 日/月/年
    ("2569-07-25", "2026-07-25"),     # 佛历 ISO
    ("2026-07-25", "2026-07-25"),     # 已是公历,原样
    ("01/01/2568", "2025-01-01"),
])
def test_normalize_date_handles_buddhist_era(raw, expected):
    assert C.normalize_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "n/a", "32/13/2569", "昨天"])
def test_normalize_date_rejects_garbage(raw):
    assert C.normalize_date(raw) is None


def test_be_to_ce_is_idempotent_for_gregorian():
    assert C.be_to_ce(2026) == 2026
    assert C.be_to_ce(2569) == 2026


# ── 三条编辑红线 ──

def test_red_line_royal_content_blocked():
    ok, why = C.passes_red_lines("ประกาศสำนักนายกรัฐมนตรี เรื่อง พระราชทานเครื่องราชอิสริยาภรณ์")
    assert ok is False and "王室" in why


def test_red_line_person_names_blocked():
    ok, why = C.passes_red_lines("ประกาศ เรื่อง แปลงสัญชาติ นายสมชาย")
    assert ok is False and "姓名" in why


def test_ordinary_title_passes():
    ok, _ = C.passes_red_lines("ประกาศกรมสรรพากร เรื่อง ภาษีเงินได้")
    assert ok is True


def test_normalize_gazette_skips_undated_records():
    """红线三:没有可核实日期就不入库,宁可 0 条。"""
    rec, why = C.normalize_gazette({"title": "ประกาศบางอย่าง"}, "2026-08-11T00:00:00+07:00")
    assert rec is None and "日期" in why


def test_normalize_gazette_skips_royal_appointment_series():
    rec, why = C.normalize_gazette(
        {"title": "ประกาศ", "date": "01/08/2569", "series": "ข"}, "2026-08-11T00:00:00+07:00")
    assert rec is None and "ข" in why


def test_normalize_gazette_never_invents_source_url():
    rec, _ = C.normalize_gazette(
        {"title": "ประกาศกรมสรรพากร", "date": "01/08/2569", "series": "ง"},
        "2026-08-11T00:00:00+07:00")
    assert rec is not None
    assert rec["sources"] == [], "没有 PDF 链接时不能编一个出来"
    assert rec["provenance"]["verified"] is False


def test_normalize_gazette_uid_is_reproducible():
    """同一条记录反复采集必须得到同一个 uid,否则每天都会重复入库。"""
    rec = {"title": "ประกาศกรมสรรพากร เรื่อง ภาษี", "date": "01/08/2569", "series": "ง"}
    a, _ = C.normalize_gazette(rec, "2026-08-11T00:00:00+07:00")
    b, _ = C.normalize_gazette(rec, "2026-09-30T00:00:00+07:00")   # 不同 run_at
    assert a["uid"] == b["uid"]


def test_normalize_cabinet_sets_pending_gazette():
    rec, _ = C.normalize_cabinet(
        {"title": "เรื่อง มติ", "date": "12/05/2569"}, "2026-08-11T00:00:00+07:00")
    assert rec["status_id"] == "pending_gazette"
    assert rec["dates"]["resolved_at"] == "2026-05-12"
    assert rec["dates"]["published_at"] is None
    assert rec["implementation_stage"] == "cabinet_resolution"


# ── 失败路径 ──

def test_collect_source_records_error_without_raising(monkeypatch):
    """源不可达时必须记 error 并继续,不能让整轮采集崩掉。"""
    def boom(*_a, **_k):
        raise httpx.ProxyError("403 Forbidden")
    monkeypatch.setattr(C, "fetch_ckan", boom)
    res = C.collect_source(C.SOURCES[0], C.Throttle(0), "2026-08-11T00:00:00+07:00",
                           C.date(2026, 8, 1), dry_run=False)
    assert res.status == "error"
    assert "403" in res.detail
    assert res.records == []


def test_collect_source_reports_ok_and_filters_by_window(monkeypatch):
    monkeypatch.setattr(C, "fetch_ckan", lambda *_a, **_k: [
        {"format": "JSON", "url": "https://example.invalid/x.json", "name": "2569-08"}])
    monkeypatch.setattr(C, "fetch_resource", lambda *_a, **_k: [
        {"title": "ประกาศ ก", "date": "10/08/2569", "series": "ง"},   # 窗口内
        {"title": "ประกาศ ข", "date": "01/01/2568", "series": "ง"},   # 太旧
        {"title": "ประกาศ ค เครื่องราชอิสริยาภรณ์", "date": "10/08/2569", "series": "ง"},  # 红线
    ])
    res = C.collect_source(C.SOURCES[0], C.Throttle(0), "2026-08-11T00:00:00+07:00",
                           C.date(2026, 8, 4), dry_run=False)
    assert res.status == "ok"
    assert len(res.records) == 1
    assert "跳过 2 条" in res.detail


def test_throttle_enforces_minimum_interval():
    import time
    t = C.Throttle(0.05)
    t.wait()
    start = time.monotonic()
    t.wait()
    assert time.monotonic() - start >= 0.04, "礼貌限速不能被绕过"


def test_iter_records_handles_wrapped_payloads():
    assert C.iter_records([{"a": 1}]) == [{"a": 1}]
    assert C.iter_records({"data": [{"a": 1}]}) == [{"a": 1}]
    assert C.iter_records({"records": [{"a": 1}]}) == [{"a": 1}]
    assert C.iter_records("nope") == []
