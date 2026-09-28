# -*- coding: utf-8 -*-
"""每条政策一个静态落地页 + sitemap + robots + ads.txt。

为什么:调研报告第八章把「Google 中文长尾 SEO」列为最大的冷启动红利 ——
每篇政策天然是一个长尾着陆页。但主站是单页应用,内容由 JS 渲染,爬虫基本看不到。
这里为每条可呈现的政策生成一个纯 HTML 页面(无需 JS 即可读完全文),带 canonical、
Open Graph 与 schema.org/Legislation 结构化数据。

GEO(生成式引擎优化):让 ChatGPT、Perplexity、Claude、豆包等 AI 检索能读懂并引用本站 ——
每页开头一句话结论 + 要点速览 + 引用格式,根目录提供 llms.txt / llms-full.txt,
robots.txt 明确放行 AI 检索爬虫。

输出全部是派生产物(p/*.html、p/topic/*.html、sitemap.xml、robots.txt、feed.xml、
llms.txt、llms-full.txt、index.html 里的两个受管区块、ads.txt),由 app.export 调用,
与 data/site/*.json 一样禁止手改,CI 会检查它们与事实层一致。
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics as A
from .config import REPO_ROOT, SITE_DIR, settings
from .ingest import split_summary
from .models import Document, Domain

PAGES_DIR = REPO_ROOT / "p"
ADS_CONFIG = REPO_ROOT / "config" / "ads.json"
SUPPORT_CONFIG = REPO_ROOT / "config" / "support.json"
ANALYTICS_CONFIG = REPO_ROOT / "config" / "analytics.json"
SEO_CONFIG = REPO_ROOT / "config" / "seo.json"
SITE_NAME = "政策脉络 · 泰国"
SITE_DESC = ("泰国皇家公报、内阁决议与各部委政策的中文结构化数据库:每条附泰文原文(泰国政府网站)"
             "溯源,含演进脉络、七维政策分析与趋势看板。非官方翻译,以泰文原文为准。")

# 明确放行的 AI 检索 / 问答 / 训练爬虫。* 组已经 Allow /,单列出来是向各家表明态度,
# 同时避免有些爬虫只认自己名字的组。GEO 的前提是它们能抓到页面
AI_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot",
               "Claude-User", "PerplexityBot", "Perplexity-User", "Google-Extended",
               "Applebot-Extended", "Bytespider", "Amazonbot", "meta-externalagent", "CCBot",
               "DuckAssistBot", "cohere-ai", "MistralAI-User"]

REL_ZH = {"supersedes": "替代", "superseded_by": "被替代", "amends": "修订", "amended_by": "被修订",
          "implements": "落实", "implemented_by": "被落实", "repeals": "废止",
          "repealed_by": "被废止", "related": "相关"}
DIR_ZH = {"tight": "收紧", "loose": "放宽", "neutral": "中性"}
CONF_ZH = {"high": "官方原文核对", "med": "官方引述/二手一致", "low": "单一二手来源", "none": "未取得"}

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731


def clear_dir(path: Path) -> None:
    """清空目录内容但保留目录本身(可能是挂载点)。"""
    path.mkdir(parents=True, exist_ok=True)
    for f in path.iterdir():
        if f.is_dir() and not f.is_symlink():
            shutil.rmtree(f)
        else:
            f.unlink()


def slug(uid: str) -> str:
    return uid.lower()


def page_url(uid: str) -> str:
    return f"{settings.site_url}/p/{slug(uid)}.html"


def seo_config() -> dict:
    return json.loads(SEO_CONFIG.read_text(encoding="utf-8")) if SEO_CONFIG.exists() else {}


def _ld(obj: dict) -> str:
    # </ 转义:摘要里万一出现 </script> 也不会提前结束脚本块
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>")


def _head(title: str, desc: str, canonical: str, jsonld: list[dict] | dict | None = None,
          up: str = "../") -> str:
    lds = jsonld if isinstance(jsonld, list) else ([jsonld] if jsonld else [])
    ld = "\n".join(_ld(x) for x in lds)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{e(canonical)}">
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" title="{SITE_NAME} · 最新政策" href="{up}feed.xml">
<meta property="og:type" content="article">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{up}css/main.css">
{ld}
</head>
<body>
<header>
  <div class="brand"><a href="{up}index.html" style="display:flex;align-items:center;gap:14px;color:inherit;text-decoration:none">
    <div class="seal">脉</div><div class="brand-name">{SITE_NAME}</div></a>
    <div class="brand-sub">Thai Policy Lineage · นโยบายไทย</div></div>
  <div class="header-right"><a href="{up}p/index.html" style="color:inherit">全部政策</a>
    <button class="btn-solid" data-support-button hidden>☕ 打赏支持</button></div>
</header>
<main style="max-width:880px;margin:0 auto;padding:32px 20px">"""


def _foot(up: str = "../") -> str:
    return f"""</main>
<footer>{SITE_NAME} —— 官方源自动监测 · 全部内容可溯源 · 零带货中立平台。
本站译文均为非官方翻译,仅供参考,以泰文原文为准;不构成法律意见。
<a href="{up}privacy.html">隐私政策</a> · <a href="{up}p/index.html">全部政策</a></footer>
<script src="{up}js/track.js" data-base="{up}"></script>
<script src="{up}js/ads.js" data-base="{up}"></script>
<script src="{up}js/vendor/qrcode-generator-1.4.4.js"></script>
<script src="{up}js/promptpay.js"></script>
<script src="{up}js/support.js" data-base="{up}"></script>
</body>
</html>
"""


FOOT = _foot()


def _field(k: str, v) -> str:
    return (f'<div class="field"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
            if v else "")


def page_title(t: str) -> str:
    """搜索结果标题约显示 30 个汉字;公报标题常常很长,截短并用短后缀,总长控制在 56 字以内。"""
    t = re.sub(r"\s+", " ", t or "").strip()
    return (t if len(t) <= 48 else t[:47] + "…") + " | 泰国政策"


def topic_url(dom_id: str) -> str:
    return f"{settings.site_url}/p/topic/{dom_id}.html"


def _lede(v: dict) -> str:
    """一句话结论:谁、何时、发布了什么、现在什么状态。AI 摘答时最常直接引用开头这一句。"""
    d = v["dates"]
    who = v["org"] or "泰国政府"
    if d.get("published_at"):
        when = f"于 {d['published_at']} 在泰国皇家公报刊登"
    elif d.get("resolved_at"):
        when = f"于 {d['resolved_at']} 经内阁决议通过"
    else:
        when = "发布"
    no = f"({v['doc_no_label']} {v['doc_no']})" if v["doc_no"] else ""
    eff = f",{d['effective_from']} 起生效" if d.get("effective_from") else ""
    sep = " " if who[-1:].isascii() else ""
    return f"{who}{sep}{when}《{v['title_zh']}》{no}{eff}。当前状态:{v['status_label']}。"


def render_page(s: Session, doc: Document, today, titles: dict[str, str],
                dom: tuple[str, str] = ("", ""), related: list[tuple[str, str, str]] = ()) -> str:
    """dom = (领域 id, 领域中文名);related = 同领域相邻政策 [(uid, 日期, 标题)],做站内链接。"""
    v = A.document_view(s, doc, today)
    d = v["dates"]
    title = page_title(v["title_zh"])
    desc = v["summary_zh"] or v["title_zh"]
    if len(desc) < 80:                 # 摘要太短(搜索结果里几乎没信息),补上一句话结论
        desc = f"{desc} {_lede(v)}".strip()
    desc = desc[:150]
    canonical = page_url(doc.uid)

    rels = "".join(
        f'<li>{e(REL_ZH.get(r.type, r.type))}:'
        f'<a href="{e(slug(r.dst_uid))}.html">{e(titles.get(r.dst_uid, r.dst_uid))}</a></li>'
        for r in doc.relations_out if r.dst_uid in titles)
    near = "".join(f'<li><a href="{e(slug(u))}.html">{e(t)}</a> <span class="lib-date">{e(dt)}</span></li>'
                   for u, dt, t in related)
    # 能生成落地页的都已有官方原文(入库规则保证),这里只负责列出原文与公报卷期
    official = [x for x in doc.sources if x.role == "official" and x.url]
    cite = f"{v['doc_no_label']} {v['doc_no']} · " if v["doc_no"] else ""
    links = " · ".join(f'<a href="{e(x.url)}" rel="nofollow noopener" target="_blank">{e(x.url)}</a>'
                       for x in official)
    origin = "泰文原文(官方):" + cite + links

    timeline = [(d.get("resolved_at"), "内阁决议"), (d.get("comment_deadline"), "征求意见截止"),
                (d.get("published_at"), "刊登皇家公报"), (d.get("effective_from"), "生效"),
                (d.get("effective_to"), "失效")]
    timeline = sorted([t for t in timeline if t[0]])
    tl = "".join(f'<div class="tl-item done"><div class="tl-date">{e(t[0])}</div>'
                 f'<div class="tl-name">{e(t[1])}</div></div>' for t in timeline)

    when = " / ".join(f"{n} {dt}" for dt, n in timeline) or "—"
    facts = [("是什么", v["title_zh"]), ("发文机关", v["org"]),
             (v["doc_no_label"], v["doc_no"]), ("关键日期", when), ("当前状态", v["status_label"]),
             ("法律层级", v["legal_form"]), ("所属领域", dom[1])]
    facts_html = "".join(f"<dt>{e(k)}</dt><dd>{e(val)}</dd>" for k, val in facts if val)

    first_official = official[0].url if official else ""
    legislation = {
        "@context": "https://schema.org", "@type": "Legislation",
        "name": v["title_zh"], "alternateName": v["title_th"] or None,
        "legislationIdentifier": v["doc_no"] or doc.uid,
        "legislationJurisdiction": "TH",
        "legislationType": v["legal_form"],
        "legislationDate": d.get("published_at") or d.get("resolved_at"),
        "legislationLegalForce": "InForce" if doc.status.in_force else "NotInForce",
        "legislationPassedBy": ({"@type": "GovernmentOrganization", "name": v["org"]}
                                if v["org"] else None),
        "datePublished": v["date"] or None,
        "inLanguage": "zh-CN", "url": canonical, "abstract": v["summary_zh"],
        "about": dom[1] or None,
        "isAccessibleForFree": True,
        # 本页是泰文原文的中文译述:指明原作,方便搜索与 AI 引擎追溯到官方来源
        "translationOfWork": ({"@type": "Legislation", "name": v["title_th"] or v["title_zh"],
                               "inLanguage": "th", "url": first_official} if first_official else None),
        "isBasedOn": first_official or None,
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": f"{settings.site_url}/"},
    }
    legislation = {k: val for k, val in legislation.items() if val}
    crumbs = [("首页", f"{settings.site_url}/"), ("全部政策", f"{settings.site_url}/p/index.html")]
    if dom[0]:
        crumbs.append((dom[1], topic_url(dom[0])))
    crumbs.append((v["title_zh"], canonical))
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList",
                  "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                      for i, (n, u) in enumerate(crumbs)]}

    crumb_html = '<a href="index.html">全部政策</a>' + (
        f' / <a href="topic/{e(dom[0])}.html">{e(dom[1])}</a>' if dom[0] else "") + f" / {e(v['legal_form'])}"
    citation = (f"《{v['title_zh']}》中文摘要,{SITE_NAME},{canonical}"
                + (f"(泰文原文:{first_official})" if first_official else ""))

    body = f"""
<div class="crumb">{crumb_html}</div>
<article class="card" style="padding:26px 30px">
  <div class="pc-top"><span class="chip {e(v['domain'])}">{e(v['domain_label'])}</span>
    <span class="dir {e(v['direction'])}">{e(DIR_ZH.get(v['direction'], ''))}</span>
    {'<span class="verified">已人工复核</span>' if v['verified'] else ''}</div>
  <h1 class="d-title">{e(v['title_zh'])}</h1>
  {f'<div class="d-thai" lang="th">泰文原题:{e(v["title_th"])}</div>' if v['title_th'] else ''}
  <p class="lede">{e(_lede(v))}</p>
  <div class="fields">
    {_field('发文机关', v['org'])}{_field(v['doc_no_label'], v['doc_no'])}
    {_field('内阁决议日', d.get('resolved_at'))}{_field('刊登公报日', d.get('published_at'))}
    {_field('生效日', d.get('effective_from'))}{_field('状态', v['status_label'])}
    {_field('法律层级', v['legal_form'])}{_field('稳定性', f"{v['stability']} / 5")}
  </div>
  <div class="d-body">
    <h2 style="font-size:15px">中文摘要</h2><p>{e(v['summary_zh'])}</p>
    {('<h2 style="font-size:15px">正文要点</h2><ul class="points">' + "".join(f"<li>{e(k)}</li>" for k in v["key_points"]) + "</ul>") if v["key_points"] else ""}
    <h2 style="font-size:15px">要点速览</h2><dl class="facts">{facts_html}</dl>
    {f'<h2 style="font-size:15px">生命周期</h2><div class="timeline">{tl}</div>' if tl else ''}
    {f'<h2 style="font-size:15px">关联文件</h2><ul>{rels}</ul>' if rels else ''}
  </div>
  <div class="origin">{origin}<br>字段可信度:日期 {e(CONF_ZH.get(v['confidence']['dates'], ''))}
    · 文号 {e(CONF_ZH.get(v['confidence']['doc_no'], ''))}</div>
  <div class="cite">引用本页:{e(citation)}</div>
  <div class="disclaim">免责声明:本页为非官方翻译,仅供参考,如与泰文原文有出入,以泰文原文为准;
    本内容不构成法律或税务意见。本站与泰国政府无隶属关系。</div>
</article>
{f'<section class="related"><h2 class="mod">同领域政策 · {e(dom[1])}</h2><ul>{near}</ul><a href="topic/{e(dom[0])}.html">查看{e(dom[1])}全部政策 →</a></section>' if near else ''}
<div class="support-slot"></div>
<div class="ad-slot" data-slot="landing_bottom" style="margin-top:18px"></div>
<p style="margin-top:18px"><a href="../index.html">← 返回政策脉络首页(检索、趋势、七维分析)</a></p>
"""
    return _head(title, desc, canonical, [legislation, breadcrumb]) + body + FOOT


def _rows_html(items, up: str = "") -> str:
    return "".join(f'<div class="lib-row"><span class="lib-date">{e(dt)}</span>'
                   f'<div class="lib-title"><a href="{up}{e(slug(uid))}.html">{e(t)}</a></div></div>'
                   for dt, uid, t in items)


def render_index(rows: list[tuple[str, str, str, str]], topics: list[tuple[str, str, int]] = ()) -> str:
    """rows: (领域中文名, 日期, uid, 标题),已按日期倒序。按领域分组的纯 HTML 目录,给爬虫一个入口。"""
    groups: dict[str, list] = {}
    for dom, date, uid, title in rows:
        groups.setdefault(dom, []).append((date, uid, title))
    nav = " · ".join(f'<a href="topic/{e(i)}.html">{e(zh)}({n})</a>' for i, zh, n in topics)
    body = ('<h1 class="page">全部政策</h1><div class="page-sub">按领域分组 · 每条均附泰文原文(官方)溯源'
            + (f"<br>按领域浏览:{nav}" if nav else "") + "</div>")
    for dom in sorted(groups):
        body += f'<h2 class="mod" style="margin-top:24px">{e(dom)}</h2><div class="lib-wrap">{_rows_html(groups[dom])}</div>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "全部政策",
          "url": f"{settings.site_url}/p/index.html", "inLanguage": "zh-CN",
          "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": f"{settings.site_url}/"}}
    return (_head("全部政策 | 泰国政策中文库",
                  f"泰国皇家公报、内阁决议与各部委政策的中文目录,共 {len(rows)} 条,按签证、税务、劳工、"
                  "海关贸易等领域分组;每条附泰文原文(泰国政府网站)链接,非官方翻译。",
                  f"{settings.site_url}/p/index.html", ld) + body + FOOT)


def render_topic(dom_id: str, zh: str, en: str, items: list[tuple[str, str, str]]) -> str:
    """领域专题页:某一领域的全部政策。长尾词「泰国 + 领域 + 政策」的落地页。"""
    url = topic_url(dom_id)
    latest = items[0][0] if items else ""
    title = f"泰国{zh}政策汇总(中文) | {SITE_NAME}"
    desc = (f"泰国{zh}({en})相关的皇家公报、内阁决议与部委公告中文摘要,共 {len(items)} 条"
            + (f",最新更新 {latest}" if latest else "") + ";每条附泰文原文(官方)链接。")
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"泰国{zh}政策",
           "url": url, "inLanguage": "zh-CN", "about": zh,
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                          "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                               "url": page_url(uid), "name": t}
                                              for i, (_, uid, t) in enumerate(items[:50])]}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList",
           "itemListElement": [
               {"@type": "ListItem", "position": 1, "name": "首页", "item": f"{settings.site_url}/"},
               {"@type": "ListItem", "position": 2, "name": "全部政策", "item": f"{settings.site_url}/p/index.html"},
               {"@type": "ListItem", "position": 3, "name": zh, "item": url}]}]
    body = (f'<div class="crumb"><a href="../index.html">全部政策</a> / {e(zh)}</div>'
            f'<h1 class="page">泰国{e(zh)}政策</h1>'
            f'<div class="page-sub">{e(desc)}</div>'
            f'<div class="lib-wrap">{_rows_html(items, "../")}</div>')
    return _head(title, desc, url, ld, up="../../") + body + _foot("../../")


# ───────────────────── 站点级文件:robots / sitemap / feed / llms ─────────────────────

def render_robots() -> str:
    rules = "Allow: /\nDisallow: /api/\nDisallow: /admin\n"
    ai = "".join(f"User-agent: {b}\n" for b in AI_CRAWLERS)
    return ("# 公开页面欢迎所有搜索引擎与 AI 检索抓取(由 backend/app/seo.py 生成)\n"
            f"User-agent: *\n{rules}\n"
            "# AI 检索 / 问答引擎:允许抓取,以便回答时引用本站并附原文链接\n"
            f"{ai}{rules}\n"
            f"Sitemap: {settings.site_url}/sitemap.xml\n")


def render_sitemap(urls: list[tuple[str, str | None]]) -> str:
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        sm.append(f"  <url><loc>{e(loc)}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
                  + "</url>")
    sm.append("</urlset>")
    return "\n".join(sm) + "\n"


def render_feed(entries: list[dict]) -> str:
    """Atom 订阅:最新 50 条。updated 取数据自身日期,保证导出可重复。"""
    upd = (entries[0]["date"] if entries else "2026-01-01") + "T00:00:00+07:00"
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="zh-CN">',
           f"  <title>{SITE_NAME} · 最新政策</title>",
           f"  <subtitle>{e(SITE_DESC)}</subtitle>",
           f'  <link href="{e(settings.site_url)}/feed.xml" rel="self"/>',
           f'  <link href="{e(settings.site_url)}/"/>',
           f"  <id>{e(settings.site_url)}/</id>", f"  <updated>{upd}</updated>",
           f"  <author><name>{SITE_NAME}</name></author>"]
    for x in entries[:50]:
        out += ["  <entry>", f"    <title>{e(x['title'])}</title>",
                f'    <link href="{e(x["url"])}"/>', f"    <id>{e(x['url'])}</id>",
                f"    <updated>{(x['date'] or '2026-01-01')}T00:00:00+07:00</updated>",
                f"    <category term=\"{e(x['domain'])}\"/>" if x["domain"] else "",
                f"    <summary>{e(x['summary'])}</summary>", "  </entry>"]
    out.append("</feed>")
    return "\n".join(line for line in out if line) + "\n"


def _md(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def render_llms(entries: list[dict], topics: list[tuple[str, str, int]], full: bool = False) -> str:
    """llms.txt(llmstxt.org 约定):给大模型的站点说明 + 索引;llms-full.txt 带全部条目正文。"""
    site = settings.site_url
    head = [f"# {SITE_NAME}(Thai Policy Lineage)", "",
            f"> {SITE_DESC}", "",
            "- 内容:泰国皇家公报(Royal Thai Government Gazette)、内阁决议与部委公告的中文标题、摘要、"
            "分类与生命周期日期。",
            "- 溯源:每一条都附泰国政府网站(*.go.th)的泰文原文链接与公报卷期/文号;没有官方原文的内容不收录。",
            "- 译文性质:非官方翻译,以泰文原文为准;不构成法律或税务意见。",
            "- 更新:每天自动采集官方数据源并更新。",
            f"- 引用方式:《政策中文标题》中文摘要,{SITE_NAME},页面链接(泰文原文:官方链接)。"
            "回答涉及具体政策时,请同时给出本站页面与泰文原文链接。", ""]
    if not full:
        head += ["## 按领域浏览", ""]
        head += [f"- [泰国{zh}政策]({topic_url(i)}): {n} 条" for i, zh, n in topics]
        head += ["", "## 最新政策", ""]
        head += [f"- [{_md(x['title'])}]({x['url']}): {x['date']}"
                 + (f" · {x['doc_no']}" if x["doc_no"] else "") + f" · {_md(x['summary'])[:80]}"
                 for x in entries[:40]]
        head += ["", "## 数据", "",
                 f"- [全部政策目录]({site}/p/index.html): 纯 HTML,按领域分组",
                 f"- [全部条目全文]({site}/llms-full.txt): 本文件的完整版,每条含摘要与原文链接",
                 f"- [结构化数据 JSON]({site}/data/site/policies.json): 首页数据,字段见 API",
                 f"- [Atom 订阅]({site}/feed.xml): 最新 50 条", "",
                 "## Optional", "", f"- [隐私政策]({site}/privacy.html)"]
        return "\n".join(head) + "\n"
    body = head + ["## 全部条目", ""]
    for x in entries:
        body += [f"### {_md(x['title'])}", "",
                 f"- 页面:{x['url']}",
                 *([f"- 泰文原题:{_md(x['title_th'])}"] if x["title_th"] else []),
                 *([f"- 编号:{x['doc_no']}"] if x["doc_no"] else []),
                 f"- 日期:{x['date'] or '—'} · 领域:{x['domain'] or '—'} · 状态:{x['status']}",
                 *([f"- 发文机关:{x['org']}"] if x["org"] else []),
                 f"- 泰文原文(官方):{x['official']}", "",
                 _md(x["summary"]), *([""] + [f"- {_md(k)}" for k in x["points"]] if x["points"] else []), ""]
    return "\n".join(body) + "\n"


# ───────────────────── index.html 受管区块 ─────────────────────

def _replace_block(text: str, name: str, content: str) -> str:
    """替换 <!-- seo:name --> … <!-- /seo:name --> 之间的内容;没有标记就原样返回。"""
    pat = re.compile(rf"(<!-- seo:{name} [^>]*-->\n?).*?(\s*<!-- /seo:{name} -->)", re.S)
    return pat.sub(lambda m: m.group(1) + content + m.group(2), text, count=1)


def update_index_html(entries: list[dict], topics: list[tuple[str, str, int]], cfg: dict) -> bool:
    path = REPO_ROOT / "index.html"
    if not path.exists():
        return False
    site = settings.site_url
    ver = cfg.get("verification") or {}
    metas = {"google": "google-site-verification", "bing": "msvalidate.01",
             "baidu": "baidu-site-verification", "yandex": "yandex-verification"}
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": f"{site}/#website", "name": SITE_NAME,
         "alternateName": ["Thai Policy Lineage", "泰国政策中文库"], "url": f"{site}/",
         "inLanguage": "zh-CN", "description": SITE_DESC,
         "publisher": {"@id": f"{site}/#org"}},
        {"@type": "Organization", "@id": f"{site}/#org", "name": SITE_NAME, "url": f"{site}/",
         "logo": f"{site}/favicon.svg"},
        {"@type": "Dataset", "name": "泰国政策中文结构化数据", "description": SITE_DESC,
         "url": f"{site}/p/index.html", "inLanguage": "zh-CN", "isAccessibleForFree": True,
         "spatialCoverage": {"@type": "Place", "name": "Thailand"},
         "creator": {"@id": f"{site}/#org"},
         "isBasedOn": "https://ratchakitcha.soc.go.th/",
         "dateModified": entries[0]["date"] if entries else None,
         "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                           "contentUrl": f"{site}/data/site/policies.json"},
                          {"@type": "DataDownload", "encodingFormat": "text/plain",
                           "contentUrl": f"{site}/llms-full.txt"}]},
    ]}
    graph["@graph"][2] = {k: v for k, v in graph["@graph"][2].items() if v is not None}
    head = "\n".join([
        f'<link rel="canonical" href="{e(site)}/">',
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
        f'<link rel="alternate" type="application/atom+xml" title="{SITE_NAME} · 最新政策" href="feed.xml">',
        f'<meta property="og:url" content="{e(site)}/">',
        '<meta property="og:locale" content="zh_CN">',
        *[f'<meta name="{metas[k]}" content="{e(ver[k])}">' for k in metas if ver.get(k)],
        _ld(graph)])
    nav = " · ".join(f'<a href="p/topic/{e(i)}.html">{e(zh)}</a>' for i, zh, _ in topics)
    latest = " · ".join(f'<a href="p/{e(slug(x["uid"]))}.html">{e(x["title"])}</a>' for x in entries[:12])
    links = (f'<nav class="seo-nav" aria-label="站内导航">'
             + (f"<div><b>按领域浏览</b> {nav}</div>" if nav else "")
             + (f"<div><b>最新收录</b> {latest}</div>" if latest else "") + "</nav>")
    old = path.read_text(encoding="utf-8")
    new = _replace_block(_replace_block(old, "head", head), "links", links)
    if new != old:
        path.write_text(new, encoding="utf-8")

    # 隐私政策页:canonical + WebPage 结构化数据(页面本身是手写的静态页)
    priv = REPO_ROOT / "privacy.html"
    if priv.exists():
        ld = {"@context": "https://schema.org", "@type": "WebPage", "name": "隐私政策",
              "url": f"{site}/privacy.html", "inLanguage": "zh-CN",
              "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": f"{site}/"}}
        old = priv.read_text(encoding="utf-8")
        new = _replace_block(old, "head", f'<link rel="canonical" href="{e(site)}/privacy.html">\n{_ld(ld)}')
        if new != old:
            priv.write_text(new, encoding="utf-8")
    return True


def build(s: Session) -> dict[str, int]:
    today = A._today(s)
    docs = s.scalars(select(Document).order_by(Document.display_date.desc().nullslast(),
                                               Document.uid)).all()
    titles = {d.uid: d.title_zh for d in docs}
    domains = {d.id: d for d in s.scalars(select(Domain)).all()}

    def dom_of(doc: Document) -> tuple[str, str]:
        dom = min(doc.domains, key=lambda x: x.seq).domain_id if doc.domains else ""
        return (dom, domains[dom].zh) if dom in domains else ("", "其他")

    # 整目录重建:已删除或被标 skip 的政策,其落地页也要消失。
    # 只清空内容、不删目录本身 —— 生产环境 p/ 是 docker 挂载点,删挂载点会 EBUSY,
    # 导出失败会让容器启动命令(ingest && export && uvicorn)永远起不来
    clear_dir(PAGES_DIR)
    (PAGES_DIR / "topic").mkdir()

    by_dom: dict[str, list[tuple[str, str, str]]] = {}
    for doc in docs:
        dom = dom_of(doc)
        by_dom.setdefault(dom[0], []).append(
            (doc.display_date.isoformat() if doc.display_date else "", doc.uid, doc.title_zh))

    rows, entries = [], []
    for doc in docs:
        dom = dom_of(doc)
        peers = by_dom.get(dom[0], [])
        i = next(k for k, x in enumerate(peers) if x[1] == doc.uid)
        related = [(u, dt, t) for dt, u, t in (peers[max(0, i - 3):i] + peers[i + 1:i + 4])][:6]
        (PAGES_DIR / f"{slug(doc.uid)}.html").write_text(
            render_page(s, doc, today, titles, dom if dom[0] else ("", ""), related), encoding="utf-8")
        date_s = doc.display_date.isoformat() if doc.display_date else ""
        rows.append((dom[1], date_s, doc.uid, doc.title_zh))
        official = next((x.url for x in doc.sources if x.role == "official" and x.url), "")
        entries.append({"uid": doc.uid, "title": doc.title_zh, "title_th": doc.title_th or "",
                        "url": page_url(doc.uid), "date": date_s, "domain": dom[1] if dom[0] else "",
                        "doc_no": doc.doc_no or "", "summary": split_summary(doc.summary_zh)[0],
                        "points": split_summary(doc.summary_zh)[1],
                        "status": doc.status.zh, "official": official,
                        "org": A.document_view(s, doc, today)["org"]})

    topics = sorted(((i, domains[i].zh, len(items)) for i, items in by_dom.items() if i),
                    key=lambda t: (-t[2], t[0]))
    for i, zh, _ in topics:
        (PAGES_DIR / "topic" / f"{i}.html").write_text(
            render_topic(i, zh, domains[i].en or "", by_dom[i]), encoding="utf-8")
    (PAGES_DIR / "index.html").write_text(render_index(rows, topics), encoding="utf-8")

    # sitemap:lastmod 用数据自身的日期,保证导出可重复
    newest = entries[0]["date"] if entries else None
    urls = [(f"{settings.site_url}/", newest), (f"{settings.site_url}/p/index.html", newest),
            (f"{settings.site_url}/privacy.html", None)]
    urls += [(topic_url(i), by_dom[i][0][0] or None) for i, _, _ in topics]
    urls += [(x["url"], x["date"] or None) for x in entries]
    (REPO_ROOT / "sitemap.xml").write_text(render_sitemap(urls), encoding="utf-8")
    (REPO_ROOT / "robots.txt").write_text(render_robots(), encoding="utf-8")
    (REPO_ROOT / "feed.xml").write_text(render_feed(entries), encoding="utf-8")
    (REPO_ROOT / "llms.txt").write_text(render_llms(entries, topics), encoding="utf-8")
    (REPO_ROOT / "llms-full.txt").write_text(render_llms(entries, topics, full=True), encoding="utf-8")
    update_index_html(entries, topics, seo_config())

    # 广告配置:config/ads.json → data/site/ads.json;启用 AdSense 时生成 ads.txt
    ads = json.loads(ADS_CONFIG.read_text(encoding="utf-8")) if ADS_CONFIG.exists() else {"enabled": False}
    (SITE_DIR / "ads.json").write_text(json.dumps(ads, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    support = (json.loads(SUPPORT_CONFIG.read_text(encoding="utf-8"))
               if SUPPORT_CONFIG.exists() else {"enabled": False})
    (SITE_DIR / "support.json").write_text(json.dumps(support, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")
    analytics = (json.loads(ANALYTICS_CONFIG.read_text(encoding="utf-8"))
                 if ANALYTICS_CONFIG.exists() else {"self_hosted": {"enabled": False}})
    (SITE_DIR / "analytics.json").write_text(json.dumps(analytics, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")
    client = (ads.get("adsense") or {}).get("client", "")
    ads_txt = REPO_ROOT / "ads.txt"
    if client.startswith("ca-pub-"):
        ads_txt.write_text(f"google.com, {client.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n",
                           encoding="utf-8")
    elif ads_txt.exists():
        ads_txt.unlink()
    return {"pages": len(docs) + 1, "topics": len(topics), "sitemap_urls": len(urls)}
