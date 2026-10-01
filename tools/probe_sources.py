"""临时探测:BOI 内嵌 JSON 格式与数量;税务厅新法列表(直连)。只打印,不写数据。"""
import json, re
from collections import Counter
import httpx

c = httpx.Client(headers={"User-Agent": "ThaiPolicyLineage/0.3 (+https://github.com/vsv1020/thai-policy-lineage)"},
                 timeout=60, follow_redirects=True)
p = c.get("https://www.boi.go.th/index.php?page=boi_announcements")
m = re.search(r'id="dataMasterLaws"[^>]*>(.*?)</div>', p.text, re.S)
raw = m.group(1).strip() if m else ""
print("BOI raw head:", raw[:200].replace("\n", " "))
print("BOI raw tail:", raw[-200:].replace("\n", " "))
dec, objs, i = json.JSONDecoder(), [], 0
while True:
    j = raw.find("{", i)
    if j < 0: break
    try:
        o, end = dec.raw_decode(raw, j); objs.append(o); i = end
    except Exception as e:
        print("decode err at", j, e); i = j + 1
print("BOI objects:", len(objs), "keys:", sorted(objs[0]) if objs else None)
print("groups:", Counter(o.get("group_name") for o in objs).most_common(15))
print("years:", Counter(str(o.get("topic_date"))[:4] for o in objs).most_common(10))
recent = sorted((o for o in objs if str(o.get("topic_date")) >= "2026-04"), key=lambda o: o["topic_date"], reverse=True)
print("since 2026-04:", len(recent))
for o in recent[:25]:
    print("  ", o["topic_date"][:10], "|", o.get("group_name"), "|", o.get("topic_name"), "|", (o.get("topic_preview") or "")[:70], "|", o.get("file_path"), "|", (o.get("topic_source") or "")[:50], "|", o.get("topic_status"))
print("EN page same data?", "dataMasterLaws" in c.get("https://www.boi.go.th/un/boi_announcements").text)

r = c.get("https://www.rd.go.th/284.html")
print("\nRD 284", r.status_code, len(r.text))
for href, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', r.text, re.S):
    t = re.sub(r"<[^>]+>|\s+", " ", t).strip()
    if re.search(r"ใหม่|newlaw|ล่าสุด|พระราชกฤษฎีกา|ประกาศ|คำสั่ง|กฎกระทรวง", t + href):
        print("  ", t[:70], "->", href[:120])
