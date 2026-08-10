# -*- coding: utf-8 -*-
"""抓取内阁决议(มติคณะรัฐมนตรี)年度数据 → 结构化 CSV。

数据源:data.go.th 数据集 ``dataset_02_03``(内阁秘书处发布的决议逐年 JSON;
决议库 resolution.soc.go.th 收录约 10.9 万条历史决议,是政策的"上游"信号:
签证放宽、税收减免、外资措施通常先以内阁决议出现,数周至数月后才见公报)。

用法:
    python fetch_cabinet.py --limit 2        # 下载最近 2 个年度文件并规范化
    python fetch_cabinet.py --list           # 只列出可用资源

输出:
    data/raw/cabinet/<年度>.json
    data/processed/cabinet_index.csv         # date / title / agency / url
"""
from __future__ import annotations

import argparse
import csv
import json

from common import PROCESSED_DIR, RAW_DIR, ckan_resources, download_resource
from fetch_gazette import iter_records, normalize_date

DATASET_ID = "dataset_02_03"

KEY_ALIASES = {
    "title": ["title", "เรื่อง", "ชื่อเรื่อง", "subject", "name"],
    "date": ["date", "วันที่มีมติ", "วันที่", "resolution_date", "meeting_date"],
    "agency": ["agency", "หน่วยงานเจ้าของเรื่อง", "หน่วยงาน", "owner", "ministry"],
    "url": ["url", "link", "detail_url", "ไฟล์"],
}


def pick(record: dict, field: str):
    for key in KEY_ALIASES[field]:
        for k, v in record.items():
            if k.strip().lower() == key.lower() and v not in (None, ""):
                return v
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="内阁决议年度数据抓取")
    ap.add_argument("--limit", type=int, default=2, help="下载最近 N 个年度资源(默认 2)")
    ap.add_argument("--list", action="store_true", help="只列出资源,不下载")
    args = ap.parse_args()

    resources = ckan_resources(DATASET_ID)
    json_res = [r for r in resources if (r.get("format") or "").lower() == "json"] or resources
    json_res.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)

    print(f"数据集 {DATASET_ID}: 共 {len(json_res)} 个资源")
    if args.list:
        for r in json_res:
            print(f"  - {r.get('name')}  [{r.get('format')}]  {r.get('last_modified')}")
        return

    raw_dir = RAW_DIR / "cabinet"
    rows: list[dict] = []
    for res in json_res[: args.limit]:
        path = download_resource(res, raw_dir)
        print(f"已下载: {path.name} ({path.stat().st_size / 1024:.0f} KB)")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  ! 解析失败,保留原始文件待人工检查: {exc}")
            continue
        for rec in iter_records(payload):
            rows.append(
                {
                    "date": normalize_date(pick(rec, "date")),
                    "title": str(pick(rec, "title")).strip(),
                    "agency": pick(rec, "agency"),
                    "url": pick(rec, "url"),
                    "source_file": path.name,
                }
            )

    if rows:
        out = PROCESSED_DIR / "cabinet_index.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"规范化完成: {out}({len(rows)} 条)")
    else:
        print("未解析出记录 —— 请检查 data/raw/cabinet/ 下的原始文件并补充 KEY_ALIASES。")


if __name__ == "__main__":
    main()
