"""临时探测脚本:内阁决议 PDF 能否下载、能否读出正文。只打印片段,不写数据。"""
import sys, json
sys.path.insert(0, "backend")
from app.collect import source_client
from app import fulltext as F

c = source_client({"User-Agent": "ThaiPolicyLineage/0.3"})
u = "https://soc.gdcatalog.go.th/dataset/dd04362c-f800-474d-85ef-72f9c06d9c45/resource/646d7902-fdb4-4a63-a56b-10b8824bdd03/download/cabinet2569.json"
rows = c.get(u).json()
from collections import Counter
names = Counter()
for r in rows:
    for d in r.get("docNews") or []:
        names[(d.get("file_name") or "").split("(")[0].strip()] += 1
print("file_name kinds:", names.most_common(12))
print("links per row:", Counter(len(r.get("docNews") or []) for r in rows).most_common())
print("hosts:", Counter(d.get("file_link", "").split("/")[2] for r in rows for d in r.get("docNews") or [] if d.get("file_link")))
for r in rows[:4]:
    for d in (r.get("docNews") or [])[:2]:
        rec = {"sources": [{"role": "official", "url": d["file_link"]}]}
        text, how = F.fetch_fulltext(rec, c)
        print("\n##", r["toP_SERLNO"], d["file_name"], "->", how, len(text))
        print(text[:500].replace("\n", " "))
print("misses", json.dumps(F.misses(), ensure_ascii=False)[:600])
# retrigger
