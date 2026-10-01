"""同名系列脉络:只按官方泰文标题字面归组,不推断替代关系。"""
from __future__ import annotations

import json
from pathlib import Path

from app.analytics import _thai_int, series_stem

ROOT = Path(__file__).resolve().parents[2]


def test_series_stem_strips_issue_number_and_year():
    a = "ประกาศกรมธุรกิจพลังงาน เรื่อง กำหนดลักษณะและคุณภาพของน้ำมันดีเซล (ฉบับที่ 5) พ.ศ. 2569"
    b = "ประกาศกรมธุรกิจพลังงาน เรื่อง กำหนดลักษณะและคุณภาพของน้ำมันดีเซล (ฉบับที่ ๖) พ.ศ. ๒๕๖๙"
    assert series_stem(a) == series_stem(b)
    assert "ฉบับที่" not in series_stem(a) and "2569" not in series_stem(a)
    assert _thai_int("๖") == 6


def test_exported_series_are_real_sequences():
    lineage = json.loads((ROOT / "data/site/lineage.json").read_text(encoding="utf-8"))
    policies = json.loads((ROOT / "data/site/policies.json").read_text(encoding="utf-8"))
    uids = {p["uid"] for p in policies["policies"]}
    for it in lineage["issues"]:
        if it.get("kind") != "series":
            continue
        stages = it["stages"]
        assert len({s["stage"][:10] for s in stages}) >= 2, f"同一天的一批不算系列:{it['issue_id']}"
        assert all(s["uid"] in uids for s in stages), "系列里的每份文件都必须在前台可见"
        assert [s["stage"][:10] for s in stages] == sorted(s["stage"][:10] for s in stages)
        assert "取代" not in it["summary_zh"].replace("是否取代", ""), "不得声称后一份取代前一份"
