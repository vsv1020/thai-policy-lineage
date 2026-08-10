#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/vocab.json + data/policies/*.jsonl 生成前端用的派生数据。

    python3 tools/build_site.py

输出(全部是派生产物,不要手改 —— 手改会在下次 build 时被覆盖):
    data/site/policies.json   首页政策流 / 检索列表 / 风向 / 生效日历
    data/site/trends.json     按月聚合:各领域发文量、风向指数、机关活跃度
    data/site/lineage.json    议题脉络链(演进脉络页)

风向指数不再是人手填的数字,而是按 direction.sign 加权 confidence 聚合出来的 ——
这样「为了让页面有变化而编造指数波动」在结构上就不可能发生。
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "data" / "site"
BKK = timezone(timedelta(hours=7))

FEED_SIZE = 6          # 首页政策流条数
TREND_MONTHS = 12      # 趋势看板窗口
CALENDAR_DAYS = 90     # 生效日历窗口
# 少于这个月份数就不让前端用真实趋势 —— 三个点画不出「趋势」,只会误导
MIN_TREND_MONTHS = 6

CONF_WEIGHT = {"high": 1.0, "med": 0.7, "low": 0.4, "none": 0.2}
# 「现在」= 上次采集时间(data/policies/sources.json 的 last_run_at),不是 build 运行时刻。
# build 必须是输入的纯函数:同样的数据在任何时候重跑都得出同一份文件,CI 才能检查
# data/site/ 有没有被手改或漏跑。main() 会覆盖这个值。
NOW = datetime.now(BKK)
# 风向指数的收缩系数:score = Σ(sign·w) / (Σw + SHRINK)。样本少时自动往中性收,
# 避免「1 份文件 = 指数 ±1.0」这种统计上没有意义的极值。
SHRINK = 2.0


def load() -> tuple[dict, list[dict], list[dict], list[dict]]:
    vocab = json.loads((ROOT / "data" / "vocab.json").read_text(encoding="utf-8"))
    def jsonl(p: Path) -> list[dict]:
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    pol = ROOT / "data" / "policies"
    deadlines = jsonl(pol / "deadlines.jsonl") if (pol / "deadlines.jsonl").exists() else []
    return vocab, jsonl(pol / "documents.jsonl"), jsonl(pol / "issues.jsonl"), deadlines


def index(vocab: dict, key: str) -> dict[str, dict]:
    return {e["id"]: e for e in vocab[key]}


def display_date(d: dict) -> str:
    """展示用日期:刊登 → 决议 → 生效 → 意见截止,取第一个有值的。"""
    dates = d.get("dates") or {}
    for f in ("published_at", "resolved_at", "effective_from", "comment_deadline"):
        if dates.get(f):
            return dates[f]
    return ""


def effective_label(d: dict, statuses: dict) -> str:
    dates = d.get("dates") or {}
    if dates.get("effective_from"):
        today = NOW.date().isoformat()
        return ("已生效" if dates["effective_from"] <= today
                else f"生效 {dates['effective_from']}")
    if d["status_id"] == "pending_gazette":
        return "待刊公报后生效"
    if dates.get("comment_deadline"):
        return f"意见截止 {dates['comment_deadline']}"
    return statuses[d["status_id"]]["zh"]


def status_label(d: dict, statuses: dict) -> str:
    dates = d.get("dates") or {}
    today = NOW.date().isoformat()
    if d["status_id"] == "gazetted" and dates.get("effective_from", "") > today:
        return f"{dates['effective_from'][5:]} 起施行"
    return statuses[d["status_id"]]["zh"]


def to_view(d: dict, vocab_idx: dict) -> dict:
    """把规范化记录摊平成前端渲染需要的形状。所有 *_label 都在这里生成,
    数据文件里不再存展示字符串。"""
    domains, agencies, forms, statuses = (vocab_idx[k] for k in
                                          ("domains", "agencies", "legal_forms", "statuses"))
    primary_domain = domains[d["domain_ids"][0]]
    def org_name(a: str) -> str:
        ag = agencies[a]
        abbr = ag.get("abbr") or ""
        # 只在缩写是拉丁字母时并列显示;泰文缩写(ครม.、กกพ.)对中文读者无信息量
        return f"{ag['zh']} ({abbr})" if abbr.replace("-", "").isascii() and abbr.isascii() and abbr.replace("-", "").isalpha() else ag["zh"]
    org = " · ".join(org_name(a) for a in d["agency_ids"])
    form = forms[d["legal_form_id"]]
    legal_form = f"{form['zh']} · {form['abbr']} 层级"
    official = next((s["url"] for s in d.get("sources") or []
                     if s.get("role") == "official" and s.get("url")), "")
    prov = d.get("provenance") or {}
    return {
        "uid": d["uid"],
        "issue_id": d.get("issue_id"),
        "date": display_date(d),
        "domain": primary_domain["chip"],
        "domain_label": primary_domain["zh"],
        "direction": d["direction"]["value"],
        "title_zh": d["titles"]["zh"],
        "title_th": d["titles"].get("th", ""),
        "summary_zh": d["summary_zh"],
        "org": org,
        "doc_no": d.get("doc_no") or "",
        "doc_no_label": "公报" if d.get("gazette") else "文号",
        "legal_form": legal_form,
        "stability": form["stability"],
        "effective_label": effective_label(d, statuses),
        "status": {"in_force": "active", "gazetted": "soon"}.get(d["status_id"], "draft"),
        "status_label": status_label(d, statuses),
        "source_url": official,
        "verified": bool(prov.get("verified")),
        "detail_ready": bool((d.get("flags") or {}).get("has_detail_page")),
        "provenance": "demo" if prov.get("pipeline") == "demo" else prov.get("pipeline", "manual"),
    }


def months_back(n: int) -> list[str]:
    y, m, out = NOW.year, NOW.month, []
    for _ in range(n):
        out.append(f"{y % 100:02d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def build_trends(docs: list[dict], vocab_idx: dict) -> dict:
    """按月 × 领域聚合发文量与风向指数;按月 × 机关聚合活跃度。"""
    months = months_back(TREND_MONTHS)
    mset = set(months)
    domains, agencies = vocab_idx["domains"], vocab_idx["agencies"]

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    wind_num: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wind_den: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    org: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    covered: set[str] = set()

    sign = {e["id"]: e["sign"] for e in vocab_idx["directions"].values()}
    for d in docs:
        date = display_date(d)
        if len(date) < 7:
            continue
        mk = f"{date[2:4]}-{date[5:7]}"
        if mk not in mset:
            continue
        covered.add(mk)
        w = CONF_WEIGHT.get(d["direction"].get("confidence", "none"), 0.2)
        for did in d["domain_ids"]:
            counts[did][mk] += 1
            wind_num[did][mk] += sign[d["direction"]["value"]] * w
            wind_den[did][mk] += w
        for aid in d["agency_ids"]:
            org[aid][mk] += 1

    def series(store, keys):
        return [{"id": k, "label": keys[k]["zh"], "data": [store[k].get(m, 0) for m in months]}
                for k in store if any(store[k].get(m) for m in months)]

    wind = []
    for did in wind_num:
        pts = []
        for m in months:
            den = wind_den[did].get(m, 0)
            pts.append(round(wind_num[did][m] / (den + SHRINK), 2) if den else None)
        if any(p is not None for p in pts):
            wind.append({"id": did, "label": domains[did]["zh"], "data": pts})

    return {
        "months": months,
        "months_covered": len(covered),
        "usable": len(covered) >= MIN_TREND_MONTHS,
        "min_months_required": MIN_TREND_MONTHS,
        "volume_by_domain": series(counts, domains),
        "wind_by_domain": wind,
        "activity_by_agency": series(org, agencies),
    }


def build_wind_now(docs: list[dict], vocab_idx: dict) -> list[dict]:
    """首页「本月政策风向」:近 90 天按领域聚合,加权平均。"""
    cutoff = (NOW - timedelta(days=90)).date().isoformat()
    num, den, cnt = defaultdict(float), defaultdict(float), defaultdict(int)
    sign = {e["id"]: e["sign"] for e in vocab_idx["directions"].values()}
    for d in docs:
        if display_date(d) < cutoff:
            continue
        w = CONF_WEIGHT.get(d["direction"].get("confidence", "none"), 0.2)
        for did in d["domain_ids"]:
            num[did] += sign[d["direction"]["value"]] * w
            den[did] += w
            cnt[did] += 1
    out = []
    for did in sorted(den, key=lambda k: -cnt[k]):
        score = round(num[did] / (den[did] + SHRINK), 2)
        out.append({
            "domain": vocab_idx["domains"][did]["chip"],
            "label": vocab_idx["domains"][did]["zh"],
            "direction": "loose" if score > 0.15 else ("tight" if score < -0.15 else "neutral"),
            "score": score,
            "n": cnt[did],
        })
    return out


def next_occurrence(rec: dict, today) -> str | None:
    """把周期性法定截止日展开成下一个具体日期。"""
    if rec.get("type") == "once":
        return rec.get("date")
    if rec.get("type") == "yearly":
        for year in (today.year, today.year + 1):
            try:
                cand = today.replace(year=year, month=rec["month"], day=rec["day"])
            except ValueError:
                continue
            if cand >= today:
                return cand.isoformat()
    return None


def build_calendar(docs: list[dict], deadlines: list[dict], vocab_idx: dict) -> list[dict]:
    """生效日历 = 文件的生效日/意见截止日 + 周期性法定截止日,窗口内合并排序。"""
    today = NOW.date()
    horizon = (today + timedelta(days=CALENDAR_DAYS)).isoformat()
    today_s = today.isoformat()
    items = []
    for d in docs:
        dates = d.get("dates") or {}
        for field, verb in (("effective_from", "生效"), ("comment_deadline", "意见截止")):
            val = dates.get(field)
            if val and today_s <= val <= horizon:
                items.append({"date": val, "text": f"{d['titles']['zh'][:34]} · {verb}",
                              "uid": d["uid"], "kind": "document"})
    for dl in deadlines:
        val = next_occurrence(dl.get("recurrence") or {}, today)
        if val and today_s <= val <= horizon:
            items.append({"date": val, "text": dl["title_zh"], "uid": None, "kind": "deadline"})
    return sorted(items, key=lambda x: x["date"])


def build_lineage(issues: list[dict], docs: list[dict], vocab_idx: dict) -> dict:
    by_uid = {d["uid"]: d for d in docs}
    out = []
    for it in issues:
        stages = []
        for st in it.get("stages") or []:
            doc = by_uid.get(st.get("uid")) if st.get("uid") else None
            stages.append({
                "stage": st["stage"],
                "title": doc["titles"]["zh"] if doc else st.get("label", ""),
                "uid": st.get("uid"),
                "milestone": bool(st.get("milestone")),
                "note": st.get("note", ""),
                "meta": (f"{vocab_idx['legal_forms'][doc['legal_form_id']]['abbr']} 层级"
                         + (f" · {doc['doc_no']}" if doc.get("doc_no") else "")) if doc else "",
            })
        out.append({"issue_id": it["issue_id"], "title_zh": it["title_zh"],
                    "summary_zh": it.get("summary_zh", ""), "watch": it.get("watch", ""),
                    "domains": [vocab_idx["domains"][x]["zh"] for x in it["domain_ids"]],
                    "stages": stages})
    return {"issues": out}


def run_state() -> tuple[str | None, list[dict]]:
    """采集运行状态由 data/policies/sources.json 记录(采集流程写入),build 只搬运。

    updated_at 取 last_run_at 而不是「现在」—— build 必须是纯函数,否则同样的输入
    每次生成的文件都不同,CI 就无法检查 data/site/ 是否与源数据一致。
    """
    p = ROOT / "data" / "policies" / "sources.json"
    if not p.exists():
        return None, []
    obj = json.loads(p.read_text(encoding="utf-8"))
    return obj.get("last_run_at"), obj.get("sources", [])


def main() -> int:
    global NOW
    if subprocess.run([sys.executable, str(ROOT / "tools" / "validate.py"), "--quiet"]).returncode:
        print("校验未通过,已中止 build —— 先修数据再生成。", file=sys.stderr)
        return 1

    last_run, sources = run_state()
    if last_run:
        NOW = datetime.fromisoformat(last_run)   # 把整个 build 钉在「上次采集时刻」

    vocab, docs, issues, deadlines = load()
    vocab_idx = {k: index(vocab, k) for k in
                 ("domains", "agencies", "legal_forms", "statuses", "directions", "parties")}

    views = sorted((to_view(d, vocab_idx) for d in docs),
                   key=lambda v: v["date"], reverse=True)
    for i, v in enumerate(views):
        v["featured"] = i < FEED_SIZE       # 派生,不再手工维护

    research = sum(1 for v in views if v["provenance"] == "research")
    payload = {
        "_generated": "由 tools/build_site.py 生成,请勿手改;改 data/policies/*.jsonl 后重跑",
        "schema_version": 2,
        "updated_at": last_run or NOW.replace(microsecond=0).isoformat(),
        "sources": sources,
        "stats": {"total": len(views), "research": research,
                  "demo": sum(1 for v in views if v["provenance"] == "demo")},
        "wind": build_wind_now(docs, vocab_idx),
        "calendar": build_calendar(docs, deadlines, vocab_idx),
        "policies": views,
    }

    SITE.mkdir(parents=True, exist_ok=True)
    def dump(name: str, obj) -> None:
        (SITE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")
        print(f"  → data/site/{name}")

    print(f"build: {len(docs)} 份文件 / {len(issues)} 个议题 / {len(deadlines)} 条周期截止日")
    dump("policies.json", payload)
    trends = build_trends(docs, vocab_idx)
    dump("trends.json", trends)
    dump("lineage.json", build_lineage(issues, docs, vocab_idx))
    if not trends["usable"]:
        print(f"  提示:仅 {trends['months_covered']} 个月有数据(需 ≥{MIN_TREND_MONTHS}),"
              "趋势看板继续用演示数据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
