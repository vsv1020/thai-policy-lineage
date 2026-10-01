"""临时探测脚本:经泰国出口查看官方站点结构。只打印片段,不写数据。"""
import re, sys, json
sys.path.insert(0, "backend")
from app.collect import source_client

c = source_client({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"})

def get(url, **kw):
    try:
        r = c.get(url, **kw)
        print(f"\n=== {url} -> {r.status_code} {r.headers.get('content-type','')} len={len(r.content)} final={r.url}")
        return r
    except Exception as e:
        print(f"\n=== {url} -> ERR {type(e).__name__}: {str(e)[:200]}")

# 1. 公报 PDF 是否也被人机验证拦
r = get("https://ratchakitcha.soc.go.th/documents/111315.pdf")
if r is not None: print(r.content[:8])

# 2. 上游目录站:是否有比 data.go.th 更新的月份
for base in ("https://soc.gdcatalog.go.th", "https://data.go.th"):
    for q in ("ราชกิจจานุเบกษา", "มติคณะรัฐมนตรี"):
        r = get(f"{base}/api/3/action/package_search", params={"q": q, "rows": 10})
        if r is None or r.status_code != 200: continue
        try:
            res = r.json()["result"]
        except Exception:
            print(r.text[:300]); continue
        for p in res["results"]:
            rs = p.get("resources", [])
            names = sorted((x.get("last_modified") or x.get("created") or "", x.get("name", "")) for x in rs)[-3:]
            print("  PKG", p["name"], p.get("title", "")[:60], "| n_res", len(rs), "| modified", p.get("metadata_modified"), "| latest", names)

# 3. 内阁决议原始文件:除 docNews 外还有什么字段
r = get("https://soc.gdcatalog.go.th/dataset/dd04362c-f800-474d-85ef-72f9c06d9c45/resource/646d7902-fdb4-4a63-a56b-10b8824bdd03")
if r is not None:
    links = sorted(set(re.findall(r'href="(https?://[^"]+/download/[^"]+)"', r.text)))
    print("DOWNLOAD LINKS", links[:5])
    for u in links[:1]:
        d = get(u)
        if d is not None and d.status_code == 200:
            try:
                data = d.json()
            except Exception:
                print(d.text[:500]); continue
            rows = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
            print("ROWS", len(rows), "KEYS", sorted({k for x in rows for k in x})[:40])
            print("docNews non-empty", sum(1 for x in rows if str(x.get("docNews") or "").strip()))
            for x in rows[:2]: print("ROW", json.dumps(x, ensure_ascii=False)[:800])

# 4. 政府官网(内阁会议新闻)
for u in ("https://www.thaigov.go.th/", "https://www.thaigov.go.th/news/contents/cabinet"):
    r = get(u)
    if r is not None and "html" in r.headers.get("content-type", ""):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", r.text, flags=re.S)))
        print("TEXT", t[:400])
        print("LINKS", sorted(set(l for l in re.findall(r'href="([^"#]+)"', r.text) if "news" in l or "cabinet" in l))[:40])
