# -*- coding: utf-8 -*-
"""采集层:佛历换算、红线拦截、失败降级、uid 可复现。

网络一律 mock —— 定时任务的正确性不能依赖泰国政府站点当下是否可达。
"""
from __future__ import annotations

import json

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


def test_normalize_cabinet_real_fields_pass_validation_rules():
    """真实接口字段(2026-09):带决议编号时必须给出文号可信度,否则 validate.py 拒收整轮结果。"""
    rec, _ = C.normalize_cabinet(
        {"toP_NAME": "เรื่อง ขอความเห็นชอบ", "meeT_DATE": "2026-04-21T00:00:00", "toP_SERLNO": "12",
         "docNews": "https://resolution.soc.go.th/?prep_id=1", "owner": "กระทรวงการคลัง"},
        "2026-09-28T00:00:00+07:00")
    assert rec["doc_no"] == "12" and rec["confidence"]["doc_no"] == "high"
    rec2, _ = C.normalize_cabinet({"toP_NAME": "เรื่อง มติ", "meeT_DATE": "2026-04-21"}, "2026-09-28T00:00:00+07:00")
    assert not rec2["doc_no"] and rec2["confidence"]["doc_no"] == "none"


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
    monkeypatch.setattr(C, "fetch_resource", lambda *_a, **_k: ([
        {"title": "ประกาศ ก", "date": "10/08/2569", "series": "ง"},   # 窗口内
        {"title": "ประกาศ ข", "date": "01/01/2568", "series": "ง"},   # 太旧
        {"title": "ประกาศ ค เครื่องราชอิสริยาภรณ์", "date": "10/08/2569", "series": "ง"},  # 红线
    ], "直连"))
    res = C.collect_source(C.SOURCES[0], C.Throttle(0), "2026-08-11T00:00:00+07:00",
                           C.date(2026, 8, 4), dry_run=False)
    assert res.status == "ok"
    assert len(res.records) == 1
    assert "跳过 2 条" in res.detail
    assert "example.invalid" in res.detail and "直连" in res.detail, "成功时也要记下文件所在域名与途径"


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


# ─────────────── 泰国出口代理 ───────────────

def test_egress_label_never_leaks_proxy_credentials(monkeypatch):
    """运行记录会提交进公开仓库:只能出现协议,不能出现代理地址和密码。"""
    from app import collect as C
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5://thai:s3cret@203.0.113.9:1080")
    label = C.egress_label()
    assert "socks5" in label
    assert "s3cret" not in label and "203.0.113.9" not in label and "thai:" not in label
    monkeypatch.setattr(settings, "egress_proxy", "")
    assert C.egress_label() == "直连"


@pytest.mark.parametrize("proxy", ["http://u:p@h:1", "https://h:1", "socks5://u:p@h:1", "socks5h://h:1"])
def test_source_client_accepts_supported_proxies(monkeypatch, proxy):
    from app import collect as C
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", proxy)
    with C.source_client({}) as c:          # 只建客户端,不联网
        assert c is not None


def test_source_client_rejects_unknown_scheme(monkeypatch):
    from app import collect as C
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "ftp://h:21")
    with pytest.raises(RuntimeError, match="协议不支持"):
        C.source_client({})


def test_llm_client_does_not_use_egress_proxy(monkeypatch):
    """泰国出口只给政府数据源用:DeepSeek 客户端创建时不能带上它。"""
    from app import enrich as E
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5://u:p@203.0.113.9:1080")
    seen = {}
    real = httpx.Client

    def spy(*a, **kw):
        seen.update(kw)
        return real(*a, **kw)
    monkeypatch.setattr(E.httpx, "Client", spy)
    E.DeepSeekClient("sk", "https://api.deepseek.com", "deepseek-chat")
    assert not seen.get("proxy") and not seen.get("proxies")


def test_data_source_client_does_use_egress_proxy(monkeypatch):
    from app import collect as C
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5://u:p@203.0.113.9:1080")
    seen = {}
    real = httpx.Client

    def spy(*a, **kw):
        seen.update(kw)
        return real(*a, **kw)
    monkeypatch.setattr(C.httpx, "Client", spy)
    C.source_client({}).close()
    assert seen["proxy"] == "socks5://u:p@203.0.113.9:1080"



# ─────────────── resource 下载:重试与直连兜底 ───────────────

class _Flaky(httpx.BaseTransport):
    """前 fail 次抛连接层错误,之后返回 JSON;calls 记录次数。"""
    def __init__(self, fail: int, exc=None):
        self.fail, self.calls = fail, 0
        self.exc = exc or httpx.ProxyError("Malformed reply")

    def handle_request(self, request):
        self.calls += 1
        if self.calls <= self.fail:
            raise self.exc
        return httpx.Response(200, json=[{"ok": 1}])


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(C.time, "sleep", lambda s: None)


def test_get_json_retries_connection_errors(no_sleep):
    t = _Flaky(fail=2)
    with httpx.Client(transport=t) as c:
        assert C.get_json(c, "https://data.go.th/x.json", C.Throttle(0)) == [{"ok": 1}]
    assert t.calls == 3


def test_get_json_does_not_retry_http_status(no_sleep):
    class T(httpx.BaseTransport):
        calls = 0
        def handle_request(self, request):
            T.calls += 1
            return httpx.Response(403)
    with httpx.Client(transport=T()) as c, pytest.raises(httpx.HTTPStatusError):
        C.get_json(c, "https://data.go.th/x", C.Throttle(0))
    assert T.calls == 1, "403 之类的 HTTP 错误重试也没用,不能拖慢整轮"


def test_resource_falls_back_to_direct_when_proxy_keeps_failing(no_sleep, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5h://u:p@h:1")
    direct = _Flaky(fail=0)
    monkeypatch.setattr(C, "direct_client", lambda h: httpx.Client(transport=direct))
    with httpx.Client(transport=_Flaky(fail=99)) as proxied:
        data, via = C.fetch_resource("https://files.example.go.th/2569.json", C.Throttle(0), proxied)
    assert data == [{"ok": 1}] and "直连兜底" in via and direct.calls == 1


def test_resource_error_names_host_and_both_paths(no_sleep, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5h://u:p@h:1")
    monkeypatch.setattr(C, "direct_client",
                        lambda h: httpx.Client(transport=_Flaky(99, httpx.ConnectError("refused"))))
    with httpx.Client(transport=_Flaky(fail=99)) as proxied, pytest.raises(RuntimeError) as ei:
        C.fetch_resource("https://files.example.go.th/2569.json", C.Throttle(0), proxied)
    msg = str(ei.value)
    assert "files.example.go.th" in msg and "经泰国出口" in msg and "直连" in msg and "Malformed" in msg
    assert "u:p" not in msg, "错误信息不能带出代理凭据"


def test_no_direct_fallback_without_proxy(no_sleep, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "")
    called = []
    monkeypatch.setattr(C, "direct_client", lambda h: called.append(1))
    with httpx.Client(transport=_Flaky(fail=99)) as c, pytest.raises(RuntimeError, match="files.example"):
        C.fetch_resource("https://files.example.go.th/x.json", C.Throttle(0), c)
    assert called == []


# ─────────────── 原始文件域名失效时:datastore 兜底 + 诊断信息 ───────────────

DEAD = "https://soc.gdcatalog.go.th/dataset/x/resource/y/download/2569.json"   # run #3 的真实情况


def test_permanent_errors_are_not_retried(no_sleep):
    t = _Flaky(99, httpx.ConnectError("[Errno -3] Temporary failure in name resolution"))
    with httpx.Client(transport=t) as c, pytest.raises(httpx.ConnectError):
        C.get_json(c, DEAD, C.Throttle(0))
    assert t.calls == 1, "域名解析不到,重试也没用"
    t2 = _Flaky(99, httpx.ProxyError("Proxy Server could not connect: General SOCKS server failure."))
    with httpx.Client(transport=t2) as c, pytest.raises(httpx.ProxyError):
        C.get_json(c, DEAD, C.Throttle(0))
    assert t2.calls == 1


def test_direct_fallback_is_single_attempt(no_sleep, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "egress_proxy", "socks5h://u:p@h:1")
    direct = _Flaky(99, httpx.ReadTimeout("slow"))
    monkeypatch.setattr(C, "direct_client", lambda h: httpx.Client(transport=direct))
    with httpx.Client(transport=_Flaky(99)) as proxied, pytest.raises(RuntimeError):
        C.fetch_resource(DEAD, C.Throttle(0), proxied)
    assert direct.calls == 1


def test_resource_period_parses_thai_month_and_year():
    assert C.resource_period({"name": "ราชกิจจานุเบกษาเดือนมีนาคม 2569"}) == (2026, 3)
    assert C.resource_period({"name": "มติคณะรัฐมนตรี ปี 2568"}) == (2025, 12)
    assert C.resource_period({"name": "x", "last_modified": "2026-05-02T00:00"}) == (2026, 5)


MONTHS = [{"id": f"m{i}", "name": f"ราชกิจจานุเบกษาเดือน{C.THAI_MONTHS[i - 1]} 2569", "format": "JSON",
           "url": DEAD} for i in range(1, 4)] + [
          {"id": "old", "name": "ราชกิจจานุเบกษาเดือนมกราคม 2566", "format": "JSON", "url": DEAD},
          {"id": "pdf", "name": "คู่มือ", "format": "PDF", "url": DEAD}]


def test_daily_sync_takes_latest_months(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "sync_resources", 2)
    ids = [r["id"] for r in C.sync_targets(MONTHS, C.date(2024, 9, 1), backfill=False)]
    assert ids == ["m3", "m2"], "最近两个月;PDF 不可解析,不下载"


def test_backfill_takes_all_months_within_lookback():
    ids = [r["id"] for r in C.sync_targets(MONTHS, C.date(2024, 9, 1), backfill=True)]
    assert ids == ["m3", "m2", "m1"], "2566(2023)早于回溯期"


def test_special_issue_series_is_kept():
    rec = {"title": "ประกาศกระทรวงการคลัง เรื่อง ภาษี", "date": "01/03/2569", "series": "ง พิเศษ"}
    norm, why = C.normalize_gazette(rec, "2026-09-27T00:00:00+07:00")
    assert norm is not None, why
    norm, why = C.normalize_gazette(dict(rec, series="ข"), "x")
    assert norm is None and "ข" in why


def _jsonl(tmp_path, monkeypatch, rows):
    d = tmp_path / "policies"; d.mkdir()
    monkeypatch.setattr(C, "POLICIES_DIR", d)
    (d / "documents.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return d / "documents.jsonl"


def _gz(uid, th="ประกาศ ก", doc_no="ง 1/2", pipeline="gazette_json", zh=""):
    return {"uid": uid, "titles": {"zh": zh, "th": th, "en": ""}, "summary_zh": "摘要" if zh else "",
            "doc_no": doc_no, "dates": {"published_at": "2026-03-01"}, "sources": [],
            "provenance": {"pipeline": pipeline}, "flags": {}}


def test_upsert_adds_updates_and_keeps_translation(tmp_path, monkeypatch):
    path = _jsonl(tmp_path, monkeypatch, [_gz("A", zh="中文A"), _gz("M", pipeline="research", zh="人工")])
    touched, added, updated = C.upsert_jsonl([
        _gz("A", doc_no="ง 1/3"),           # 官方源改了卷期 → 更新,中文保留
        _gz("M", doc_no="改过"),            # 人工整理的条目 → 不动
        _gz("B")], "2026-09-27")            # 新条目 → 追加
    assert (added, updated) == (1, 1)
    rows = {r["uid"]: r for r in map(json.loads, path.read_text().splitlines())}
    assert rows["A"]["doc_no"] == "ง 1/3" and rows["A"]["titles"]["zh"] == "中文A"
    assert rows["A"]["provenance"]["updated_at"] == "2026-09-27"
    assert rows["M"]["doc_no"] == "ง 1/2"
    assert list(rows) == ["A", "M", "B"], "原位改写,保持顺序"


def test_upsert_retitle_triggers_retranslation(tmp_path, monkeypatch):
    path = _jsonl(tmp_path, monkeypatch, [_gz("A", zh="中文A")])
    C.upsert_jsonl([_gz("A", th="ประกาศ ก (แก้ไข)")], "x")
    row = json.loads(path.read_text())
    assert row["titles"]["th"].endswith("(แก้ไข)") and row["titles"]["zh"] == "" and row["summary_zh"] == ""


def test_upsert_unchanged_is_noop(tmp_path, monkeypatch):
    path = _jsonl(tmp_path, monkeypatch, [_gz("A", zh="中文A")])
    before = path.read_text()
    assert C.upsert_jsonl([_gz("A")], "x")[1:] == (0, 0)
    assert path.read_text() == before, "没有变化就不改写文件,避免每天无意义的提交"


def test_multi_month_sync_and_field_sample(monkeypatch):
    monkeypatch.setattr(C, "fetch_ckan", lambda *_a, **_k: MONTHS)
    rows = {"m3": [{"title": "ประกาศ ก", "date": "01/03/2569", "series": "ง"}],
            "m2": [{"title": "ประกาศ ข", "date": "01/02/2569", "series": "ง พิเศษ"}]}
    monkeypatch.setattr(C, "download", lambda r, *_a: (rows.get(r["id"], []), "直连"))
    res = C.collect_source(C.SOURCES[0], C.Throttle(0), "x", C.date(2024, 9, 1), dry_run=False, backfill=False)
    assert res.status == "ok" and len(res.records) == 2
    assert "同步 3 个文件" in res.detail


def test_field_sample_reported_when_titles_missing(monkeypatch):
    monkeypatch.setattr(C, "fetch_ckan", lambda *_a, **_k: MONTHS[:1])
    monkeypatch.setattr(C, "download", lambda r, *_a: ([{"หัวข้อ": "x", "วันประชุม": "1"}], "直连"))
    res = C.collect_source(C.SOURCES[1], C.Throttle(0), "x", C.date(2024, 9, 1), dry_run=False)
    assert "字段样本:หัวข้อ,วันประชุม" in res.detail


def _source_with(monkeypatch, resources, datastore=None):
    resources = [dict(r, name=r.get("name", "") + " มีนาคม 2569") for r in resources]
    monkeypatch.setattr(C, "fetch_ckan", lambda *_a, **_k: resources)
    def dead(url, *_a, **_k):
        raise RuntimeError("soc.gdcatalog.go.th:经泰国出口 ProxyError: General SOCKS server failure")
    monkeypatch.setattr(C, "fetch_resource", dead)
    if datastore is not None:
        monkeypatch.setattr(C, "fetch_datastore", lambda *_a, **_k: datastore)
    return C.collect_source(C.SOURCES[0], C.Throttle(0), "2026-08-11T00:00:00+07:00",
                            C.date(2026, 8, 4), dry_run=False)


def test_datastore_rescues_dead_file_host(monkeypatch):
    res = _source_with(monkeypatch,
                       [{"id": "r1", "name": "2569-08", "format": "JSON", "url": DEAD, "datastore_active": True}],
                       datastore=[{"title": "ประกาศ ก", "date": "10/08/2569", "series": "ง"}])
    assert res.status == "ok" and len(res.records) == 1
    assert "data.go.th datastore" in res.detail


def test_all_dead_reports_resource_structure(monkeypatch):
    res = _source_with(monkeypatch, [
        {"id": "r1", "name": "2569-09", "format": "JSON", "url": DEAD},
        {"id": "r2", "name": "2569-08", "format": "CSV", "url": DEAD}])
    assert res.status == "error"
    # 下一次看运行记录就能知道:有哪些 resource、什么格式、放在哪、有没有 datastore
    assert "soc.gdcatalog.go.th" in res.detail and "datastore=否" in res.detail
    assert "[json·soc.gdcatalog.go.th" in res.detail and "[csv·soc.gdcatalog.go.th" in res.detail
