#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 data/policies/*.jsonl 对 data/vocab.json 的一致性。

只用标准库 —— 这个脚本会在无人值守的定时任务里跑,不能依赖 pip 装包。
除了结构校验,还做 JSON Schema 表达不了的语义校验:词表成员、关系目标存在、
关系对称性、日期顺序、生效状态与日期是否矛盾、以及三条编辑红线的机械扫描。

    python3 tools/validate.py            # 校验,有错返回码 1
    python3 tools/validate.py --quiet    # 只在出错时输出
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOCAB = ROOT / "data" / "vocab.json"
DOCS = ROOT / "data" / "policies" / "documents.jsonl"
ISSUES = ROOT / "data" / "policies" / "issues.jsonl"
CONFLICTS = ROOT / "data" / "policies" / "conflicts.jsonl"

UID_RE = re.compile(r"^TH-[A-Z0-9]+-[A-Z0-9]+(-[A-Z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATE_FIELDS = ("resolved_at", "published_at", "effective_from", "effective_to", "comment_deadline")
# 生效链的时间顺序:决议 → 刊登 → 生效 → 失效
DATE_ORDER = ("resolved_at", "published_at", "effective_from", "effective_to")

REQUIRED = ("uid", "titles", "summary_zh", "agency_ids", "domain_ids", "legal_form_id",
            "status_id", "direction", "dates", "relations", "provenance", "flags")

# 红线三:王室相关内容零加工 —— 命中即要求人工确认,不允许自动流程写入
ROYAL_TERMS = ("พระบรมราชโองการ", "สมเด็จพระ", "พระบาทสมเด็จ", "ราชวงศ์",
               "王室", "国王", "王后", "御准", "冒犯君主")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"[错误] {where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"[提醒] {where}: {msg}")


def read_jsonl(path: Path, rep: Report) -> list[dict]:
    out = []
    if not path.exists():
        rep.err(str(path.relative_to(ROOT)), "文件不存在")
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            rep.err(f"{path.name}:{i}", f"JSON 解析失败: {exc}")
            continue
        if not isinstance(rec, dict):
            rep.err(f"{path.name}:{i}", "每行必须是一个对象")
            continue
        rec["_line"] = i
        out.append(rec)
    return out


def ids(vocab: dict, key: str) -> set[str]:
    return {e["id"] for e in vocab[key]}


def check_doc(d: dict, v: dict, rep: Report, all_uids: set[str], issue_ids: set[str]) -> None:
    where = f"documents.jsonl:{d['_line']} {d.get('uid', '<无 uid>')}"

    for f in REQUIRED:
        if f not in d:
            rep.err(where, f"缺少必填字段 {f}")

    uid = d.get("uid", "")
    if not UID_RE.match(uid):
        rep.err(where, f"uid 不合规范(应形如 TH-RD-20260808-FOREIGN-INCOME): {uid!r}")

    # 受控词表
    for aid in d.get("agency_ids") or []:
        if aid not in ids(v, "agencies"):
            rep.err(where, f"未知 agency_id: {aid}")
    if not d.get("agency_ids"):
        rep.err(where, "agency_ids 不能为空 —— 没有发文机关的条目不得入库")
    for did in d.get("domain_ids") or []:
        if did not in ids(v, "domains"):
            rep.err(where, f"未知 domain_id: {did}")
    if not d.get("domain_ids"):
        rep.err(where, "domain_ids 不能为空")
    if d.get("legal_form_id") not in ids(v, "legal_forms"):
        rep.err(where, f"未知 legal_form_id: {d.get('legal_form_id')}")
    if d.get("status_id") not in ids(v, "statuses"):
        rep.err(where, f"未知 status_id: {d.get('status_id')}")

    direction = d.get("direction") or {}
    if direction.get("value") not in ids(v, "directions"):
        rep.err(where, f"未知 direction.value: {direction.get('value')}")
    if direction.get("confidence") not in ids(v, "confidence_levels"):
        rep.err(where, f"未知 direction.confidence: {direction.get('confidence')}")

    for ap in d.get("affected_parties") or []:
        if ap.get("party_id") not in ids(v, "parties"):
            rep.err(where, f"未知 party_id: {ap.get('party_id')}")
        if ap.get("stance") not in ids(v, "stances"):
            rep.err(where, f"未知 stance: {ap.get('stance')}")

    if d.get("issue_id") is not None and d["issue_id"] not in issue_ids:
        rep.err(where, f"issue_id 在 issues.jsonl 中不存在: {d['issue_id']}")

    # 维度分析用字段(维度一/二/七)
    for iid in d.get("instrument_ids") or []:
        if iid not in ids(v, "instruments"):
            rep.err(where, f"未知 instrument_id: {iid}")
    if not d.get("instrument_ids"):
        rep.warn(where, "没有 instrument_ids,维度一/二的工具结构矩阵会漏掉这一条")
    for gid in d.get("goal_ids") or []:
        if gid not in ids(v, "goals"):
            rep.err(where, f"未知 goal_id: {gid}")
    if not d.get("goal_ids"):
        rep.warn(where, "没有 goal_ids,维度二的工具×目标矩阵会漏掉这一条")
    stage = d.get("implementation_stage")
    if stage is not None and stage not in ids(v, "implementation_stages"):
        rep.err(where, f"未知 implementation_stage: {stage}")

    # 日期
    dates = d.get("dates") or {}
    for f in DATE_FIELDS:
        val = dates.get(f)
        if val is not None and not DATE_RE.match(str(val)):
            rep.err(where, f"dates.{f} 必须是 YYYY-MM-DD 或 null: {val!r}")
    for f in dates:
        if f not in DATE_FIELDS:
            rep.err(where, f"dates 里有未定义字段 {f}")
    seq = [(f, dates.get(f)) for f in DATE_ORDER if dates.get(f)]
    for (f1, v1), (f2, v2) in zip(seq, seq[1:]):
        # 生效日期可以早于刊登日(追溯生效),其余必须单调
        if f1 == "published_at" and f2 == "effective_from":
            continue
        if v1 > v2:
            rep.err(where, f"日期顺序矛盾: {f1}={v1} 晚于 {f2}={v2}")

    status = d.get("status_id")
    if status == "in_force" and not (dates.get("effective_from") or dates.get("published_at")):
        rep.err(where, "status=in_force 但既无 effective_from 也无 published_at")
    if status == "pending_gazette" and dates.get("published_at"):
        rep.err(where, "status=pending_gazette 但已有 published_at —— 应改为 gazetted 或 in_force")

    # 溯源
    prov = d.get("provenance") or {}
    if prov.get("pipeline") not in ("gazette_json", "cabinet_json", "research", "manual", "demo"):
        rep.err(where, f"未知 provenance.pipeline: {prov.get('pipeline')}")
    if prov.get("verified") is True and not prov.get("verified_at"):
        rep.err(where, "verified=true 必须同时填 verified_at")
    if prov.get("pipeline") == "research" and prov.get("verified") is True:
        rep.err(where, "自动采集的条目不得自称已人工复核(verified 必须为 false)")

    conf = d.get("confidence") or {}
    for k, val in conf.items():
        if val not in ids(v, "confidence_levels"):
            rep.err(where, f"未知 confidence.{k}: {val}")

    # 红线三:不虚构 —— 有文号就得说明可信度;链接必须是真 URL 或空
    if d.get("doc_no") and conf.get("doc_no") in (None, "none"):
        rep.err(where, "填了 doc_no 但 confidence.doc_no 为 none —— 要么给出可信度,要么清空文号")
    for s in d.get("sources") or []:
        url = s.get("url") or ""
        if url and not url.startswith("http"):
            rep.err(where, f"sources[].url 必须是 http(s) 链接或空字符串: {url!r}")
        if s.get("role") not in ("official", "secondary", "archive"):
            rep.err(where, f"未知 sources[].role: {s.get('role')}")

    # 红线一:王室相关
    blob = json.dumps(d, ensure_ascii=False)
    for t in ROYAL_TERMS:
        if t in blob:
            rep.err(where, f"命中王室相关词 {t!r} —— 自动流程不得加工王室内容,需人工处理")

    # 红线二:名单类不建人名索引(启发式:泰文人名前缀 / 中文姓名字段)
    if re.search(r"(นาย|นาง|นางสาว)\s*\S", blob):
        rep.warn(where, "文本中出现泰文人名前缀(นาย/นาง/นางสาว),确认没有写入自然人姓名")

    # 关系
    for rel in d.get("relations") or []:
        if rel.get("type") not in ids(v, "relation_types"):
            rep.err(where, f"未知 relation.type: {rel.get('type')}")
        if rel.get("uid") not in all_uids:
            rep.err(where, f"关系指向不存在的 uid: {rel.get('uid')}")
        if rel.get("uid") == uid:
            rep.err(where, "关系不能指向自身")


def check_relation_symmetry(docs: list[dict], v: dict, rep: Report) -> None:
    inverse = {e["id"]: e["inverse"] for e in v["relation_types"]}
    by_uid = {d["uid"]: d for d in docs if d.get("uid")}
    for d in docs:
        for rel in d.get("relations") or []:
            target = by_uid.get(rel.get("uid"))
            want = inverse.get(rel.get("type"))
            if not target or not want:
                continue
            have = any(r.get("type") == want and r.get("uid") == d["uid"]
                       for r in target.get("relations") or [])
            if not have:
                rep.warn(f"{d['uid']} → {target['uid']}",
                         f"关系 {rel['type']} 缺少反向 {want},脉络图会少一条边")


def check_issue(it: dict, v: dict, rep: Report, all_uids: set[str]) -> None:
    where = f"issues.jsonl:{it['_line']} {it.get('issue_id', '<无 id>')}"
    for f in ("issue_id", "title_zh", "domain_ids", "stages"):
        if f not in it:
            rep.err(where, f"缺少必填字段 {f}")
    for did in it.get("domain_ids") or []:
        if did not in ids(v, "domains"):
            rep.err(where, f"未知 domain_id: {did}")
    for st in it.get("stages") or []:
        if not st.get("stage"):
            rep.err(where, "stages[] 每项必须有 stage")
        uid = st.get("uid")
        if uid is not None and uid not in all_uids:
            rep.err(where, f"stages[].uid 指向不存在的文件: {uid}")
        if uid is None and not st.get("label"):
            rep.err(where, "stages[] 没有 uid 时必须给 label(否则前端无可显示内容)")


def check_conflict(c: dict, v: dict, rep: Report, all_uids: set[str]) -> None:
    where = f"conflicts.jsonl:{c['_line']} {c.get('id', '<无 id>')}"
    for f in ("id", "severity", "title_zh", "sides", "impact_zh"):
        if f not in c:
            rep.err(where, f"缺少必填字段 {f}")
    if c.get("severity") not in ids(v, "severities"):
        rep.err(where, f"未知 severity: {c.get('severity')}")
    for did in c.get("domain_ids") or []:
        if did not in ids(v, "domains"):
            rep.err(where, f"未知 domain_id: {did}")
    sides = c.get("sides") or []
    if len(sides) < 2:
        rep.err(where, "冲突必须有至少两方(sides ≥ 2),否则无从对照")
    for s in sides:
        if s.get("uid") is not None and s["uid"] not in all_uids:
            rep.err(where, f"sides[].uid 指向不存在的文件: {s['uid']}")
        if s.get("uid") is None and not s.get("label"):
            rep.err(where, "sides[] 没有 uid 时必须给 label")
        if not s.get("quote_zh"):
            rep.err(where, "sides[] 必须给 quote_zh —— 冲突要能看到双方口径")
    if c.get("confidence") not in ids(v, "confidence_levels"):
        rep.err(where, f"未知 confidence: {c.get('confidence')}")


def check_site_config(rep: Report) -> None:
    """config/ads.json 与 config/support.json 是手改的配置 —— 改错了页面会静默不显示,
    或者更糟:显示了不该显示的东西。在这里机械地挡住。"""
    from datetime import date as _date
    cfg_dir = ROOT / "config"
    ads_p, sup_p = cfg_dir / "ads.json", cfg_dir / "support.json"

    if ads_p.exists():
        try:
            ads = json.loads(ads_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rep.err("config/ads.json", f"JSON 解析失败: {exc}")
            ads = None
        if ads:
            allowed = set((ads.get("allowed_categories") or {}).keys())
            for bad in ("visa_agent", "nominee_service", "immigration_broker", "gambling"):
                if bad in allowed:
                    rep.err("config/ads.json", f"allowed_categories 不得包含 {bad} —— 中立性红线")
            for slot, conf in (ads.get("slots") or {}).items():
                for i, it in enumerate(conf.get("items") or []):
                    where = f"config/ads.json slots.{slot}.items[{i}]"
                    if it.get("category") not in allowed:
                        rep.warn(where, f"类别 {it.get('category')!r} 不在白名单,前端不会显示")
                    if not str(it.get("href", "")).startswith("https://"):
                        rep.err(where, "href 必须是 https:// 链接")
                    for k in ("start", "end"):
                        if it.get(k):
                            try:
                                _date.fromisoformat(it[k])
                            except ValueError:
                                rep.err(where, f"{k} 必须是 YYYY-MM-DD")
                    if not it.get("sponsor"):
                        rep.err(where, "必须写明 sponsor —— 读者有权知道是谁付的钱")
            client = (ads.get("adsense") or {}).get("client", "")
            if client and not re.match(r"^ca-pub-\d{10,20}$", client):
                rep.err("config/ads.json", f"adsense.client 格式应为 ca-pub-数字: {client!r}")

    if sup_p.exists():
        try:
            sup = json.loads(sup_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rep.err("config/support.json", f"JSON 解析失败: {exc}")
            return
        for i, ch in enumerate(sup.get("channels") or []):
            where = f"config/support.json channels[{i}]"
            t = ch.get("type")
            if t == "promptpay" and ch.get("id"):
                d = re.sub(r"\D", "", str(ch["id"]))
                if not (len(d) in (13, 15) or (len(d) == 10 and d.startswith("0"))):
                    rep.err(where, "PromptPay id 需为 10 位手机号、13 位税号或 15 位电子钱包号")
                if len(d) == 10:
                    rep.warn(where, "用手机号收款会把号码公开编码进二维码,扫码时还会显示收款人真实姓名")
            elif t == "image" and ch.get("src"):
                if not (ROOT / ch["src"]).is_file():
                    rep.err(where, f"图片不存在: {ch['src']}")
                if not ch["src"].startswith("assets/"):
                    rep.err(where, "图片必须放在 assets/ 下,其他目录不对外公开")
            elif t == "link" and ch.get("href") and not ch["href"].startswith("https://"):
                rep.err(where, "href 必须是 https:// 链接")
            elif t not in ("promptpay", "image", "link"):
                rep.err(where, f"未知渠道类型 {t!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="政策数据校验")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rep = Report()
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    docs = read_jsonl(DOCS, rep)
    issues = read_jsonl(ISSUES, rep)
    conflicts = read_jsonl(CONFLICTS, rep) if CONFLICTS.exists() else []

    uids = [d.get("uid") for d in docs if d.get("uid")]
    dup = {u for u in uids if uids.count(u) > 1}
    for u in sorted(dup):
        rep.err("documents.jsonl", f"uid 重复: {u}")

    iids = [i.get("issue_id") for i in issues if i.get("issue_id")]
    for i in sorted({x for x in iids if iids.count(x) > 1}):
        rep.err("issues.jsonl", f"issue_id 重复: {i}")

    all_uids, issue_ids = set(uids), set(iids)
    for d in docs:
        check_doc(d, vocab, rep, all_uids, issue_ids)
    for it in issues:
        check_issue(it, vocab, rep, all_uids)
    for c in conflicts:
        check_conflict(c, vocab, rep, all_uids)
    check_relation_symmetry(docs, vocab, rep)
    check_site_config(rep)

    for w in rep.warnings:
        if not args.quiet:
            print(w)
    for e in rep.errors:
        print(e, file=sys.stderr)

    if rep.errors:
        print(f"\n校验失败:{len(rep.errors)} 个错误、{len(rep.warnings)} 个提醒", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"校验通过:{len(docs)} 份文件、{len(issues)} 个议题、{len(conflicts)} 条冲突、{len(rep.warnings)} 个提醒")
    return 0


if __name__ == "__main__":
    sys.exit(main())
