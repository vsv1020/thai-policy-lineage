"""临时探测:税务厅「新法」列表页、BOI 公告数据接口(直连)。只打印,不写数据。"""
import re
import httpx

c = httpx.Client(headers={"User-Agent": "ThaiPolicyLineage/0.3 (+https://github.com/vsv1020/thai-policy-lineage)"},
                 timeout=60, follow_redirects=True)

def links(html, pat):
    out = []
    for href, txt in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", txt).strip()
        if re.search(pat, href + " " + t, re.I):
            out.append(f"{t[:80]} -> {href[:150]}")
    return sorted(set(out))

# 1. 税务厅:找「กฎหมายใหม่ / newlaw」列表页
seen = set()
for u in ["https://www.rd.go.th/landing.html", "https://www.rd.go.th/26/9877.html"]:
    p = c.get(u)
    for l in links(p.text, r"กฎหมาย|newlaw|law"):
        if l not in seen:
            seen.add(l); print("RD", l)
for cand in [l.split(" -> ")[1] for l in seen if "กฎหมายใหม่" in l or "newlaw" in l.lower()][:3]:
    u = cand if cand.startswith("http") else "https://www.rd.go.th/" + cand.lstrip("/")
    p = c.get(u)
    print("\n=== RD LIST", u, p.status_code, len(p.text))
    pdfs = re.findall(r'<a[^>]+href="([^"]*newlaw[^"]*\.pdf)"[^>]*>(.*?)</a>', p.text, re.S)
    print("newlaw pdfs:", len(pdfs))
    for href, t in pdfs[:25]:
        print("  ", re.sub(r"<[^>]+>|\s+", " ", t).strip()[:100], "->", href)
    i = p.text.find("newlaw")
    print("CONTEXT:", re.sub(r"\s+", " ", p.text[max(0, i - 1200):i + 300]))

# 2. BOI:dataLaw 的数据来自哪里
p = c.get("https://www.boi.go.th/index.php?page=boi_announcements")
for key in ("dataLaw", "axios", "fetch(", "$.ajax", "$.get", "$.post", ".json", "api/"):
    for m in list(re.finditer(re.escape(key), p.text))[:3]:
        print(f"\nBOI [{key}]", re.sub(r"\s+", " ", p.text[max(0, m.start() - 250):m.start() + 350]))
m = re.search(r"8 มกราคม 2569", p.text)
if m:
    print("\nBOI DATE CONTEXT", re.sub(r"\s+", " ", p.text[max(0, m.start() - 900):m.start() + 300]))
