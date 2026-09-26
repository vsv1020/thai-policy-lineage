# -*- coding: utf-8 -*-
"""DB → data/site/*.json,给 GitHub Pages 静态降级用。

    python3 -m app.export

前端优先打 API;打不通(后端没部署、跨域、离线)就读这些文件。所以这里导出的
形状必须和 API 返回的一模一样 —— 两边都由 app.analytics 生成,不存在第二套逻辑。
"""
from __future__ import annotations

import json

from . import analytics as A
from .config import SITE_DIR
from .db import session_scope

GENERATED_NOTE = ("由 backend/app/export.py 从数据库导出,请勿手改;"
                  "改 data/policies/*.jsonl → python3 -m app.ingest → python3 -m app.export")


def export_all() -> dict[str, int]:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    with session_scope() as s:
        payloads = {
            "policies.json": A.overview(s),
            "trends.json": A.trends(s),
            "lineage.json": A.lineage(s),
            "dimensions.json": A.dimensions(s),
            "ops.json": A.ops(s),
        }
        from .seo import build as build_seo
        seo = build_seo(s)
    for name, payload in payloads.items():
        if isinstance(payload, dict):
            payload = {"_generated": GENERATED_NOTE, **payload}
        path = SITE_DIR / name
        text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        path.write_text(text, encoding="utf-8")
        written[name] = len(text)
    written["_seo"] = seo
    return written


def main() -> None:
    out = export_all()
    seo = out.pop("_seo")
    for name, size in out.items():
        print(f"  → data/site/{name} ({size / 1024:.1f} KB)")
    print(f"  → p/*.html {seo['pages']} 页 · sitemap.xml {seo['sitemap_urls']} 条 · robots.txt")


if __name__ == "__main__":
    main()
