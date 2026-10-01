"""临时探测:税务厅、BOI 官网结构(robots、RSS、公告列表)。只打印,不写数据。"""
import re, sys
sys.path.insert(0, "backend")
import httpx
from app.collect import source_client

H = {"User-Agent": "ThaiPolicyLineage/0.3 (+https://github.com/vsv1020/thai-policy-lineage)"}
proxied = source_client(H); proxied.timeout = httpx.Timeout(60)
direct = httpx.Client(headers=H, timeout=60, follow_redirects=True)
c = proxied
print("## 对照:经代理访问 data.go.th")
try:
    print(proxied.get("https://data.go.th/api/3/action/package_show", params={"id": "dataset_02_04"}).status_code)
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:120])
KW = re.compile(r"ประกาศ|คำสั่ง|กฎหมาย|ระเบียบ|announce|notification|law|regulat|rss|feed|news|ข่าว|policy|นโยบาย|มาตรการ", re.I)

def get(u):
    try:
        r = c.get(u)
        cf = "Just a moment" in r.text[:3000]
        print(f"\n=== {u} -> {r.status_code} {r.headers.get('content-type','')} len={len(r.content)} final={r.url} cloudflare={cf}")
        return r
    except Exception as e:
        print(f"\n=== {u} -> ERR {type(e).__name__}: {str(e)[:150]}")

import sys as _s
for c in (proxied, direct):
  print("\n######## 经代理" if c is proxied else "\n######## 直连(GitHub 美国机房)")
  for u in ["https://www.rd.go.th/robots.txt", "https://www.boi.go.th/robots.txt"]:
      r = get(u)
      if r is not None and r.status_code == 200: print(r.text[:800])

  for u in ["https://www.rd.go.th/", "https://www.rd.go.th/rss.xml", "https://www.boi.go.th/", "https://www.boi.go.th/en/index/",
            "https://www.boi.go.th/index.php?page=announcement", "https://www.boi.go.th/rss"]:
      r = get(u)
      if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", ""): 
          if r is not None and "xml" in r.headers.get("content-type", ""): print(r.text[:1500])
          continue
      print("FEEDS", re.findall(r'<link[^>]+(?:rss|atom)[^>]*>', r.text, re.I)[:5])
      links = []
      for href, txt in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', r.text, re.S):
          t = re.sub(r"<[^>]+>|\s+", " ", txt).strip()
          if KW.search(href) or KW.search(t):
              links.append(f"{t[:50]} -> {href[:120]}")
      print("LINKS", len(links)); print("\n".join(sorted(set(links))[:70]))
