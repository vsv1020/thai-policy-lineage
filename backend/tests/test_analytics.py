# -*- coding: utf-8 -*-
"""分析层:七维、风向收缩、日历合并、样本量诚实性。"""
from __future__ import annotations

from datetime import date

from app import analytics as A


def test_wind_shrinks_toward_neutral_with_small_n(session):
    """单份高可信度文件不应给出 ±1.0 的极值 —— 收缩项的意义就在这里。"""
    for w in A.wind_now(session, A._today(session)):
        assert -1.0 < w["score"] < 1.0
        if w["n"] == 1:
            assert abs(w["score"]) <= 0.34, f"n=1 时 {w['label']} 指数过大: {w['score']}"


def test_wind_reports_sample_size(session):
    for w in A.wind_now(session, A._today(session)):
        assert w["n"] >= 1, "风向必须带样本量,否则读者无法判断可信度"


def test_dim1_years_are_contiguous(session):
    """中间「没有任何文件的那一年」是信号,不能被压缩掉。"""
    d = A.dim1_instrument_structure(session)
    years = [int(y) for y in d["years"]]
    assert years == list(range(years[0], years[-1] + 1))


def test_dim1_shares_sum_to_about_100(session):
    d = A.dim1_instrument_structure(session)
    assert 97 <= sum(g["share"] for g in d["groups"]) <= 103


def test_dim2_detects_policy_gaps(session):
    """工具×目标里为 0 的格子必须被列为空白。"""
    d = A.dim2_instrument_x_goal(session)
    for gap in d["gaps"]:
        assert gap["class"] and gap["goal"]
    labels = {m["label"] for m in d["matrix"]}
    assert all(g["class"] in labels for g in d["gaps"])


def test_dim3_fragile_pct_matches_counts(session):
    d = A.dim3_legal_forms(session)
    fragile = sum(f["count"] for f in d["forms"] if f["stability"] <= 2)
    assert d["fragile_pct"] == round(fragile / d["total"] * 100)


def test_dim3_marks_itself_insufficient_on_small_corpus(session):
    """12 份文件不足以谈「法律形式分布」,必须自认样本不足。"""
    d = A.dim3_legal_forms(session)
    assert d["sufficient"] is False
    assert d["n"] < d["min_n"]


def test_dim4_counts_support_and_constrain(session):
    d = A.dim4_affected_parties(session)
    travellers = next(i for i in d["items"] if i["id"] == "traveller")
    assert travellers["constrain"] >= 2 and travellers["constrain"] > travellers["support"]


def test_dim5_pairs_only_from_cosigned_documents(session):
    """联署对只能来自同一份文件上并列署名的机关。"""
    d = A.dim5_agency_cooperation(session)
    pairs = {frozenset((p["a"], p["b"])) for p in d["pairs"]}
    assert frozenset(("内阁", "内政部")) in pairs, "免签决议由内阁与内政部联署"
    assert frozenset(("劳工部", "社会保障办公室")) in pairs, "社保部令由劳工部与社保办联署"
    assert d["solo_documents"] >= 1
    assert all(p["n"] >= 1 for p in d["pairs"])


def test_dim6_sorted_by_severity(session):
    d = A.dim6_conflicts(session)
    order = {"high": 0, "med": 1, "low": 2}
    sev = [order[i["severity"]] for i in d["items"]]
    assert sev == sorted(sev)
    for item in d["items"]:
        assert len(item["sides"]) >= 2, "冲突必须能看到双方口径"


def test_dim7_flags_missing_links(session):
    d = A.dim7_implementation(session)
    assert "评估与复盘" in d["missing"], "评估环节为 0 是真实的缺环,必须报出来"
    hot = [x for x in d["stages"] if x["hot"]]
    assert len(hot) == 1 and hot[0]["count"] == d["peak"]


def test_calendar_merges_documents_and_statutory_deadlines(session):
    items = A.calendar(session, A._today(session))
    kinds = {i["kind"] for i in items}
    assert "deadline" in kinds, "周期性法定截止日必须出现在日历里"
    assert items == sorted(items, key=lambda x: x["date"])


def test_calendar_excludes_past(session):
    today = A._today(session)
    for i in A.calendar(session, today):
        assert date.fromisoformat(i["date"]) >= today


def test_trends_refuses_to_be_usable_without_enough_months(session):
    t = A.trends(session)
    assert t["usable"] == (t["months_covered"] >= t["min_months_required"])


def test_overview_featured_is_derived_not_stored(session):
    o = A.overview(session)
    from app.config import settings
    featured = [p for p in o["policies"] if p["featured"]]
    assert len(featured) <= settings.feed_size
    from collections import Counter
    assert max(Counter(p["org"] for p in featured).values()) <= 2, "同一机关在首页最多 2 条"
    # 有要点的排前面,同组内日期倒序
    keys = [(not p["key_points"], p["date"]) for p in o["policies"]]
    groups = [k[0] for k in keys]
    assert groups == sorted(groups)
    for g in (False, True):
        ds = [d for k, d in keys if k == g]
        assert ds == sorted(ds, reverse=True)


def test_overview_stats_cover_the_front_page(session):
    o = A.overview(session)
    st = o["stats"]
    assert sum(d["n"] for d in st["by_domain"]) == st["total"], "各领域条数之和要等于总数"
    assert st["with_points"] == sum(1 for p in o["policies"] if p["key_points"])
    assert st["date_from"] <= st["date_to"]
    assert all({"id", "label", "stance"} <= set(x) for p in o["policies"] for x in p["parties"])


def test_research_documents_never_claim_human_review(session):
    o = A.overview(session)
    for p in o["policies"]:
        if p["provenance"] == "research":
            assert p["verified"] is False


def test_iso_bkk_attaches_timezone(session):
    from datetime import datetime
    naive = datetime(2026, 8, 11, 0, 38, 8)
    assert A.iso_bkk(naive).endswith("+07:00")
    assert A.iso_bkk(None) is None


def test_trends_window_ends_at_latest_data_not_today(session):
    """官方公报滞后数月:时间窗必须以数据截止月为终点,否则最近几个月是假的「断崖」。"""
    from sqlalchemy import func, select
    from app import analytics as A
    from app.models import Document
    t = A.trends(session)
    latest = session.scalar(select(func.max(Document.display_date)))
    assert t["data_through"] == latest.isoformat()[:7]
    assert t["months"][-1] == f"{latest.year % 100:02d}-{latest.month:02d}"
    assert t["total_documents"] >= 1


def test_rising_topics_are_real_counts(session):
    from datetime import timedelta
    from sqlalchemy import func, select
    from app import analytics as A
    from app.models import Document
    latest = session.scalar(select(func.max(Document.display_date)))
    rows = A.rising_topics(session, latest)
    for r in rows:
        assert r["current"] >= 2
        assert r["growth_pct"] is None or r["growth_pct"] > 0
    # 窗口外(未来)的锚点不会凭空产生话题
    assert A.rising_topics(session, latest + timedelta(days=400)) == []


def test_morphology_counts_are_consistent(session):
    from sqlalchemy import func, select
    from app import analytics as A
    from app.models import Document
    m = A.morphology(session)
    total = session.scalar(select(func.count(Document.uid)))
    assert m["n"] == total == m["kpis"]["total"]
    assert sum(f["n"] for f in m["legal_forms"]) == total
    assert sum(t["n"] for t in m["tiers"]) == total
    assert sum(st["n"] for st in m["statuses"]) == total
    assert sum(sum(r) for r in m["matrix"]["cells"]) == sum(p["n"] for p in m["domain_profiles"])
    assert len(m["evolution"]) == 8, "连续 8 个季度,空季度记 0"
    assert all(1 <= p["avg_stability"] <= 5 for p in m["domain_profiles"])


def test_morphology_insights_come_from_numbers(session):
    from app import analytics as A
    m = A.morphology(session)
    assert m["insights"] and str(m["kpis"]["total"]) in m["insights"][0]
    # 小样本时不做「前后对比」的结论
    k = dict(m["kpis"])
    ev = [{"quarter": f"2026Q{i}", "n": 1, "avg_stability": 5 - i, "tiers": {}} for i in range(1, 5)]
    assert not any("平均层级" in t and "相比" in t for t in A.morphology_insights(k, m["tiers"], [], ev))
