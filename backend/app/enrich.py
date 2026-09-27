# -*- coding: utf-8 -*-
"""LLM 翻译分类:把自动采集进来的泰文条目补成可呈现的结构化记录。

    python3 -m app.enrich                 # 处理待办队列(title_zh 为空的条目)
    python3 -m app.enrich --limit 5       # 只处理 5 条
    python3 -m app.enrich --dry-run       # 只列出队列,不调用 API

为什么需要这一步:app.collect 从官方接口取回的是泰文标题 + 公报卷期 + 日期,
中文标题、摘要、领域、工具、方向全是空的或占位值 —— 不补这一步,自动采集的内容
没法直接呈现。

安全边界(与 collect 相同的三条红线,在这里再机械执行一遍):
- 王室相关标题**不发给模型**,直接跳过 —— 红线一要求零加工,翻译也是加工。
- 模型只能从词表里选 id(JSON schema 里的 enum),返回后再按词表校验一次。
- 产出一律 verified=false、direction.method="llm"(数据层保留,便于日后人工复核);
  前台不单独标注,由全站「非官方翻译,以泰文原文为准」的免责声明覆盖。
- 模型判定「与在泰外籍人士/企业无关」的条目(人事任免、地方工程招标等)
  标记为 skip,不会出现在首页,但保留在库里。

服务商(ENRICH_PROVIDER,留空自动选):
- deepseek:配了 DEEPSEEK_API_KEY 时默认用它。走官方 HTTP 接口(OpenAI 兼容格式)。
  它的 JSON 模式只保证返回合法 JSON,不保证字段齐全、枚举合规 —— 所以 validate_output
  逐字段检查,不合格的整条丢弃,和拒答一样处理。
- anthropic:Claude,结构化输出由接口按 JSON schema 强制约束。

两家都没配 key 时整个步骤跳过,采集照常工作。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime

import httpx

from .config import BKK, DATA_DIR, POLICIES_DIR, settings
from .db import init_db, session_scope
from .ingest import load_documents, read_jsonl

log = logging.getLogger("policy.enrich")

ROYAL_TERMS = ("พระบรมราชโองการ", "สมเด็จพระ", "พระบาทสมเด็จ", "ราชวงศ์",
               "เครื่องราชอิสริยาภรณ์", "พระราชทาน")

SYSTEM_PROMPT = """你是泰国政策数据库的编辑助手,把泰国皇家公报/内阁决议的泰文标题整理成中文结构化记录,
读者是在泰国生活和经商的华人(长居个人、中资企业、投资者)。

规则:
- title_zh:忠实翻译,保留文件类型与发文机关,不加评论、不夸大。
- summary_zh:1-2 句,说明谁受影响、要做什么。只根据标题能推出的内容写;推不出就只写
  「据标题,本文件涉及……;具体条款待原文核对」,绝不编造条款、金额、日期。
- relevant:这份文件是否与在泰外籍个人或外资企业相关。人事任免、授勋、地方工程招标、
  单个企业登记、宗教事务等一律 false。
- 所有 id 字段只能从给定枚举里选;拿不准就选最保守的值(direction 选 neutral,
  confidence 选 low)。
- 涉及王室的内容不在你的处理范围内(上游已过滤),若仍遇到,relevant 设为 false。"""


def _vocab() -> dict:
    return json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8"))


def output_schema(v: dict) -> dict:
    """JSON schema;枚举直接取自词表,模型没法造出词表外的 id。"""
    ids = lambda key: [e["id"] for e in v[key]]  # noqa: E731
    arr = lambda key, lo, hi: {"type": "array", "items": {"type": "string", "enum": ids(key)},  # noqa: E731
                               "minItems": lo, "maxItems": hi}
    return {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "title_zh": {"type": "string"},
            "summary_zh": {"type": "string"},
            "agency_ids": arr("agencies", 1, 3),
            "domain_ids": arr("domains", 1, 2),
            "legal_form_id": {"type": "string", "enum": ids("legal_forms")},
            "instrument_ids": arr("instruments", 0, 3),
            "goal_ids": arr("goals", 0, 2),
            "implementation_stage": {"type": "string", "enum": ids("implementation_stages")},
            "direction": {"type": "string", "enum": ids("directions")},
            "direction_confidence": {"type": "string", "enum": ["low", "med"]},
            "affected_parties": {
                "type": "array", "maxItems": 3,
                "items": {"type": "object",
                          "properties": {"party_id": {"type": "string", "enum": ids("parties")},
                                         "stance": {"type": "string", "enum": ids("stances")}},
                          "required": ["party_id", "stance"], "additionalProperties": False}},
        },
        "required": ["relevant", "title_zh", "summary_zh", "agency_ids", "domain_ids",
                     "legal_form_id", "instrument_ids", "goal_ids", "implementation_stage",
                     "direction", "direction_confidence", "affected_parties"],
        "additionalProperties": False,
    }


def vocab_brief(v: dict) -> str:
    """给模型看的词表中文释义 —— 只有 id 模型不知道 'rabiap' 是什么。放在 system 里
    便于缓存:词表不变,前缀就不变。"""
    lines = []
    for key in ("agencies", "domains", "legal_forms", "instruments", "goals",
                "implementation_stages", "parties"):
        items = ", ".join(f"{e['id']}={e.get('zh', '')}" + (f"({e['th']})" if e.get("th") else "")
                          for e in v[key])
        lines.append(f"{key}: {items}")
    return "\n".join(lines)


def is_pending(rec: dict) -> bool:
    return not (rec.get("titles") or {}).get("zh") and not (rec.get("flags") or {}).get("skip")


DEFAULT_MODELS = {"deepseek": "deepseek-chat", "anthropic": "claude-opus-5"}


def provider() -> str:
    """显式配置优先;否则有 DeepSeek key 就用 DeepSeek,再否则 Claude。"""
    if settings.enrich_provider in DEFAULT_MODELS:
        return settings.enrich_provider
    return "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "anthropic"


def model_name(prov: str | None = None) -> str:
    return settings.enrich_model_override or DEFAULT_MODELS[prov or provider()]


def has_credentials(prov: str | None = None) -> bool:
    if (prov or provider()) == "deepseek":
        return bool(os.getenv("DEEPSEEK_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                or os.getenv("ANTHROPIC_PROFILE"))


class DeepSeekClient:
    """DeepSeek 官方接口的最小客户端:POST {base}/chat/completions,OpenAI 兼容格式。
    用项目已有的 httpx,不为一个接口多引一个 SDK。transport 参数留给测试注入。"""

    def __init__(self, api_key: str, base_url: str, model: str, transport=None):
        self.model = model
        self.http = httpx.Client(base_url=base_url, timeout=120, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    def complete(self, system: str, user: str) -> tuple[str, str]:
        """返回 (文本, finish_reason)。429/5xx 退避重试两次,其余错误直接抛出。"""
        body = {"model": self.model, "max_tokens": 2000, "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        for attempt in range(3):
            r = self.http.post("/chat/completions", json=body)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
            r.raise_for_status()
            choice = r.json()["choices"][0]
            return (choice.get("message") or {}).get("content") or "", choice.get("finish_reason") or ""
        raise RuntimeError("unreachable")


def _user_message(rec: dict) -> str:
    th = (rec.get("titles") or {}).get("th", "")
    d = rec.get("dates") or {}
    return (f"泰文标题:{th}\n"
            f"公报/文号:{rec.get('doc_no') or '无'}\n"
            f"日期:刊登 {d.get('published_at') or '—'} / 决议 {d.get('resolved_at') or '—'}\n"
            f"来源管线:{(rec.get('provenance') or {}).get('pipeline')}")


def _parse(text: str, uid: str) -> dict | None:
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        log.warning("JSON 解析失败,跳过 %s", uid)
        return None
    return out if isinstance(out, dict) else None


def call_deepseek(client: DeepSeekClient, v: dict, rec: dict) -> dict | None:
    # JSON 模式要求提示词里出现 "json" 并给出格式;schema 放在 system 末尾,
    # 整段 system 每条都一样,DeepSeek 会自动缓存这段前缀
    system = (SYSTEM_PROMPT + "\n\n词表:\n" + vocab_brief(v)
              + "\n\n只输出一个 json 对象,不要任何其他文字。字段、类型与可选值必须严格符合以下 JSON Schema:\n"
              + json.dumps(output_schema(v), ensure_ascii=False))
    text, finish = client.complete(system, _user_message(rec))
    if finish == "length":
        log.warning("输出被截断,跳过 %s", rec["uid"])
        return None
    if finish == "content_filter" or not text.strip():
        log.warning("模型未返回内容(%s),跳过 %s", finish or "空", rec["uid"])
        return None
    return _parse(text, rec["uid"])


def call_model(client, v: dict, rec: dict) -> dict | None:
    """单条调用。拒答或解析失败返回 None,调用方跳过该条。"""
    if isinstance(client, DeepSeekClient):
        return call_deepseek(client, v, rec)
    user = _user_message(rec)
    resp = client.beta.messages.create(
        model=model_name("anthropic"),
        max_tokens=4000,
        # 拒答时由服务端按类别自动换备用模型重跑,不需要自己维护模型列表
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": output_schema(v)}},
        system=[{"type": "text", "text": SYSTEM_PROMPT + "\n\n词表:\n" + vocab_brief(v),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        log.warning("模型拒答,跳过 %s", rec["uid"])
        return None
    if resp.stop_reason == "max_tokens":
        log.warning("输出被截断,跳过 %s", rec["uid"])
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return _parse(text, rec["uid"])


def validate_output(out: dict, v: dict) -> str | None:
    """字段级检查,返回问题描述;None = 合格。Claude 的结构化输出本就满足这些,
    DeepSeek 的 JSON 模式不保证 —— 缺字段、类型错、必选枚举不在词表里,整条丢弃。"""
    if not isinstance(out.get("relevant"), bool):
        return "relevant 不是布尔值"
    for k in ("title_zh", "summary_zh"):
        if not isinstance(out.get(k), str):
            return f"{k} 缺失或不是字符串"
    if out["relevant"] and not out["title_zh"].strip():
        return "title_zh 为空"
    if not out["relevant"]:
        return None                    # 无关条目只用到 title_zh
    for k in ("agency_ids", "domain_ids", "instrument_ids", "goal_ids", "affected_parties"):
        if not isinstance(out.get(k), list):
            return f"{k} 缺失或不是数组"
    for k, vocab_key in (("legal_form_id", "legal_forms"),
                         ("implementation_stage", "implementation_stages"),
                         ("direction", "directions")):
        if out.get(k) not in {e["id"] for e in v[vocab_key]}:
            return f"{k}={out.get(k)!r} 不在词表里"
    if out.get("direction_confidence") not in ("low", "med"):
        return "direction_confidence 不合法"
    if not isinstance(out.get("affected_parties"), list) or \
            not all(isinstance(x, dict) for x in out["affected_parties"]):
        return "affected_parties 格式不对"
    return None


def apply_enrichment(rec: dict, out: dict, v: dict, model: str) -> dict:
    """把模型输出合并进记录。再按词表过一遍 —— schema 约束之外的第二道闸。"""
    valid = {k: {e["id"] for e in v[k]} for k in
             ("agencies", "domains", "legal_forms", "instruments", "goals",
              "implementation_stages", "directions", "parties", "stances")}
    keep = lambda xs, k: [x for x in xs if x in valid[k]]  # noqa: E731
    rec = json.loads(json.dumps(rec))          # 深拷贝,别改调用方的对象
    now = datetime.now(BKK).replace(microsecond=0).isoformat()

    if not out.get("relevant", True):
        rec.setdefault("flags", {})["skip"] = True
        rec["titles"]["zh"] = out.get("title_zh", "")[:200]
        rec["note"] = (rec.get("note", "") + f" | {now} LLM 判定与在泰外籍人士/企业无关,不上首页").strip(" |")
        return rec

    rec["titles"]["zh"] = out["title_zh"].strip()[:300]
    rec["summary_zh"] = out["summary_zh"].strip()[:1200]
    rec["agency_ids"] = keep(out["agency_ids"], "agencies") or rec.get("agency_ids") or ["cabinet"]
    rec["domain_ids"] = keep(out["domain_ids"], "domains") or rec.get("domain_ids")
    if out["legal_form_id"] in valid["legal_forms"]:
        rec["legal_form_id"] = out["legal_form_id"]
    rec["instrument_ids"] = keep(out["instrument_ids"], "instruments")
    rec["goal_ids"] = keep(out["goal_ids"], "goals")
    if out["implementation_stage"] in valid["implementation_stages"]:
        rec["implementation_stage"] = out["implementation_stage"]
    rec["direction"] = {"value": out["direction"] if out["direction"] in valid["directions"]
                        else "neutral",
                        "confidence": out.get("direction_confidence", "low"),
                        "method": "llm"}
    rec["affected_parties"] = [p for p in out.get("affected_parties", [])
                               if p.get("party_id") in valid["parties"]
                               and p.get("stance") in valid["stances"]]
    prov = rec.setdefault("provenance", {})
    prov["verified"] = False                   # 模型产出永远不算人工复核
    prov["verified_at"] = None
    prov["enriched_by"] = model
    prov["enriched_at"] = now
    # 替换采集时「待翻译」的占位说明;详情页「数据说明」展示的就是这一句
    src = {"gazette_json": "官方公报索引", "cabinet_json": "内阁决议数据"}.get(prov.get("pipeline"), "官方来源")
    rec["note"] = f"自{src}自动收录;中文标题、摘要与分类依泰文原题整理,以泰文原文为准"
    return rec


def rewrite_jsonl(updated: dict[str, dict]) -> None:
    """按 uid 原位替换行,保持文件顺序 —— diff 只出现被改的那几行。"""
    path = POLICIES_DIR / "documents.jsonl"
    lines = []
    for rec in read_jsonl(path):
        lines.append(json.dumps(updated.get(rec["uid"], rec), ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_enrichment(limit: int | None = None, dry_run: bool = False, client=None) -> dict:
    limit = limit or settings.enrich_max_per_run
    records = read_jsonl(POLICIES_DIR / "documents.jsonl")
    queue = [r for r in records if is_pending(r)]
    result = {"pending": len(queue), "processed": 0, "enriched": 0, "skipped_irrelevant": 0,
              "skipped_red_line": 0, "failed": 0, "status": "ok"}
    if not queue:
        return result
    if dry_run:
        result["status"] = "dry_run"
        result["queue"] = [r["uid"] for r in queue[:limit]]
        return result
    prov = provider()
    if client is None:
        if not has_credentials(prov):
            result["status"] = "no_credentials"
            log.info("没有 %s,跳过翻译分类(%d 条待处理)",
                     "DEEPSEEK_API_KEY" if prov == "deepseek" else "ANTHROPIC_API_KEY", len(queue))
            return result
        if prov == "deepseek":
            client = DeepSeekClient(os.environ["DEEPSEEK_API_KEY"], settings.deepseek_base_url,
                                    model_name(prov))
        else:
            import anthropic
            client = anthropic.Anthropic()
    model = client.model if isinstance(client, DeepSeekClient) else model_name("anthropic")
    result["provider"], result["model"] = ("deepseek" if isinstance(client, DeepSeekClient)
                                           else "anthropic"), model

    v = _vocab()
    updated: dict[str, dict] = {}
    todo = []
    for rec in queue[:limit]:
        result["processed"] += 1
        th = (rec.get("titles") or {}).get("th", "")
        if any(t in th for t in ROYAL_TERMS):
            rec = json.loads(json.dumps(rec))
            rec.setdefault("flags", {})["skip"] = True
            rec["note"] = (rec.get("note", "") + " | 王室相关,按红线一不做任何加工").strip(" |")
            updated[rec["uid"]] = rec
            result["skipped_red_line"] += 1
            continue
        todo.append(rec)

    def call(rec: dict) -> dict | None:
        try:
            return call_model(client, v, rec)
        except Exception as exc:               # 单条失败不能拖垮整轮
            log.warning("调用失败 %s: %s", rec["uid"], exc)
            return None

    # 并发调用模型:回填历史数据时一次几百条,串行要一个多小时。结果按原顺序合并
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, settings.enrich_concurrency)) as pool:
        outputs = list(pool.map(call, todo))

    for rec, out in zip(todo, outputs):
        problem = None if out is None else validate_output(out, v)
        if problem:
            log.warning("输出不合格,跳过 %s:%s", rec["uid"], problem)
        if out is None or problem:
            result["failed"] += 1
            continue
        new = apply_enrichment(rec, out, v, model)
        updated[rec["uid"]] = new
        if (new.get("flags") or {}).get("skip"):
            result["skipped_irrelevant"] += 1
        else:
            result["enriched"] += 1

    if updated:
        rewrite_jsonl(updated)
        init_db()
        with session_scope() as s:
            load_documents(s, list(updated.values()))
    if result["failed"] and not result["enriched"]:
        result["status"] = "failed"
    result["pending_after"] = len(queue) - len(updated)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 翻译分类")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run_enrichment(args.limit, args.dry_run), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
