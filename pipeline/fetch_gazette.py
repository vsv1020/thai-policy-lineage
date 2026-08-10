# -*- coding: utf-8 -*-
"""抓取皇家公报(ราชกิจจานุเบกษา)官方月度索引 → 结构化 CSV。

数据源:data.go.th 数据集 ``dataset_02_04``(内阁秘书处发布的公报月度 JSON 索引,
含标题/卷/期/类别/日期/PDF 链接)。这是官方开放数据接口,无需爬公报主站。

用法:
    python fetch_gazette.py --limit 3        # 下载最近 3 个月度文件并规范化
    python fetch_gazette.py --list           # 只列出可用资源,不下载

输出:
    data/raw/gazette/<月度>.json             # 原始文件永久归档
    data/processed/gazette_index.csv         # 规范化索引(date/series/title/pdf_url/...)

后续扩展(见 pipeline/README.md):下载 PDF → PyMuPDF 抽文本 → LLM 翻译/分类。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from common import PROCESSED_DIR, RAW_DIR, be_to_ce, ckan_resources, download_resource

DATASET_ID = "dataset_02_04"

# 公报 JSON 的键名可能是泰文或英文,做宽松映射;未识别字段原样保留在 raw 文件里。
KEY_ALIASES = {
    "title": ["title", "ชื่อเรื่อง", "เรื่อง", "name", "subject"],
    "date": ["date", "วันที่", "วันที่ประกาศ", "announce_date", "publish_date"],
    "volume": ["volume", "เล่ม", "book"],
    "part": ["part", "ตอน", "ตอนที่"],
    "series": ["series", "ประเภท", "type", "category"],
    "pdf_url": ["pdf_url", "url", "link", "file", "ไฟล์"],
}


def pick(record: dict, field: str):
    for key in KEY_ALIASES[field]:
        for k, v in record.items():
            if k.strip().lower() == key.lower() and v not in (None, ""):
                return v
    return ""


def normalize_date(value: str) -> str:
    """把 '25/07/2569' 或 '2569-07-25' 等佛历日期规范成 ISO 公历;失败原样返回。"""
    value = str(value).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        return f"{be_to_ce(y):04d}-{mo:02d}-{d:02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{be_to_ce(y):04d}-{mo:02d}-{d:02d}"
    return value


def iter_records(payload) -> list[dict]:
    """月度 JSON 可能是数组或 {data:[...]} 包装,统一展开为记录列表。"""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "records", "result", "items"):
            if isinstance(payload.get(key), list):
                return [r for r in payload[key] if isinstance(r, dict)]
        return [payload]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="皇家公报月度索引抓取")
    ap.add_argument("--limit", type=int, default=3, help="下载最近 N 个月度资源(默认 3)")
    ap.add_argument("--list", action="store_true", help="只列出资源,不下载")
    args = ap.parse_args()

    resources = ckan_resources(DATASET_ID)
    # JSON 资源優先,按最后修改时间倒序(最近月份在前)
    json_res = [r for r in resources if (r.get("format") or "").lower() == "json"] or resources
    json_res.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)

    print(f"数据集 {DATASET_ID}: 共 {len(json_res)} 个资源")
    if args.list:
        for r in json_res:
            print(f"  - {r.get('name')}  [{r.get('format')}]  {r.get('last_modified')}")
        return

    raw_dir = RAW_DIR / "gazette"
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
                    "series": pick(rec, "series"),
                    "volume": pick(rec, "volume"),
                    "part": pick(rec, "part"),
                    "title": str(pick(rec, "title")).strip(),
                    "pdf_url": pick(rec, "pdf_url"),
                    "source_file": path.name,
                }
            )

    if rows:
        out = PROCESSED_DIR / "gazette_index.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"规范化完成: {out}({len(rows)} 条)")
    else:
        print("未解析出记录 —— 请检查 data/raw/gazette/ 下的原始文件结构并补充 KEY_ALIASES。")


if __name__ == "__main__":
    main()
