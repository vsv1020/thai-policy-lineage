# -*- coding: utf-8 -*-
"""共享工具:data.go.th (CKAN) 数据集发现与下载、佛历转换、礼貌抓取。

泰国开放数据平台 data.go.th 基于 CKAN,标准 API:
  /api/3/action/package_show?id=<dataset_id>  → 数据集元数据与资源(resource)列表

注意:
- 泰国政府站点对部分海外 IP / 非浏览器 UA 有 WAF 拦截,建议在泰国网络环境运行,
  或配置 HTTPS_PROXY 指向泰国出口;脚本对失败做了显式提示。
- 礼貌抓取:全局限速(默认 ≥1s/请求)、可识别 UA、超时与重试。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "https://data.go.th"
UA = (
    "ThaiPolicyLineage/0.1 (+https://github.com/vsv1020/thai-policy-lineage; "
    "research prototype; contact: via GitHub issues)"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

_last_request_ts = 0.0
MIN_INTERVAL = 1.0  # 秒/请求,礼貌限速


class FetchError(RuntimeError):
    pass


def _throttle() -> None:
    global _last_request_ts
    wait = MIN_INTERVAL - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def http_get(url: str, *, retries: int = 3, timeout: int = 30) -> requests.Response:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        _throttle()
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last_err = FetchError(f"HTTP {resp.status_code} for {url}")
        except requests.RequestException as exc:  # 网络层错误
            last_err = exc
        time.sleep(2 * attempt)
    raise FetchError(
        f"请求失败: {url}\n  原因: {last_err}\n"
        "  提示: 泰国政府数据源可能屏蔽海外 IP 或非浏览器 UA,"
        "建议在泰国网络环境运行,或设置 HTTPS_PROXY 后重试。"
    )


def ckan_resources(dataset_id: str) -> list[dict]:
    """返回数据集的 resource 列表(含 name / url / format / last_modified)。"""
    url = f"{BASE}/api/3/action/package_show?id={dataset_id}"
    data = http_get(url).json()
    if not data.get("success"):
        raise FetchError(f"CKAN package_show 失败: {dataset_id}: {data}")
    return data["result"].get("resources", [])


def download_resource(res: dict, dest_dir: Path) -> Path:
    """下载单个 resource 到 dest_dir,文件名取自 resource name/url。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = res["url"]
    name = (res.get("name") or url.rsplit("/", 1)[-1]).strip().replace("/", "_")
    if not name.lower().endswith((".json", ".csv", ".xlsx", ".xls")):
        fmt = (res.get("format") or "json").lower()
        name = f"{name}.{fmt}"
    dest = dest_dir / name
    resp = http_get(url)
    dest.write_bytes(resp.content)
    return dest


def be_to_ce(year: int) -> int:
    """佛历(พ.ศ.)→ 公历(ค.ศ.):2569 → 2026。已是公历则原样返回。"""
    return year - 543 if year > 2400 else year


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
