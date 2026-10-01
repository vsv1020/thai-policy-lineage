"""临时:对刚采进来的新来源抽样翻译,打印结果。只在 Actions 里跑,不提交任何数据。"""
import json, os, sys
sys.path.insert(0, "backend")
from app import enrich as E
from app.ingest import read_jsonl
from app.config import POLICIES_DIR, settings
from app.persons import redact, output_person_reason

recs = read_jsonl(POLICIES_DIR / "documents.jsonl")
pend = [r for r in recs if E.is_pending(r)]
by = {}
for r in pend:
    by.setdefault(r["provenance"]["pipeline"], []).append(r)
print({k: len(v) for k, v in by.items()})
sample = by.get("rd_web", [])[:2] + by.get("boi_web", [])[:3] + by.get("cabinet_json", [])[:2]
client = E.DeepSeekClient(os.environ["DEEPSEEK_API_KEY"], settings.deepseek_base_url, E.model_name("deepseek"))
fetch = E._default_fetcher()
v = E._vocab()
for r in sample:
    text, how = fetch(r)
    text, n = redact(text)
    out = E.call_model(client, v, r, text)
    print("\n####", r["uid"], "| 正文", how or "无", len(text), "字 | 去名", n)
    print("TH:", r["titles"]["th"][:120])
    if not out:
        print("  模型无输出"); continue
    print("  校验:", E.validate_output(out, v) or "OK",
          "| 人名:", output_person_reason(json.dumps([out.get("title_zh"), out.get("summary_zh"), out.get("key_points")], ensure_ascii=False)) or "无")
    print("  ZH:", out.get("title_zh"))
    print("  摘要:", out.get("summary_zh"))
    for k in out.get("key_points") or []:
        print("   -", k)
    print("  领域/机关/相关:", out.get("domain_ids"), out.get("agency_ids"), out.get("relevant"), "| 生效:", out.get("effective_rule"), out.get("effective_date"))
