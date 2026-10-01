"""临时探测脚本:经泰国出口查看官方站点结构。只打印片段,不写数据。"""
import re, sys, json
sys.path.insert(0, "backend")
from app.collect import source_client, UA

H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
c = source_client(H)

def get(url, n=1500, **kw):
    try:
        r = c.get(url, **kw)
        print(f"\n=== {url} -> {r.status_code} {r.headers.get('content-type','')} len={len(r.content)} final={r.url}")
        return r
    except Exception as e:
        print(f"\n=== {url} -> ERR {type(e).__name__}: {str(e)[:200]}")
        return None

def text(r, n=1500):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)[:n]

for url in sys.argv[1:]:
    r = get(url)
    if r is None: continue
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        print(r.text[:3000]); continue
    if "html" not in ct:
        print(r.text[:800]); continue
    print("TEXT:", text(r, 2000))
    print("LINKS:", sorted(set(re.findall(r'href="([^"#]{4,200})"', r.text)))[:80])
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
    print("SCRIPTS:", srcs[:20])
    print("API-ish:", sorted(set(re.findall(r'["\'](/?api/[^"\']{2,120}|https?://[^"\']*(?:api|service)[^"\']{0,120})["\']', r.text)))[:40])
    for s in srcs[:10]:
        su = s if s.startswith("http") else r.url.join(s)
        if "go.th" not in str(su): continue
        js = get(str(su))
        if js is None or js.status_code != 200: continue
        found = sorted(set(re.findall(r'["\'`]((?:https?://[a-z0-9.\-]+)?/?(?:api|services?|search|document)[a-zA-Z0-9_/\-\.\?=&{}$]{2,120})["\'`]', js.text)))
        print("  JS endpoints:", found[:60])
