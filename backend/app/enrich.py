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

正文(app.fulltext):有官方 PDF 原文时先下载并抽取泰文正文,连同标题一起交给模型,
摘要写出实质内容、列出要点、按正文推出生效日;拿不到正文就退回只看标题。
早先只凭标题写的摘要会被逐步重做(每轮在新条目之后、同一个上限内)。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta

import httpx

from .config import BKK, DATA_DIR, POLICIES_DIR, settings
from .db import init_db, session_scope
from .ingest import load_documents, read_jsonl

log = logging.getLogger("policy.enrich")

ROYAL_TERMS = ("พระบรมราชโองการ", "สมเด็จพระ", "พระบาทสมเด็จ", "ราชวงศ์",
               "เครื่องราชอิสริยาภรณ์", "พระราชทาน")
# 模型输出里也不得出现王室相关表述(与 tools/validate.py 的红线一保持一致)。
# 读正文后模型可能写出「经国王御准」之类的话 —— 命中就按红线一整条跳过,不写入任何译文
ROYAL_OUTPUT_TERMS = ROYAL_TERMS + ("王室", "国王", "王后", "御准", "冒犯君主")

SYSTEM_PROMPT = """你是泰国政策数据库的编辑助手,把泰国皇家公报/内阁决议整理成中文结构化记录,
读者是在泰国生活和经商的华人(长居个人、中资企业、投资者)。输入有泰文标题,多数还附有正文(从官方 PDF 抽取,
可能有少量识别错字,按上下文理解即可)。

规则:
- title_zh:忠实翻译,保留文件类型与发文机关,不加评论、不夸大。
- summary_zh:
  · 有正文时:2-4 句,写清这份文件做了什么、谁受影响、要做什么/不能做什么、关键数字与期限。
    只写正文里明确写着的内容,不推测、不评论。
  · 没有正文时:1-2 句,只写标题能推出的内容;推不出就写「据标题,本文件涉及……;具体条款待原文核对」。
  · 任何情况下都不编造条款、金额、日期。
  · 不要提及国王、王室、御准、签署颁布的程序性内容(如「经国王御准颁布」),只写政策本身。
- key_points:仅在有正文时填写,3-5 条,每条一句中文(不超过 60 字),列出最实用的信息:
  适用对象、具体义务或权利、金额/比例、期限、办理机关。正文里没有的信息不要写;没有正文时给空数组。
- effective_rule:正文如何规定生效。day_after_publication = 「自公报刊登次日起施行」
  (ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษา);on_publication = 自刊登之日起;
  explicit_date = 写明了具体日期(同时填 effective_date,格式 YYYY-MM-DD,佛历年减 543);
  none = 没有正文或正文没写。effective_date 在其他情况下填空字符串。
- relevant:这份文件是否与在泰外籍个人或外资企业相关。人事任免、授勋、地方工程招标、
  单个企业登记、宗教事务等一律 false。
- 所有 id 字段只能从给定枚举里选;拿不准就选最保守的值(direction 选 neutral,
  confidence 选 low)。
- 涉及王室的内容不在你的处理范围内(上游已过滤),若仍遇到,relevant 设为 false。"""


def _vocab() -> dict:
    return json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8"))


EFFECTIVE_RULES = ["none", "on_publication", "day_after_publication", "explicit_date"]
UPGRADE_MAX_ATTEMPTS = 3     # 正文拿不到的条目最多重试几轮,之后不再占用每日额度


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
            "key_points": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
            "effective_rule": {"type": "string", "enum": EFFECTIVE_RULES},
            "effective_date": {"type": "string"},
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


def needs_fulltext_upgrade(rec: dict) -> bool:
    """早先只凭标题翻译的相关条目:有 PDF 原文、还没用正文重做过、重试没超过上限。"""
    from .fulltext import pdf_url
    prov = rec.get("provenance") or {}
    return (bool((rec.get("titles") or {}).get("zh")) and not (rec.get("flags") or {}).get("skip")
            and bool(prov.get("enriched_by")) and prov.get("summary_basis") != "fulltext"
            and int(prov.get("fulltext_attempts", 0) or 0) < UPGRADE_MAX_ATTEMPTS
            and bool(pdf_url(rec)))


def is_pending(rec: dict) -> bool:
    """待翻译:没有中文标题、未被跳过,且有可考证的官方原文 —— 没有原文的条目上不了前台,不花钱翻译。"""
    from .ingest import official_sources
    return (not (rec.get("titles") or {}).get("zh") and not (rec.get("flags") or {}).get("skip")
            and bool(official_sources(rec)))


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


def _user_message(rec: dict, fulltext: str = "") -> str:
    th = (rec.get("titles") or {}).get("th", "")
    d = rec.get("dates") or {}
    msg = (f"泰文标题:{th}\n"
           f"公报/文号:{rec.get('doc_no') or '无'}\n"
           f"日期:刊登 {d.get('published_at') or '—'} / 决议 {d.get('resolved_at') or '—'}\n"
           f"来源管线:{(rec.get('provenance') or {}).get('pipeline')}\n")
    if fulltext:
        return msg + f"\n正文(官方 PDF 抽取):\n<<<\n{fulltext}\n>>>"
    return msg + "\n正文:无(只能依据标题)"


def _parse(text: str, uid: str) -> dict | None:
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        log.warning("JSON 解析失败,跳过 %s", uid)
        return None
    return out if isinstance(out, dict) else None


def call_deepseek(client: DeepSeekClient, v: dict, rec: dict, fulltext: str = "") -> dict | None:
    # JSON 模式要求提示词里出现 "json" 并给出格式;schema 放在 system 末尾,
    # 整段 system 每条都一样,DeepSeek 会自动缓存这段前缀
    system = (SYSTEM_PROMPT + "\n\n词表:\n" + vocab_brief(v)
              + "\n\n只输出一个 json 对象,不要任何其他文字。字段、类型与可选值必须严格符合以下 JSON Schema:\n"
              + json.dumps(output_schema(v), ensure_ascii=False))
    text, finish = client.complete(system, _user_message(rec, fulltext))
    if finish == "length":
        log.warning("输出被截断,跳过 %s", rec["uid"])
        return None
    if finish == "content_filter" or not text.strip():
        log.warning("模型未返回内容(%s),跳过 %s", finish or "空", rec["uid"])
        return None
    return _parse(text, rec["uid"])


def call_model(client, v: dict, rec: dict, fulltext: str = "") -> dict | None:
    """单条调用。拒答或解析失败返回 None,调用方跳过该条。"""
    if isinstance(client, DeepSeekClient):
        return call_deepseek(client, v, rec, fulltext)
    user = _user_message(rec, fulltext)
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
    kp = out.get("key_points", [])
    if not isinstance(kp, list) or not all(isinstance(x, str) for x in kp):
        return "key_points 格式不对"
    rule = out.get("effective_rule", "none")
    if rule not in EFFECTIVE_RULES:
        return f"effective_rule={rule!r} 不合法"
    if rule == "explicit_date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", out.get("effective_date") or ""):
        return "effective_date 格式不对"
    if not isinstance(out.get("affected_parties"), list) or \
            not all(isinstance(x, dict) for x in out["affected_parties"]):
        return "affected_parties 格式不对"
    return None


def effective_from(rule: str, explicit: str, published: str | None) -> str | None:
    """按正文的生效规定推出生效日;推不出返回 None(不覆盖已有日期)。"""
    try:
        pub = date.fromisoformat(published) if published else None
    except ValueError:
        pub = None
    if rule == "on_publication" and pub:
        return pub.isoformat()
    if rule == "day_after_publication" and pub:
        return (pub + timedelta(days=1)).isoformat()
    if rule == "explicit_date":
        try:
            d = date.fromisoformat(explicit)
        except ValueError:
            return None
        if d.year > 2400:                      # 模型忘了把佛历换成公历
            d = d.replace(year=d.year - 543)
        # 离刊登日太远的多半是抽错了,不采用
        if pub is None or abs((d - pub).days) <= 3 * 366:
            return d.isoformat()
    return None


def apply_enrichment(rec: dict, out: dict, v: dict, model: str, basis: str = "title") -> dict:
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
    points = [re.sub(r"^[\s·•\-\d.、)]+", "", x).strip()[:120] for x in out.get("key_points") or []]
    rec["key_points_zh"] = [x for x in points if x][:5] if basis == "fulltext" else []
    dates = rec.setdefault("dates", {})
    eff = effective_from(out.get("effective_rule", "none"), out.get("effective_date", ""),
                         dates.get("published_at")) if basis == "fulltext" else None
    if eff and not dates.get("effective_from"):
        dates["effective_from"] = eff
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
    prov["summary_basis"] = basis
    # 替换采集时「待翻译」的占位说明;详情页「数据说明」展示的就是这一句
    src = {"gazette_json": "官方公报索引", "cabinet_json": "内阁决议数据"}.get(prov.get("pipeline"), "官方来源")
    what = "泰文原文正文" if basis == "fulltext" else "泰文原题"
    rec["note"] = f"自{src}自动收录;中文标题、摘要与分类依{what}整理,以泰文原文为准"
    return rec


def rewrite_jsonl(updated: dict[str, dict]) -> None:
    """按 uid 原位替换行,保持文件顺序 —— diff 只出现被改的那几行。"""
    path = POLICIES_DIR / "documents.jsonl"
    lines = []
    for rec in read_jsonl(path):
        lines.append(json.dumps(updated.get(rec["uid"], rec), ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _default_fetcher():
    """真实的正文获取器:经泰国出口下载官方 PDF。ENRICH_FULLTEXT=0 时关闭(测试、离线)。"""
    if not settings.enrich_fulltext:
        return None
    from .collect import source_client
    from .fulltext import fetch_fulltext
    client = source_client({"User-Agent": "ThaiPolicyLineage/1.0 (+https://www.thaipolicy.com)"})
    return lambda rec: fetch_fulltext(rec, client)


def run_enrichment(limit: int | None = None, dry_run: bool = False, client=None,
                   fetch_text=None) -> dict:
    """fetch_text(rec) -> (正文, 方式);None = 用默认获取器(ENRICH_FULLTEXT=0 时不取正文)。"""
    limit = limit or settings.enrich_max_per_run
    records = read_jsonl(POLICIES_DIR / "documents.jsonl")
    pending = [r for r in records if is_pending(r)]
    # 新条目优先;剩余额度用来把早先只凭标题写的摘要按正文重做
    upgrades = [r for r in records if needs_fulltext_upgrade(r)] if settings.enrich_fulltext or fetch_text else []
    queue = pending + upgrades
    result = {"pending": len(pending), "upgrade_pending": len(upgrades), "processed": 0, "enriched": 0,
              "upgraded": 0, "fulltext": 0, "ocr": 0, "skipped_irrelevant": 0,
              "skipped_red_line": 0, "failed": 0, "status": "ok"}
    if not queue:
        return result
    if dry_run:
        result["status"] = "dry_run"
        result["queue"] = [r["uid"] for r in queue[:limit]]
        return result
    if fetch_text is None:
        fetch_text = _default_fetcher()
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
            rec["note"] = (rec.get("note", "") + " | 触及红线一,不做任何加工").strip(" |")
            updated[rec["uid"]] = rec
            result["skipped_red_line"] += 1
            continue
        todo.append(rec)

    upgrade_ids = {r["uid"] for r in upgrades}

    def call(rec: dict) -> tuple[dict | None, str]:
        text, how = "", ""
        if fetch_text:
            try:
                text, how = fetch_text(rec)
            except Exception as exc:           # noqa: BLE001 —— 取正文失败就只看标题
                log.info("取正文失败 %s: %s", rec["uid"], exc)
        if rec["uid"] in upgrade_ids and not text:
            return None, "no_text"             # 重做的意义就在正文;没拿到就留到下一轮
        try:
            return call_model(client, v, rec, text), how
        except Exception as exc:               # 单条失败不能拖垮整轮
            log.warning("调用失败 %s: %s", rec["uid"], exc)
            return None, how

    # 并发调用模型:回填历史数据时一次几百条,串行要一个多小时。结果按原顺序合并
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, settings.enrich_concurrency)) as pool:
        outputs = list(pool.map(call, todo))

    for rec, (out, how) in zip(todo, outputs):
        is_upgrade = rec["uid"] in upgrade_ids
        if how == "no_text":
            # 记下尝试次数,超过上限后不再占用每日额度
            rec = json.loads(json.dumps(rec))
            prov = rec.setdefault("provenance", {})
            prov["fulltext_attempts"] = int(prov.get("fulltext_attempts", 0) or 0) + 1
            updated[rec["uid"]] = rec
            continue
        problem = None if out is None else validate_output(out, v)
        if problem:
            log.warning("输出不合格,跳过 %s:%s", rec["uid"], problem)
        if out is None or problem:
            result["failed"] += 1
            continue
        text_out = json.dumps([out.get("title_zh"), out.get("summary_zh"), out.get("key_points")],
                              ensure_ascii=False)
        hit = next((t for t in ROYAL_OUTPUT_TERMS if t in text_out), None)
        if hit:
            # 红线一:不写入任何模型输出,标记跳过,留给人工判断
            rec = json.loads(json.dumps(rec))
            rec.setdefault("flags", {})["skip"] = True
            # 说明里不能再写出命中的词,否则整条记录又会被 validate.py 的红线检查拒收
            rec["note"] = (rec.get("note", "") + " | 译文触及红线一,不做加工,待人工处理").strip(" |")
            updated[rec["uid"]] = rec
            result["skipped_red_line"] += 1
            continue
        if is_upgrade and not out.get("relevant", True):
            # 重做时不推翻早先的「相关」判定,只更新内容
            out = {**out, "relevant": True}
        new = apply_enrichment(rec, out, v, model, "fulltext" if how else "title")
        updated[rec["uid"]] = new
        result["fulltext"] += bool(how)
        result["ocr"] += how == "ocr"
        if is_upgrade:
            result["upgraded"] += 1
        elif (new.get("flags") or {}).get("skip"):
            result["skipped_irrelevant"] += 1
        else:
            result["enriched"] += 1

    if updated:
        rewrite_jsonl(updated)
        init_db()
        with session_scope() as s:
            load_documents(s, list(updated.values()))
    if result["failed"] and not (result["enriched"] or result["upgraded"]):
        result["status"] = "failed"
    result["pending_after"] = len(pending) - sum(1 for r in pending if r["uid"] in updated)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 翻译分类")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run_enrichment(args.limit, args.dry_run), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
