# -*- coding: utf-8 -*-
"""部门官网来源:税务厅「新法」与 BOI 公告。

为什么需要:政府开放数据平台上的公报、决议数据集自 2026-04 起没有更新,公报官网的网页又有
人机验证(不绕过)。税务厅和 BOI 在自己官网发布新规,这两处没有人机验证、robots.txt 允许抓取,
而且都附官方 PDF 原文(*.go.th),符合「只放有官方原文的内容」的规则。

- 税务厅(rd.go.th):官方 RSS(/rss.xml,最近约 30 条)里链接到 /fileadmin/user_upload/kormor/newlaw/*.pdf
  的条目就是新发布的法规;其余是新闻、活动、申报期提醒,不收。「รวมกฎหมายภาษี」页(/284.html)
  列出最新几部新法,用于补 RSS 里没有的条目 —— 但只有 RSS 给出日期,没有日期的不收(红线三)。
- BOI(boi.go.th):公告列表页把全部公告以 JSON 内嵌在 <div id="dataMasterLaws"> 里,
  每条有编号、标题、日期、PDF、法律依据/废止说明。

两站都直连,不走泰国出口(实测代理连不上这两个域名,而直连正常)。
日期是部门官网的发布日期,不是公报刊登日;记录的 note 里写明来源。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin

import httpx

RD_BASE = "https://www.rd.go.th/"
RD_RSS = RD_BASE + "rss.xml"
RD_LAW_INDEX = RD_BASE + "284.html"
RD_NEWLAW = re.compile(r"/fileadmin/user_upload/kormor/newlaw/[^\"'<>\s]+\.pdf$", re.I)

BOI_BASE = "https://www.boi.go.th/"
BOI_LIST = BOI_BASE + "index.php?page=boi_announcements"

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _clean(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def title_key(title: str) -> str:
    """跨来源比对同一份文件:去空白、泰文数字转阿拉伯数字。"""
    return re.sub(r"\s+", "", (title or "").translate(THAI_DIGITS))


def legal_form_of(title: str) -> str:
    t = title.strip()
    for prefix, form in (("พระราชบัญญัติ", "act"), ("พระราชกำหนด", "emergency"), ("พระราชกฤษฎีกา", "decree"),
                         ("กฎกระทรวง", "ministerial"), ("ระเบียบ", "rabiap"), ("คำชี้แจง", "guidance")):
        if t.startswith(prefix):
            return form
    return "prakat"


def _record(uid: str, title: str, published: str, pdf: str, pipeline: str, run_at: str, *,
            agency: str, domain: str, legal_form: str, status: str, doc_no: str = "",
            note: str = "", source_note: str = "") -> dict:
    return {
        "uid": uid,
        "issue_id": None,
        "titles": {"zh": "", "th": title, "en": ""},
        "summary_zh": "",
        "instrument_ids": [],
        "goal_ids": [],
        "implementation_stage": None,
        "subjects": [],
        "agency_ids": [agency],
        "domain_ids": [domain],
        "legal_form_id": legal_form,
        "status_id": status,
        "direction": {"value": "neutral", "confidence": "none", "method": "none"},
        "doc_no": doc_no[:64],
        "gazette": None,
        "dates": {"resolved_at": None, "published_at": published, "effective_from": None,
                  "effective_to": None, "comment_deadline": None},
        "affected_parties": [],
        "relations": [],
        "sources": [{"role": "official", "url": pdf, "note": source_note}],
        "provenance": {"pipeline": pipeline, "run_at": run_at, "verified": False, "verified_at": None},
        # 日期、文号都取自部门官网自己的列表(官方数据);日期含义是官网发布日,note 里写明
        "confidence": {"dates": "high", "doc_no": "high" if doc_no else "none"},
        "flags": {"has_detail_page": False},
        "note": note,
    }


# ─────────────────────── 税务厅 ───────────────────────

def parse_rd_rss(xml: str) -> list[dict]:
    """RSS → [{title, url, date}],只留链接到「新法」PDF 的条目。"""
    out = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(name: str) -> str:
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", item, re.S)
            return _clean(m.group(1)) if m else ""
        url = urljoin(RD_BASE, tag("link"))
        if not RD_NEWLAW.search(url):
            continue
        try:
            day = parsedate_to_datetime(tag("pubDate")).date().isoformat()
        except (TypeError, ValueError):
            day = ""
        out.append({"title": tag("title"), "url": url, "date": day})
    return out


def parse_rd_index(html: str) -> list[dict]:
    """「รวมกฎหมายภาษี」页上的新法链接 → [{title, url}](没有日期)。"""
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S):
        url = urljoin(RD_BASE, href.strip())
        if RD_NEWLAW.search(url):
            out.append({"title": _clean(text), "url": url})
    return out


def normalize_rd(item: dict, run_at: str) -> tuple[dict | None, str]:
    from .collect import passes_red_lines
    title = item.get("title", "").strip()
    if not title:
        return None, "无标题"
    ok, why = passes_red_lines(title)
    if not ok:
        return None, why
    if not item.get("date"):
        return None, "无可解析日期"
    stem = re.sub(r"[^A-Za-z0-9]+", "", item["url"].rsplit("/", 1)[-1].rsplit(".", 1)[0]).upper()[:24]
    agency = "mof" if title.startswith("ประกาศกระทรวงการคลัง") else "rd"
    return _record(
        f"TH-RD-{item['date'].replace('-', '')}-{stem}", title, item["date"], item["url"], "rd_web", run_at,
        agency=agency, domain="tax", legal_form=legal_form_of(title),
        # 税务厅「新法」栏目只发布已生效施行的法规(皇家法令、部令须先刊公报)
        status="gazetted",
        note="自税务厅官网「新法」栏目自动入库;日期为官网发布日;中文标题与摘要待翻译环节补全",
        source_note="税务厅官网原文 PDF"), ""


def fetch_rd(client: httpx.Client) -> tuple[list[dict], str]:
    """返回 (条目, 说明)。RSS 是主来源;索引页只用来发现 RSS 里没有的链接(无日期的不收,计入说明)。"""
    rss = parse_rd_rss(client.get(RD_RSS).raise_for_status().text)
    seen = {x["url"] for x in rss}
    undated = []
    try:
        for x in parse_rd_index(client.get(RD_LAW_INDEX).raise_for_status().text):
            if x["url"] not in seen:
                seen.add(x["url"])
                undated.append({**x, "date": ""})
    except httpx.HTTPError:
        pass                      # 索引页只是补充,失败不影响 RSS
    return rss + undated, f"RSS 新法 {len(rss)} 条,索引页另有 {len(undated)} 条无日期"


# ─────────────────────── BOI ───────────────────────

def parse_boi(html: str) -> list[dict]:
    """列表页内嵌的公告 JSON(一串对象,个别字段含控制字符,宽松解析)。"""
    m = re.search(r'id="dataMasterLaws"[^>]*>(.*?)</div>', html, re.S)
    raw = m.group(1) if m else ""
    dec, out, i = json.JSONDecoder(strict=False), [], 0
    while (j := raw.find("{", i)) >= 0:
        try:
            obj, i = dec.raw_decode(raw, j)
        except ValueError:
            i = j + 1
            continue
        if isinstance(obj, dict) and obj.get("topic_id"):
            out.append(obj)
    return out


_BOI_REPEALED = ("ยกเลิกแล้ว", "ถูกยกเลิก", "repealed", "cancel")
# BOI 公告的发文方:编号只有加上发文方才唯一(「ที่ 9/2569」在 กกท. 和 สกท. 各有一份)
_BOI_ISSUERS = (("สำนักงานคณะกรรมการส่งเสริมการลงทุน", "สกท."), ("คณะกรรมการส่งเสริมการลงทุน", "กกท."),
                ("สกท", "สกท."), ("กกท", "กกท."), ("คสดช", "คสดช."))
_NUM = r"([ก-ฮ]?\.?\s?\d+/\d{4})"


def boi_key(issuer_text: str, num: str) -> str:
    """「สกท.」+「ป.11/2569」→ 统一键,用于在废止说明里找到被废止的那一份。"""
    abbr = next((a for full, a in _BOI_ISSUERS if full in issuer_text), "")
    num = re.sub(r"\s+", "", num)
    return f"{abbr} {num}" if abbr else ""


def boi_doc_key(name: str) -> str:
    m = re.search(r"^(.*?)ที่\s*" + _NUM, name.translate(THAI_DIGITS))
    return boi_key(m.group(1), m.group(2)) if m else ""


def boi_repealed_keys(basis: str) -> list[str]:
    """「ยกเลิกประกาศสำนักงานคณะกรรมการส่งเสริมการลงทุน ที่ ป.1/2569 ลงวันที่ …」→ ["สกท. ป.1/2569"]"""
    out = []
    for m in re.finditer(r"ยกเลิก(.{0,80}?)ที่\s*" + _NUM, basis.translate(THAI_DIGITS)):
        key = boi_key(m.group(1), m.group(2))
        if key:
            out.append(key)
    return out


def link_boi(records: list[dict]) -> int:
    """按废止说明在同批 BOI 记录之间建立替代关系;被替代的一份状态改为 superseded。返回建立的关系数。"""
    by_key = {r["doc_no"]: r for r in records if r.get("doc_no")}
    n = 0
    for r in records:
        for key in r.pop("_repeals", []):
            old = by_key.get(key)
            if old is None or old is r:
                continue
            r["relations"].append({"type": "supersedes", "uid": old["uid"]})
            old["relations"].append({"type": "superseded_by", "uid": r["uid"]})
            old["status_id"] = "superseded"
            n += 1
    for r in records:
        r.pop("_repeals", None)
        r["relations"].sort(key=lambda x: (x["type"], x["uid"]))
    return n


def normalize_boi(obj: dict, run_at: str) -> tuple[dict | None, str]:
    from .collect import passes_red_lines
    name = _clean(str(obj.get("topic_name") or ""))
    subject = _clean(str(obj.get("topic_preview") or ""))
    if not (name or subject):
        return None, "无标题"
    title = name if (not subject or subject in name) else f"{name} เรื่อง {subject}"
    ok, why = passes_red_lines(title)
    if not ok:
        return None, why
    try:
        day = datetime.fromisoformat(str(obj.get("topic_date"))[:10]).date().isoformat()
    except ValueError:
        return None, "无可解析日期"
    path = str(obj.get("file_path") or "").strip()
    if not path.lower().endswith(".pdf"):
        return None, "没有官方 PDF"
    pdf = urljoin(BOI_BASE, quote(path, safe="/:._-?=&%"))
    status_text = str(obj.get("topic_status") or "").lower()
    basis = _clean(str(obj.get("topic_source") or ""))
    agency = "boi"
    rec = _record(
        f"TH-BOI-{day.replace('-', '')}-{obj['topic_id']}", title, day, pdf, "boi_web", run_at,
        agency=agency, domain="biz", legal_form=legal_form_of(title),
        status="repealed" if any(k in status_text for k in _BOI_REPEALED) else "in_force",
        doc_no=boi_doc_key(name),
        note=("自 BOI 官网公告列表自动入库;日期为公告日期" + (f";依据/说明:{basis[:160]}" if basis else "")
              + ";中文标题与摘要待翻译环节补全"),
        source_note="BOI 官网原文 PDF")
    rec["_repeals"] = boi_repealed_keys(basis)        # link_boi 用完即删,不写入事实层
    return rec, ""


def fetch_boi(client: httpx.Client) -> tuple[list[dict], str]:
    objs = parse_boi(client.get(BOI_LIST).raise_for_status().text)
    if not objs:
        raise RuntimeError("公告列表页里没有找到内嵌数据(dataMasterLaws),页面可能改版")
    return objs, f"公告列表共 {len(objs)} 条"


def in_window(day: str, cutoff: date) -> bool:
    return bool(day) and date.fromisoformat(day) >= cutoff
