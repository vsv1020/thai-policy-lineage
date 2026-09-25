# -*- coding: utf-8 -*-
"""每条政策一个静态落地页 + sitemap + robots + ads.txt。

为什么:调研报告第八章把「Google 中文长尾 SEO」列为最大的冷启动红利 ——
每篇政策天然是一个长尾着陆页。但主站是单页应用,内容由 JS 渲染,爬虫基本看不到。
这里为每条可呈现的政策生成一个纯 HTML 页面(无需 JS 即可读完全文),带 canonical、
Open Graph 与 schema.org/Legislation 结构化数据。

输出全部是派生产物(p/*.html、sitemap.xml、robots.txt、ads.txt),由 app.export 调用,
与 data/site/*.json 一样禁止手改,CI 会检查它们与事实层一致。
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics as A
from .config import REPO_ROOT, SITE_DIR, settings
from .models import Document, Domain

PAGES_DIR = REPO_ROOT / "p"
ADS_CONFIG = REPO_ROOT / "config" / "ads.json"

REL_ZH = {"supersedes": "替代", "superseded_by": "被替代", "amends": "修订", "amended_by": "被修订",
          "implements": "落实", "implemented_by": "被落实", "repeals": "废止",
          "repealed_by": "被废止", "related": "相关"}
DIR_ZH = {"tight": "收紧", "loose": "放宽", "neutral": "中性"}
CONF_ZH = {"high": "官方原文核对", "med": "官方引述/二手一致", "low": "单一二手来源", "none": "未取得"}

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731


def slug(uid: str) -> str:
    return uid.lower()


def page_url(uid: str) -> str:
    return f"{settings.site_url}/p/{slug(uid)}.html"


def _head(title: str, desc: str, canonical: str, jsonld: dict | None = None) -> str:
    ld = (f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
          if jsonld else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="政策脉络 · 泰国">
<link rel="stylesheet" href="../css/main.css">
{ld}
</head>
<body>
<header>
  <div class="brand"><a href="../index.html" style="display:flex;align-items:center;gap:14px;color:inherit;text-decoration:none">
    <div class="seal">脉</div><div class="brand-name">政策脉络 · 泰国</div></a>
    <div class="brand-sub">Thai Policy Lineage · นโยบายไทย</div></div>
  <div class="header-right"><a href="index.html" style="color:inherit">全部政策</a></div>
</header>
<main style="max-width:880px;margin:0 auto;padding:32px 20px">"""


FOOT = """</main>
<footer>政策脉络 · 泰国 —— 官方源自动监测 · 全部内容可溯源 · 零带货中立平台。
本站译文均为非官方翻译,仅供参考,以泰文原文为准;不构成法律意见。</footer>
<script src="../js/ads.js" data-base="../"></script>
</body>
</html>
"""


def _field(k: str, v) -> str:
    return (f'<div class="field"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
            if v else "")


def render_page(s: Session, doc: Document, today, titles: dict[str, str]) -> str:
    v = A.document_view(s, doc, today)
    d = v["dates"]
    title = f"{v['title_zh']} | 泰国政策中文库"
    desc = (v["summary_zh"] or v["title_zh"])[:150]
    canonical = page_url(doc.uid)

    rels = "".join(
        f'<li>{e(REL_ZH.get(r.type, r.type))}:'
        f'<a href="{e(slug(r.dst_uid))}.html">{e(titles.get(r.dst_uid, r.dst_uid))}</a></li>'
        for r in doc.relations_out if r.dst_uid in titles)
    official = [x for x in doc.sources if x.role == "official" and x.url]
    origin = ("泰文原文:" + " · ".join(
        f'<a href="{e(x.url)}" rel="nofollow noopener" target="_blank">{e(x.url)}</a>'
        for x in official)) if official else \
        '<span style="color:var(--seal)">尚未取得官方原文链接</span> —— 本条依二手来源整理,取得公报原件后回填。'

    timeline = [(d.get("resolved_at"), "内阁决议"), (d.get("comment_deadline"), "征求意见截止"),
                (d.get("published_at"), "刊登皇家公报"), (d.get("effective_from"), "生效"),
                (d.get("effective_to"), "失效")]
    timeline = sorted([t for t in timeline if t[0]])
    tl = "".join(f'<div class="tl-item done"><div class="tl-date">{e(t[0])}</div>'
                 f'<div class="tl-name">{e(t[1])}</div></div>' for t in timeline)

    jsonld = {
        "@context": "https://schema.org", "@type": "Legislation",
        "name": v["title_zh"], "alternateName": v["title_th"] or None,
        "legislationIdentifier": v["doc_no"] or doc.uid,
        "legislationJurisdiction": "TH",
        "legislationType": v["legal_form"],
        "legislationDate": d.get("published_at") or d.get("resolved_at"),
        "legislationLegalForce": "InForce" if doc.status.in_force else "NotInForce",
        "inLanguage": "zh-CN", "url": canonical, "abstract": v["summary_zh"],
        "isAccessibleForFree": True,
    }
    jsonld = {k: val for k, val in jsonld.items() if val}

    body = f"""
<div class="crumb"><a href="index.html">全部政策</a> / {e(v['domain_label'])} / {e(v['legal_form'])}</div>
<article class="card" style="padding:26px 30px">
  <div class="pc-top"><span class="chip {e(v['domain'])}">{e(v['domain_label'])}</span>
    <span class="dir {e(v['direction'])}">{e(DIR_ZH.get(v['direction'], ''))}</span>
    {'<span class="verified">已人工复核</span>' if v['verified'] else
     '<span class="chip bare" style="color:var(--muted)">未经人工复核</span>'}</div>
  <h1 class="d-title">{e(v['title_zh'])}</h1>
  {f'<div class="d-thai">泰文原题:{e(v["title_th"])}</div>' if v['title_th'] else ''}
  <div class="fields">
    {_field('发文机关', v['org'])}{_field(v['doc_no_label'], v['doc_no'])}
    {_field('内阁决议日', d.get('resolved_at'))}{_field('刊登公报日', d.get('published_at'))}
    {_field('生效日', d.get('effective_from'))}{_field('状态', v['status_label'])}
    {_field('法律层级', v['legal_form'])}{_field('稳定性', f"{v['stability']} / 5")}
  </div>
  <div class="d-body">
    <h2 style="font-size:15px">中文摘要</h2><p>{e(v['summary_zh'])}</p>
    {f'<h2 style="font-size:15px">生命周期</h2><div class="timeline">{tl}</div>' if tl else ''}
    {f'<h2 style="font-size:15px">关联文件</h2><ul>{rels}</ul>' if rels else ''}
  </div>
  <div class="origin">{origin}<br>字段可信度:日期 {e(CONF_ZH.get(v['confidence']['dates'], ''))}
    · 文号 {e(CONF_ZH.get(v['confidence']['doc_no'], ''))}</div>
  <div class="disclaim">免责声明:本页为非官方翻译,仅供参考,如与泰文原文有出入,以泰文原文为准;
    本内容不构成法律或税务意见。本站与泰国政府无隶属关系。</div>
</article>
<div class="ad-slot" data-slot="landing_bottom" style="margin-top:18px"></div>
<p style="margin-top:18px"><a href="../index.html">← 返回政策脉络首页(检索、趋势、七维分析)</a></p>
"""
    return _head(title, desc, canonical, jsonld) + body + FOOT


def render_index(rows: list[tuple[str, str, str, str]]) -> str:
    """rows: (domain_label, date, uid, title)。按领域分组的纯 HTML 目录,给爬虫一个入口。"""
    groups: dict[str, list] = {}
    for dom, date, uid, title in rows:
        groups.setdefault(dom, []).append((date, uid, title))
    body = '<h1 class="page">全部政策</h1><div class="page-sub">按领域分组 · 每条均附原文溯源与可信度标注</div>'
    for dom in sorted(groups):
        items = "".join(f'<div class="lib-row"><span class="lib-date">{e(dt)}</span>'
                        f'<div class="lib-title"><a href="{e(slug(uid))}.html">{e(t)}</a></div></div>'
                        for dt, uid, t in sorted(groups[dom], reverse=True))
        body += f'<h2 class="mod" style="margin-top:24px">{e(dom)}</h2><div class="lib-wrap">{items}</div>'
    return (_head("全部政策 | 泰国政策中文库",
                  "泰国皇家公报、内阁决议与各部委政策的中文结构化数据库,每条附泰文原文溯源。",
                  f"{settings.site_url}/p/index.html") + body + FOOT)


def build(s: Session) -> dict[str, int]:
    today = A._today(s)
    docs = s.scalars(select(Document).order_by(Document.display_date.desc().nullslast())).all()
    titles = {d.uid: d.title_zh for d in docs}

    # 整目录重建:已删除或被标 skip 的政策,其落地页也要消失
    if PAGES_DIR.exists():
        shutil.rmtree(PAGES_DIR)
    PAGES_DIR.mkdir(parents=True)

    rows = []
    for doc in docs:
        (PAGES_DIR / f"{slug(doc.uid)}.html").write_text(
            render_page(s, doc, today, titles), encoding="utf-8")
        dom = min(doc.domains, key=lambda x: x.seq).domain_id if doc.domains else ""
        dom_zh = (s.get(Domain, dom).zh if dom and s.get(Domain, dom) else "其他")
        rows.append((dom_zh, doc.display_date.isoformat() if doc.display_date else "",
                     doc.uid, doc.title_zh))
    (PAGES_DIR / "index.html").write_text(render_index(rows), encoding="utf-8")

    # sitemap:lastmod 用数据自身的日期,保证导出可重复
    urls = [(f"{settings.site_url}/", None), (f"{settings.site_url}/p/index.html", None)]
    urls += [(page_url(d.uid), d.display_date.isoformat() if d.display_date else None) for d in docs]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        sm.append(f"  <url><loc>{e(loc)}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
                  + "</url>")
    sm.append("</urlset>")
    (REPO_ROOT / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (REPO_ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {settings.site_url}/sitemap.xml\n",
        encoding="utf-8")

    # 广告配置:config/ads.json → data/site/ads.json;启用 AdSense 时生成 ads.txt
    ads = json.loads(ADS_CONFIG.read_text(encoding="utf-8")) if ADS_CONFIG.exists() else {"enabled": False}
    (SITE_DIR / "ads.json").write_text(json.dumps(ads, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    client = (ads.get("adsense") or {}).get("client", "")
    ads_txt = REPO_ROOT / "ads.txt"
    if client.startswith("ca-pub-"):
        ads_txt.write_text(f"google.com, {client.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n",
                           encoding="utf-8")
    elif ads_txt.exists():
        ads_txt.unlink()
    return {"pages": len(docs) + 1, "sitemap_urls": len(urls)}
