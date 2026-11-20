"""临时只读探测:找出生成末尾连字符 uid 的源记录,并在真实标题上对比修复前后的 slug。不写任何数据。"""
import json, re, sys
from collections import Counter
sys.path.insert(0, "backend")
import httpx
from app import collect as C

UID_RE = re.compile(r"^TH-[A-Z0-9]+-[A-Z0-9]+(-[A-Z0-9]+)*$")

def slug_old(text, limit=5):
    words = re.findall(r"[A-Za-z0-9]+", text)
    if words:
        return "-".join(w.upper() for w in words[:limit])[:48]
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10].upper()

th = C.Throttle(1.0)
titles = []          # (来源, uid 前缀, 标题)
with C.source_client({"User-Agent": C.UA, "Accept": "application/json"}) as client:
    client.timeout = httpx.Timeout(120)
    for src in C.SOURCES:
        if src.get("kind") == "agency":
            continue
        res = C.fetch_ckan(src["dataset"], th, client)
        usable = [r for r in res if r.get("datastore_active") or (r.get("format") or "").lower() == "json"]
        usable.sort(key=C.resource_period, reverse=True)
        take = usable if src["id"] == "cabinet_json" else usable[:3]
        norm = C.normalize_cabinet if src["id"] == "cabinet_json" else C.normalize_gazette
        for r in take:
            payload, _ = C.download(r, th, client)
            for rec in C.iter_records(payload):
                n, why = norm(rec, "x")
                if n is None:
                    continue
                prefix = n["uid"].rsplit("-", 1)[0] if False else None
                titles.append((src["id"], n, rec))

print("标题样本数", len(titles), Counter(s for s, _, _ in titles))
bad = [(s, n, rec) for s, n, rec in titles if not UID_RE.match(n["uid"])]
print("\n## 当前代码生成的不合规 uid:", len(bad))
for s, n, rec in bad:
    print(" ", s, n["uid"])
    print("    原始记录:", json.dumps({k: (v if k != "docNews" else f"[{len(v)} 个附件]") for k, v in rec.items()}, ensure_ascii=False)[:600])

changed, after = 0, Counter()
for s, n, rec in titles:
    t = n["titles"]["th"]
    o, f = slug_old(t), C.slug(t)
    if o != f:
        changed += 1
        print("  slug 变化:", o, "→", f)
    date = n["uid"].split("-")[2]
    after[(n["uid"].split("-")[1], date, f)] += 1
print("\n## 修复前后 slug 不同的条数:", changed)
dup_new = [k for k, v in after.items() if v > 1]
before = Counter((n["uid"].split("-")[1], n["uid"].split("-")[2], slug_old(n["titles"]["th"])) for _, n, _ in titles)
print("## 修复前同批撞号组数:", sum(1 for v in before.values() if v > 1), " 修复后:", len(dup_new))
print("## 修复后新增的撞号组:", [k for k in dup_new if before.get((k[0], k[1], k[2] + "-"), 0) and before[k] == 0][:5])
