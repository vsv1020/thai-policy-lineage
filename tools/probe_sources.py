"""临时:列出新规则下新放行的公报标题,检查有没有人名。只打印,不提交。"""
import json, re, sys, random
from collections import Counter
sys.path.insert(0, "backend")
from app.ingest import read_jsonl
from app.config import POLICIES_DIR

old = {json.loads(l)["uid"] for l in open("/tmp/before.jsonl")}
new = [r for r in read_jsonl(POLICIES_DIR / "documents.jsonl") if r["uid"] not in old
       and r["provenance"]["pipeline"] == "gazette_json"]
print("new gazette", len(new))
OLD = re.compile(r"(นาย|นาง|นางสาว)\s*\S")
hit = [r["titles"]["th"] for r in new if OLD.search(r["titles"]["th"])]
print("含 นาย/นาง 字样:", len(hit))
ctx = Counter()
for t in hit:
    for m in OLD.finditer(t):
        ctx[t[m.start():m.start() + 14]] += 1
for k, v in ctx.most_common(80):
    print(f"  {v:4d} {k}")
heads = Counter(re.split(r"\s|เรื่อง", r["titles"]["th"])[0][:30] for r in new)
print("\n标题开头:")
for k, v in heads.most_common(40):
    print(f"  {v:4d} {k}")
random.seed(1)
print("\n随机样本:")
for r in random.sample(new, min(60, len(new))):
    print("  ", r["titles"]["th"][:150])
