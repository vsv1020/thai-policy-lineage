"""临时探测:用真实网站跑新采集器(只打印,不写数据)。"""
import sys
from datetime import date
sys.path.insert(0, "backend")
from app import collect as C

for sid in ("rd_web", "boi_web"):
    src = next(s for s in C.SOURCES if s["id"] == sid)
    res = C.collect_source(src, C.Throttle(1.0), "2026-10-01T07:00:00+07:00", date(2025, 10, 1), dry_run=False)
    print(f"\n## {sid}: {res.status} — {res.detail}")
    for r in res.records[:40]:
        print("  ", r["dates"]["published_at"], r["uid"], r["legal_form_id"], r["status_id"], r["doc_no"], "|",
              r["titles"]["th"][:90], "|", r["sources"][0]["url"][-50:])
