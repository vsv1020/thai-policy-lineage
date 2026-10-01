"""临时探测:税务厅 RSS 全部条目、BOI 公告列表结构(直连)。只打印,不写数据。"""
import re
import httpx

c = httpx.Client(headers={"User-Agent": "ThaiPolicyLineage/0.3 (+https://github.com/vsv1020/thai-policy-lineage)"},
                 timeout=60, follow_redirects=True)

r = c.get("https://www.rd.go.th/rss.xml")
items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
print("RD RSS items", len(items))
for it in items:
    g = lambda tag: (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1].strip()
    print(" |", g("pubDate")[:16], "|", g("link"), "|", re.sub(r"\s+", " ", g("title"))[:90])

for u in ["https://www.rd.go.th/26/9877.html"]:
    p = c.get(u)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", p.text, flags=re.S)))
    print("\nRD PAGE", u, p.status_code, t[:600])
    print("  pdf links:", re.findall(r'href="([^"]+\.pdf)"', p.text)[:5])

for u in ["https://www.boi.go.th/index.php?page=boi_announcements", "https://www.boi.go.th/un/boi_announcements",
          "https://www.boi.go.th/index.php?page=boi_announcements&language=th"]:
    p = c.get(u)
    print("\n=== BOI", u, p.status_code, len(p.text), p.url)
    rows = re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', p.text, re.S)
    out = []
    for href, txt in rows:
        t = re.sub(r"<[^>]+>|\s+", " ", txt).strip()
        if re.search(r"announce|ประกาศ|upload|\.pdf|topic_id", href + t, re.I) and len(t) > 8:
            out.append(f"{t[:90]} -> {href[:140]}")
    print("\n".join(out[:40]))
    dates = re.findall(r"\d{1,2}\s+(?:[A-Z][a-z]{2,8}|[ก-๙\.]{3,12})\s+\d{4}", p.text)
    print("DATES sample:", dates[:10])
