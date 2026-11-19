"""临时:看 2023-11~2024-02 几个月为什么一条都没过,字段长什么样。只打印。"""
import json, sys
from collections import Counter
sys.path.insert(0, "backend")
import httpx
from app import collect as C

th = C.Throttle(1.0)
with C.source_client({"User-Agent": C.UA, "Accept": "application/json"}) as client:
    client.timeout = httpx.Timeout(120)
    res = C.fetch_ckan("dataset_02_04", th, client)
    for r in sorted(res, key=C.resource_period):
        per = C.resource_period(r)
        if not ((2023, 11) <= per <= (2024, 2) or per in ((2024, 6), (2024, 7), (2024, 3))):
            continue
        print("\n==", per, r.get("name"), r.get("format"), r.get("datastore_active"), (r.get("url") or "")[:120])
        try:
            payload, via = C.download(r, th, client)
        except Exception as e:
            print("FAIL", e); continue
        rows = C.iter_records(payload)
        print("rows", len(rows), "via", via, "type", type(payload).__name__)
        if rows:
            print("keys", list(rows[0].keys())[:20])
            for x in rows[:2]:
                print("  ", json.dumps(x, ensure_ascii=False)[:500])
        why = Counter(C.normalize_gazette(x, "x")[1] for x in rows)
        print("skip reasons", why.most_common(6))
