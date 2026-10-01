# -*- coding: utf-8 -*-
"""新收录政策推送到 Telegram 频道(可选)。

    python -m app.notify              # 推送本轮新上线的政策
    python -m app.notify --dry-run    # 只列出将要推送的条目,不发送、不记状态

需要两个配置,缺一个就整步跳过(日志一行,不报错):
- TELEGRAM_BOT_TOKEN:@BotFather 创建机器人得到的令牌(GitHub Secret);
- TELEGRAM_CHANNEL:频道用户名,如 @thaipolicy(GitHub Variable)。机器人要先被加为频道管理员。

已推送过的 uid 记在 data/notify/telegram.json(随采集结果提交),不会重复推送。
第一次运行时只把现有条目全部记为「已推送」、不发送 —— 否则会一口气推几百条刷屏。
每轮最多推 MAX_PER_RUN 条,剩下的留到下一轮。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import httpx

from .config import DATA_DIR, POLICIES_DIR, settings
from .ingest import presentable, read_jsonl

log = logging.getLogger("policy.notify")
STATE = DATA_DIR / "notify" / "telegram.json"
MAX_PER_RUN = 30
INTERVAL_S = 3.2          # Telegram 对同一频道约 20 条/分钟


def _vocab_domains() -> dict[str, str]:
    v = json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8"))
    return {d["id"]: d["zh"] for d in v["domains"]}


def candidates() -> list[dict]:
    """当前可在前台呈现的条目,按刊登日倒序。"""
    rows = [r for r in read_jsonl(POLICIES_DIR / "documents.jsonl") if presentable(r)]
    def day(r):
        d = r.get("dates") or {}
        return d.get("published_at") or d.get("resolved_at") or ""
    return sorted(rows, key=lambda r: (day(r), r["uid"]), reverse=True)


def message(r: dict, domains: dict[str, str]) -> str:
    from html import escape as e
    d = r.get("dates") or {}
    when = d.get("published_at") or d.get("resolved_at") or ""
    dom = domains.get((r.get("domain_ids") or [""])[0], "")
    official = next((s.get("url") for s in r.get("sources") or [] if s.get("role") == "official" and s.get("url")), "")
    summary = (r.get("summary_zh") or "").strip()
    if len(summary) > 220:
        summary = summary[:220] + "…"
    points = "".join(f"\n• {e(k)}" for k in (r.get("key_points_zh") or [])[:3])
    page = f"{settings.site_url}/p/{r['uid'].lower()}.html"
    return (f"<b>{e(r['titles']['zh'])}</b>\n"
            + " · ".join(x for x in (dom, f"刊登 {when}" if when else "", r.get("doc_no") or "") if x)
            + f"\n\n{e(summary)}{points}\n\n"
            f'<a href="{e(page)}">中文摘要</a> · <a href="{e(official)}">泰文原文</a>\n'
            "非官方翻译,以泰文原文为准")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["sent"] = sorted(set(st.get("sent", [])))
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def run(dry_run: bool = False, client: httpx.Client | None = None, sleep=time.sleep) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.getenv("TELEGRAM_CHANNEL", "").strip()
    rows = candidates()
    st = load_state()
    sent = set(st.get("sent", []))
    if not st:                                   # 第一次:只记账,不发送
        if not dry_run and token and channel:
            save_state({"sent": [r["uid"] for r in rows]})
        return {"status": "bootstrap", "marked": len(rows), "sent": 0}
    todo = [r for r in rows if r["uid"] not in sent][:MAX_PER_RUN]
    if dry_run:
        domains = _vocab_domains()
        return {"status": "dry_run", "pending": len(todo), "preview": [message(r, domains) for r in todo[:3]]}
    if not (token and channel):
        log.info("没配置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL,跳过推送(%d 条待推送)", len(todo))
        return {"status": "not_configured", "pending": len(todo), "sent": 0}
    domains = _vocab_domains()
    client = client or httpx.Client(timeout=20)
    n, errors = 0, []
    for r in todo:
        resp = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": channel, "text": message(r, domains), "parse_mode": "HTML",
            "disable_web_page_preview": True})
        if resp.status_code == 200:
            sent.add(r["uid"]); n += 1
        else:
            # 令牌错、机器人不是频道管理员等:后面也会一样失败,停下,下轮重试
            errors.append(f"HTTP {resp.status_code} {resp.text[:160]}")
            break
        sleep(INTERVAL_S)
    save_state({"sent": list(sent)})
    return {"status": "error" if errors else "ok", "sent": n, "pending": len(todo) - n, "errors": errors}


def main() -> None:
    ap = argparse.ArgumentParser(description="新收录政策推送到 Telegram 频道")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(args.dry_run), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
