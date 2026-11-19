# -*- coding: utf-8 -*-
"""每条政策一个静态落地页 + sitemap + robots + ads.txt。

为什么:调研报告第八章把「Google 中文长尾 SEO」列为最大的冷启动红利 ——
每篇政策天然是一个长尾着陆页。但主站是单页应用,内容由 JS 渲染,爬虫基本看不到。
这里为每条可呈现的政策生成一个纯 HTML 页面(无需 JS 即可读完全文),带 canonical、
Open Graph 与 schema.org/Legislation 结构化数据。

GEO(生成式引擎优化):让 ChatGPT、Perplexity、Claude、豆包等 AI 检索能读懂并引用本站 ——
每页开头一句话结论 + 要点速览 + 引用格式,根目录提供 llms.txt / llms-full.txt,
robots.txt 明确放行 AI 检索爬虫。

输出全部是派生产物(p/*.html、p/topic/、p/t/、p/who/、p/week/、p/guide/、p/404.html、sitemap.xml、
robots.txt、feed.xml、llms.txt、llms-full.txt、index.html 里的三个受管区块、ads.txt,以及 zh-hant/ 下
全部静态页的繁体版),由 app.export 调用,
与 data/site/*.json 一样禁止手改,CI 会检查它们与事实层一致。
"""
from __future__ import annotations

import contextvars
import html
import json
import logging
import os
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics as A
from .config import DATA_DIR, REPO_ROOT, SITE_DIR, settings
from .ingest import split_summary
from .models import Agency, Document, Domain, Party

log = logging.getLogger("policy.seo")
PAGES_DIR = REPO_ROOT / "p"
ADS_CONFIG = REPO_ROOT / "config" / "ads.json"
SUPPORT_CONFIG = REPO_ROOT / "config" / "support.json"
SUBSCRIBE_CONFIG = REPO_ROOT / "config" / "subscribe.json"
TOPICS_CONFIG = REPO_ROOT / "config" / "topics.json"
MIN_COLLECTION = 3          # 专题 / 影响对象页少于这么多条就不生成(太薄,不值得一页)
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
               "DuckAssistBot", "cohere-ai", "MistralAI-User", "meta-externalfetcher",
               "ChatGLM-Spider", "YouBot"]

REL_ZH = {"supersedes": "替代", "superseded_by": "被替代", "amends": "修订", "amended_by": "被修订",
          "implements": "落实", "implemented_by": "被落实", "repeals": "废止",
          "repealed_by": "被废止", "related": "相关"}
DIR_ZH = {"tight": "收紧", "loose": "放宽", "neutral": "中性"}
CONF_ZH = {"high": "官方原文核对", "med": "官方引述/二手一致", "low": "单一二手来源", "none": "未取得"}

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731

# 链接预览图(微信、LINE、Telegram、Facebook、X 分享时显示),1200×630;源文件 tools/og.html
OG_IMAGE = "assets/og.png"
OG_ALT = "政策脉络 · 泰国:泰国皇家公报与内阁决议的中文数据库"
ROBOTS_INDEX = "index, follow, max-snippet:-1, max-image-preview:large"
ROBOTS_NOINDEX = "noindex, follow"
GUIDE_PATH = "p/guide/royal-gazette.html"

# ───────────────────── 繁体版:/zh-hant/ 镜像简体的全部静态页 ─────────────────────
# 同一套渲染函数跑两遍:简体一遍,繁体一遍(_variant(True) 下),繁体那遍的输出再整页过 app.hant 转换。
# 渲染函数里只有三处随字形变:站内绝对地址(_base)、语言标记(_lang 等)、资源文件的相对路径(_root)。
# 站内相对链接(../index.html、topic/x.html、../../feed.xml)两边目录结构相同,不用改,自然留在 /zh-hant/ 内;
# css / js / favicon / assets 不复制,繁体页多退一级到站点根目录去取。
HANT_DIR = "zh-hant"
OG_IMAGE_HANT = "assets/og-hant.png"
# 用 ContextVar 而不是模块级全局:服务进程里的采集线程导出时,别的线程调用 page_url 等不会读到繁体状态
_HANT: contextvars.ContextVar[bool] = contextvars.ContextVar("seo_hant", default=False)


class _variant:
    """with _variant(True): 其间渲染的是繁体页(地址、语言标记按繁体版写,文字仍是简体,写盘前再转换)。
    退出时(包括抛异常)恢复原状态。"""

    def __init__(self, hant: bool):
        self.hant = hant

    def __enter__(self):
        self.token = _HANT.set(self.hant)
        return self

    def __exit__(self, *exc):
        _HANT.reset(self.token)


def _is_hant() -> bool:
    return _HANT.get()


# 繁体版没能生成时(HANT_STRICT=0 下转换出错),简体页只链向旧 zh-hant/ 里确实存在的繁体页:
# None = 全部存在(正常情况);否则是旧 zh-hant/ 里已有页面的相对路径集合
_HANT_AVAIL: contextvars.ContextVar[frozenset | None] = contextvars.ContextVar("seo_hant_avail", default=None)


def hant_strict() -> bool:
    """HANT_STRICT(默认 1):繁体版生成失败时导出直接报错(CI、本地)。
    生产环境设 0:繁体失败只记错误日志、保留旧的 zh-hant/,简体照常导出,站点照常启动。"""
    return os.getenv("HANT_STRICT", "1").strip() not in ("0", "false", "no")


def _has_hant(canonical: str) -> bool:
    avail = _HANT_AVAIL.get()
    if avail is None or _is_hant():
        return True
    rel = _alternates(canonical)[0][len(settings.site_url) + 1:] if canonical else ""
    return (rel or "index.html") in avail


def _base() -> str:
    """当前字形的站点根地址(不带结尾斜杠):简体 https://…,繁体 https://…/zh-hant。"""
    return settings.site_url + (f"/{HANT_DIR}" if _is_hant() else "")


def _home() -> str:
    return _base() + "/"


def _lang() -> str:
    """结构化数据的 inLanguage / <html lang>。"""
    return "zh-Hant" if _is_hant() else "zh-CN"


def _og_image() -> str:
    return OG_IMAGE_HANT if _is_hant() else OG_IMAGE


def _root(up: str) -> str:
    """资源文件(css / js / favicon / assets)与 data-base 的前缀:繁体页比站内链接多退一级。"""
    if not _is_hant():
        return up
    return "/" if up.startswith("/") else up + "../"


def _alternates(canonical: str) -> tuple[str, str]:
    """canonical → (简体地址, 繁体地址)。两边目录结构相同,只差 /zh-hant 前缀。"""
    site = settings.site_url
    rel = canonical[len(_base()):] if canonical.startswith(_base()) else canonical[len(site):]
    return site + rel, f"{site}/{HANT_DIR}" + rel


def hreflang_links(canonical: str) -> str:
    """简繁互指 + x-default(指简体)。两种字形的页面上写的完全一样。没有对应繁体页时返回空串。"""
    if not _has_hant(canonical):
        return ""
    hans, hant = _alternates(canonical)
    return (f'<link rel="alternate" hreflang="zh-Hans" href="{e(hans)}">\n'
            f'<link rel="alternate" hreflang="zh-Hant" href="{e(hant)}">\n'
            f'<link rel="alternate" hreflang="x-default" href="{e(hans)}">')


def BACK_HOME() -> str:  # noqa: N802
    """落地页、指南页末尾回首页的链接文字。繁体首页是静态门户页,没有检索与图表,不能照抄简体的说法。"""
    return "← 返回政策脉络首页" if _is_hant() else "← 返回政策脉络首页(检索、趋势、七维分析)"


def lang_switch(up: str, canonical: str = "") -> str:
    """页头的字形切换链接,指向同一页的另一种字形。标签不经转换器(「简体中文」要保持简体)。"""
    from .hant import keep
    if not _has_hant(canonical):
        return ""
    if canonical:
        rel = _alternates(canonical)[0][len(settings.site_url):]       # /p/x.html
        href = (_root(up) + rel[1:]) if _is_hant() else f"{up}{HANT_DIR}{rel}"
    else:                                                              # 404 页:回另一种字形的首页
        href = "/" if _is_hant() else f"/{HANT_DIR}/"
    if _is_hant():
        return (f'<a class="lang-switch" href="{e(href)}" hreflang="zh-Hans" lang="zh-Hans">'
                f'{keep("简体中文")}</a>')
    return f'<a class="lang-switch" href="{e(href)}" hreflang="zh-Hant" lang="zh-Hant">繁體中文</a>'


def clip(text: str, n: int = 150) -> str:
    """搜索结果里的描述:不超过 n 字,尽量停在句末;停不了就停在逗号处并加省略号。
    原先一律砍到第 150 个字,七成页面的描述断在半句话上。"""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= n:
        return t
    cut = t[:n]
    end = max(cut.rfind(c) for c in "。；！？!?;")
    if end >= n * 0.55:
        return cut[:end + 1]
    soft = max(cut[:n - 1].rfind(c) for c in "，,、：:")
    return (cut[:soft] if soft >= n * 0.55 else cut[:n - 1]) + "…"


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
    return f"{_base()}/p/{slug(uid)}.html"


def seo_config() -> dict:
    return json.loads(SEO_CONFIG.read_text(encoding="utf-8")) if SEO_CONFIG.exists() else {}


def _ld(obj: dict) -> str:
    # </ 转义:摘要里万一出现 </script> 也不会提前结束脚本块
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>")


def _head(title: str, desc: str, canonical: str, jsonld: list[dict] | dict | None = None,
          up: str = "../", robots: str = ROBOTS_INDEX, og_type: str = "website", extra: str = "") -> str:
    """extra:追加到 <head> 的标签(如本领域的订阅地址),调用方负责转义。"""
    lds = jsonld if isinstance(jsonld, list) else ([jsonld] if jsonld else [])
    ld = "\n".join(x for x in [extra, *(_ld(x) for x in lds)] if x)
    img = f"{settings.site_url}/{_og_image()}"
    root = _root(up)
    canon = "\n".join(x for x in (f'<link rel="canonical" href="{e(canonical)}">', hreflang_links(canonical),
                                   f'<meta property="og:url" content="{e(canonical)}">') if x) if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="{"zh-Hant" if _is_hant() else "zh-CN"}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
{canon}
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" title="{SITE_NAME} · 最新政策" href="{up}feed.xml">
<meta property="og:type" content="{og_type}">
<meta property="og:locale" content="{"zh_TW" if _is_hant() else "zh_CN"}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{OG_ALT}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{e(img)}">
<link rel="stylesheet" href="{root}css/main.css">
{ld}
</head>
<body>
<header>
  <div class="brand"><a href="{up}index.html" style="display:flex;align-items:center;gap:14px;color:inherit;text-decoration:none">
    <div class="seal">脉</div><div class="brand-name">{SITE_NAME}</div></a>
    <div class="brand-sub">Thai Policy Lineage · นโยบายไทย</div></div>
  <div class="header-right">{lang_switch(up, canonical)}<a class="hdr-all" href="{up}p/index.html" style="color:inherit">全部政策</a>
    <button class="btn-solid" data-support-button hidden>☕ 打赏支持</button></div>
</header>
<main style="max-width:880px;margin:0 auto;padding:32px 20px">"""


def _foot(up: str = "../") -> str:
    root = _root(up)
    return f"""</main>
<footer>{SITE_NAME} —— 官方源自动监测 · 全部内容可溯源 · 零带货中立平台。
本站译文均为非官方翻译,仅供参考,以泰文原文为准;不构成法律意见。
<a href="{up}about.html">关于本站与数据来源</a> · <a href="{up}{GUIDE_PATH}">泰国皇家公报指南</a> ·
<a href="{up}p/index.html">全部政策</a> · <a href="{up}feed.xml">RSS 订阅</a> · <a href="{up}privacy.html">隐私政策</a></footer>
<script src="{root}js/track.js" data-base="{root}"></script>
<script src="{root}js/ads.js" data-base="{root}"></script>
<script src="{root}js/vendor/qrcode-generator-1.4.4.js"></script>
<script src="{root}js/promptpay.js"></script>
<script src="{root}js/support.js" data-base="{root}"></script>
</body>
</html>
"""



def _crumbs_ld(trail: list[tuple[str, str]]) -> dict:
    """BreadcrumbList 结构化数据:trail = [(名称, 地址)…],首页与「全部政策」自动加在前面。
    只用在页面上看得见面包屑的页(与可见内容一致);搜索结果里显示的是路径名而不是一串网址。"""
    full = [("首页", _home()), ("全部政策", f"{_base()}/p/index.html"), *trail]
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                for i, (n, u) in enumerate(full)]}


def _field(k: str, v) -> str:
    return (f'<div class="field"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
            if v else "")


def page_title(t: str, tag: str = "", lead: str = "") -> str:
    """搜索结果标题约显示 30 个汉字;公报标题常常很长,截短并用短后缀,总长控制在 56 字以内。
    tag:标题与别的页面完全相同时(同名系列)附上日期,否则搜索结果里分不出是哪一份。
    lead:写在最前面的限定语(见 title_lead),算在总长之内。"""
    t = re.sub(r"\s+", " ", t or "").strip()
    tag = f"({tag})" if tag else ""
    room = 48 - len(tag) - len(lead)
    return lead + (t if len(t) <= room else t[:room - 1] + "…") + tag + " | 泰国政策"


def title_lead(title_zh: str, cabinet_resolution: bool = False) -> str:
    """<title> 最前面的「泰国」。公报标题是「工业部公告:…」「土地厅公告:…」这样的写法,九成不含「泰国」二字,
    而搜索结果只显示标题的前 30 个字左右,结尾的「| 泰国政策」几乎都被截掉 —— 搜索的人看不出这是哪国的规定。
    内阁决议的标题多是「关于……的措施」,前面写明「泰国内阁决议:」。标题本身以「泰国」开头的不重复加。
    只改 <title>(以及随它的 og:title);页面上的 H1 仍是标题原样。"""
    t = (title_zh or "").strip()
    if cabinet_resolution and not t.startswith(("内阁决议", "泰国内阁")):
        return "泰国内阁决议:"
    if t.startswith(("泰国", "泰王国")):
        return ""
    return "泰国 " if t[:1].isascii() and t[:1].isalnum() else "泰国"


def topic_url(dom_id: str) -> str:
    return f"{_base()}/p/topic/{dom_id}.html"


def _status(v: dict) -> str:
    """落地页上的状态:「01-01 起施行」补上年份。首页卡片挨着日期看得懂,单独被引用时分不清是哪一年。"""
    eff = v["dates"].get("effective_from")
    return f"{eff} 起施行" if eff and v["status_label"].endswith("起施行") else v["status_label"]


# 早先的要点清洗把开头的数字一律当成列表序号删掉(app.enrich.strip_list_marker 已改正,新条目不再出错):
# 「2026年7月1日及以后建造的船舶须……」成了「年7月1日及以后建造的船舶须……」,「7号线涵盖……」成了「号线涵盖……」。
# 事实层里已有的这几十条要等重新整理才能恢复;在那之前,页面上不展示这种开头明显缺字的要点 ——
# 缺了年份的日期被 AI 引用出去就是一条错误信息。摘要不受影响。只认不可能是句子开头的写法,「年利率」「月均」这类照常显示
_CLIPPED_POINT_RE = re.compile(r"^(?:[年月]\s?\d|号线|级(?:包括|[:\uff1a])|个月)")


def sound_points(points: list[str]) -> list[str]:
    return [p for p in points or [] if not _CLIPPED_POINT_RE.match(p)]


def book(title: str) -> str:
    """给标题加书名号。标题里已有书名号时内层改用单书名号:《〈清迈倡议多边化协议〉修订版草案》,
    而不是《《清迈倡议多边化协议》修订版草案》。"""
    t = str(title or "")
    return "《" + (t.replace("《", "〈").replace("》", "〉") if "《" in t or "》" in t else t) + "》"


def is_cabinet_resolution(doc: Document) -> bool:
    """内阁决议条目:只有决议日,没有公报卷期,也没有发布日。"""
    return bool(doc.resolved_at) and not doc.published_at and not doc.gazette_series


def agency_th_names() -> dict[str, list[str]]:
    """词表里各机关的泰文名与别名 {id: [名称…]}(与 app.enrich.agency_rules 同一口径:4 个字符以下的缩写不用)。
    词表里写的是「某某委员会办公室」(สำนักงานคณะกรรมการ…)的,委员会本身(คณะกรรมการ…)发的公告也算它的 ——
    BOI 在词表里是办公室的泰文名,而公报上的「投资促进委员会公告」署的是委员会。"""
    try:
        vocab = json.loads((DATA_DIR / "vocab.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[str]] = {}
    for a in vocab.get("agencies") or []:
        names = [n for n in [a.get("th") or "", *(a.get("th_aliases") or [])] if len(n) >= 4]
        names += [n[len("สำนักงาน"):] for n in names if n.startswith("สำนักงานคณะกรรมการ")]
        out[a["id"]] = list(dict.fromkeys(names))
    return out


def issuer_info(doc: Document, org: str, th_names: dict[str, list[str]]) -> tuple[str, str]:
    """落地页上「机关」一栏的 (标签, 名称)。标签是「发文机关」时,开头那句话和结构化数据才把它写成发文者。

    数据里的机关是模型从词表里选的:词表没有的机关(宪法法院、商品与服务安全委员会、疾病控制厅……)
    会被归到上级部委,或者落到缺省值「内阁」。原样写成「内阁于某日在皇家公报刊登《宪法法院裁决……》」
    就是一句错话,而开头这句正是 AI 最常引用的。所以只在有依据时才说是谁发的:
    - 公报条目:泰文原题的发文机关段(「เรื่อง」之前)里出现了该机关的泰文名;没有泰文原题的(人工整理的条目)照旧。
    - 官网来源的条目:第一个机关就是这个官网的机关(uid 的第二段,如 TH-BOI-…、TH-RD-…),或泰文原题印证。
    - 内阁决议:第一个机关是内阁。
    - 人工复核过的条目照旧。
    印证不了的:标签改为「相关机关」(本站归类,不等于发文者);只有一个缺省的「内阁」时整栏不显示。"""
    ids = [a.agency_id for a in sorted(doc.agencies, key=lambda x: x.seq)]
    if not ids or not org:
        return "发文机关", org
    head = re.split(r"เรื่อง|ว่าด้วย", doc.title_th or "")[0][:160].strip()
    named = bool(head) and any(n in head for i in ids for n in th_names.get(i, ()))
    if doc.verified or named:
        ok = True
    elif is_cabinet_resolution(doc):
        ok = ids[0] == "cabinet"
    elif doc.gazette_series:
        ok = not head
    else:
        ok = ids[0] == _uid_agency(doc.uid) or (not head and ids[0] != "cabinet")
    if ok:
        return "发文机关", org
    return ("", "") if ids == ["cabinet"] else ("相关机关", org)


def _uid_agency(uid: str) -> str:
    """uid 的第二段(TH-<机关>-<日期>-…):官网来源的条目,这一段就是来源网站所属的机关。"""
    parts = str(uid or "").split("-")
    return parts[1].lower() if len(parts) > 2 else ""


def source_site(doc: Document, agencies_zh: dict[str, str]) -> str:
    """官网来源的条目:原文所在官网属于哪个机关(中文名)。由 uid 的机关段与原文链接的域名互相印证,
    对不上就返回空串。只用于「在某某官网发布」这句话。"""
    aid = _uid_agency(doc.uid)
    if doc.gazette_series or aid not in agencies_zh:
        return ""
    hosts = [re.sub(r"^https?://([^/:]+).*$", r"\1", x.url or "") for x in doc.sources if x.role == "official"]
    return agencies_zh[aid] if any(h == f"{aid}.go.th" or h.endswith(f".{aid}.go.th") for h in hosts) else ""


def legal_force(doc: Document, today) -> str | None:
    """结构化数据的 legislationLegalForce。原先只看状态词表的 in_force,「已刊公报」一律写成 NotInForce ——
    而页面正文写着「某日起生效」。按页面上看得见的事实来:
    已被替代 / 废止 / 失效,或过了失效日 → NotInForce;现行有效 → InForce;
    已刊公报:生效日已到 → InForce,生效日未到 → NotInForce,没有生效日 → 不声明;
    草案、待刊公报 → NotInForce。"""
    if doc.status_id in ("superseded", "repealed", "expired") or (doc.effective_to and doc.effective_to < today):
        return "NotInForce"
    if doc.status.in_force:
        return "InForce"
    if doc.status_id == "gazetted":
        if not doc.effective_from:
            return None
        return "InForce" if doc.effective_from <= today else "NotInForce"
    return "NotInForce"


def _lede(v: dict, gazetted: bool = True, issuer: bool = True, site: str = "") -> str:
    """一句话结论:谁、何时、发布了什么、现在什么状态。AI 摘答时最常直接引用开头这一句,
    所以每个成分都要是本站核对过的事实。
    gazetted=False:条目来自发文机关官网(税务厅、BOI 等),日期是官网发布日,没有公报卷期 ——
    不能写成「在皇家公报刊登」。
    issuer=False:机关一栏印证不了是发文者(见 issuer_info)—— 不拿它当主语,改用「《……》于某日刊登 / 发布」;
    site 是原文所在官网的机关名,有它就写「在某某官网发布」。
    内阁决议:只说「内阁就《……》作出决议」。决议可能是批准,也可能只是听取报告或交办,
    没读过决议正文的条目不能一律写成「通过」。"""
    d = v["dates"]
    who = v["org"] if issuer else ""
    sep = " " if who[-1:].isascii() else ""
    title = book(v["title_zh"])
    no = f"({v['doc_no_label']} {v['doc_no']})" if v["doc_no"] else ""
    eff = f",{d['effective_from']} 起生效" if d.get("effective_from") else ""
    if d.get("published_at") and not gazetted:
        if who:
            what = f"{who}{sep}于 {d['published_at']} 发布{title}{no}"
        else:
            what = f"{title}{no}于 {d['published_at']} " + (f"在{site}官网发布" if site else "发布")
    elif d.get("published_at"):
        what = (f"{who}{sep}于 {d['published_at']} 在泰国皇家公报刊登{title}{no}" if who
                else f"{title}{no}于 {d['published_at']} 在泰国皇家公报刊登")
    elif d.get("resolved_at"):
        what = f"泰国内阁于 {d['resolved_at']} 就{title}作出决议{no}"
    else:
        who = who or "泰国政府"
        what = f"{who}{' ' if who[-1:].isascii() else ''}发布{title}{no}"
    return f"{what}{eff}。当前状态:{_status(v)}。"


def render_page(s: Session, doc: Document, today, titles: dict[str, str],
                dom: tuple[str, str] = ("", ""), related: list[tuple[str, str, str]] = (),
                series: list[tuple[str, str, str]] = (),
                collections: list[tuple[str, str]] = (), dup_title: bool = False,
                view: dict | None = None, issuer: tuple[str, str] | None = None, site: str = "") -> str:
    """dom = (领域 id, 领域中文名);related = 同领域相邻政策 [(uid, 日期, 标题)],做站内链接;
    series = 同一标题先后刊登的其他文件 [(uid, 日期, 标题)],按日期排列;
    collections = 收录本条的汇总页 [(相对 p/ 的地址, 名称)],专题页与影响对象页靠它拿到内链;
    dup_title = 还有别的条目与本条中文标题完全相同,<title> 要带上日期区分;
    view = 已算好的 A.document_view(简繁两遍渲染共用一份,省一半查询);
    issuer = issuer_info 的结果 (机关一栏的标签, 名称),site = source_site 的结果;不传就现算。"""
    v = view or A.document_view(s, doc, today)
    d = v["dates"]
    # 有公报卷期才说「刊登公报」;部门官网来源的条目,日期是官网发布日
    gazetted = bool(doc.gazette_series)
    org_label, org = issuer if issuer is not None else issuer_info(doc, v["org"], agency_th_names())
    is_issuer = org_label == "发文机关"
    points = sound_points(v["key_points"])
    lede = _lede(v, gazetted, is_issuer, site)
    title = page_title(v["title_zh"], v["date"] if dup_title else "",
                       title_lead(v["title_zh"], is_cabinet_resolution(doc)))
    desc = v["summary_zh"] or v["title_zh"]
    if len(desc) < 80:                 # 摘要太短(搜索结果里几乎没信息),补上一句话结论
        desc = f"{desc} {lede}".strip()
    desc = clip(desc)
    canonical = page_url(doc.uid)

    rels = "".join(
        f'<li>{e(REL_ZH.get(r.type, r.type))}:'
        f'<a href="{e(slug(r.dst_uid))}.html">{e(titles.get(r.dst_uid, r.dst_uid))}</a></li>'
        for r in doc.relations_out if r.dst_uid in titles)
    near = "".join(f'<li><a href="{e(slug(u))}.html">{e(t)}</a> <span class="lib-date">{e(dt)}</span></li>'
                   for u, dt, t in related)
    colls = " · ".join(f'<a href="{e(h)}">{e(n)}</a>' for h, n in collections)
    same = "".join(f'<li><a href="{e(slug(u))}.html">{e(t)}</a> <span class="lib-date">{e(dt)}</span></li>'
                   for u, dt, t in series)
    # 能生成落地页的都已有官方原文(入库规则保证),这里只负责列出原文与公报卷期
    official = [x for x in doc.sources if x.role == "official" and x.url]
    cite = f"{v['doc_no_label']} {v['doc_no']} · " if v["doc_no"] else ""
    # 官方原文是本页的出处,不加 nofollow:nofollow 是给不愿背书的链接用的
    links = " · ".join(f'<a href="{e(x.url)}" rel="noopener" target="_blank">{e(x.url)}</a>'
                       for x in official)
    origin = "泰文原文(官方):" + cite + links

    timeline = [(d.get("resolved_at"), "内阁决议"), (d.get("comment_deadline"), "征求意见截止"),
                (d.get("published_at"), "刊登皇家公报" if gazetted else ("发文机关发布" if is_issuer else "官网发布")),
                (d.get("effective_from"), "生效"),
                (d.get("effective_to"), "失效")]
    timeline = sorted([t for t in timeline if t[0]])
    tl = "".join(f'<div class="tl-item done"><div class="tl-date">{e(t[0])}</div>'
                 f'<div class="tl-name">{e(t[1])}</div></div>' for t in timeline)

    when = " / ".join(f"{n} {dt}" for dt, n in timeline) or "—"
    facts = [("是什么", v["title_zh"]), (org_label, org),
             (v["doc_no_label"], v["doc_no"]), ("关键日期", when), ("当前状态", _status(v)),
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
        "legislationLegalForce": legal_force(doc, today),
        # 只在机关确是发文者时才声明(见 issuer_info);印证不了的不写
        "legislationPassedBy": ({"@type": "GovernmentOrganization", "name": org}
                                if is_issuer and org else None),
        "datePublished": v["date"] or None,
        "inLanguage": _lang(), "url": canonical, "abstract": v["summary_zh"],
        "about": dom[1] or None,
        "isAccessibleForFree": True,
        # 本页是泰文原文的中文译述:指明原作,方便搜索与 AI 引擎追溯到官方来源
        "translationOfWork": ({"@type": "Legislation", "name": v["title_th"] or v["title_zh"],
                               "inLanguage": "th", "url": first_official} if first_official else None),
        "isBasedOn": first_official or None,
        # 与首页的 Organization / WebSite 用同一个 @id,搜索引擎把各页归到同一个站点实体
        "publisher": {"@type": "Organization", "@id": f"{settings.site_url}/#org", "name": SITE_NAME,
                      "url": f"{settings.site_url}/"},
        "isPartOf": {"@type": "WebSite", "@id": f"{_home()}#website", "name": SITE_NAME,
                     "url": _home()},
        "mainEntityOfPage": canonical,
    }
    legislation = {k: val for k, val in legislation.items() if val}
    crumbs = [("首页", _home()), ("全部政策", f"{_base()}/p/index.html")]
    if dom[0]:
        crumbs.append((dom[1], topic_url(dom[0])))
    crumbs.append((v["title_zh"], canonical))
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList",
                  "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                      for i, (n, u) in enumerate(crumbs)]}

    crumb_html = '<a href="index.html">全部政策</a>' + (
        f' / <a href="topic/{e(dom[0])}.html">{e(dom[1])}</a>' if dom[0] else "") + f" / {e(v['legal_form'])}"
    citation = (f"{book(v['title_zh'])}中文摘要,{SITE_NAME},{canonical}"
                + (f"(泰文原文:{first_official})" if first_official else ""))

    body = f"""
<div class="crumb">{crumb_html}</div>
<article class="card" style="padding:26px 30px">
  <div class="pc-top"><span class="chip {e(v['domain'])}">{e(v['domain_label'])}</span>
    <span class="dir {e(v['direction'])}">{e(DIR_ZH.get(v['direction'], ''))}</span>
    {'<span class="verified">已人工复核</span>' if v['verified'] else ''}</div>
  <h1 class="d-title">{e(v['title_zh'])}</h1>
  {f'<div class="d-thai" lang="th">泰文原题:{e(v["title_th"])}</div>' if v['title_th'] else ''}
  <p class="lede">{e(lede)}</p>
  <div class="fields">
    {_field(org_label, org)}{_field(v['doc_no_label'], v['doc_no'])}
    {_field('内阁决议日', d.get('resolved_at'))}{_field('刊登公报日' if gazetted else '发布日', d.get('published_at'))}
    {_field('生效日', d.get('effective_from'))}{_field('状态', _status(v))}
    {_field('法律层级', v['legal_form'])}{_field('稳定性', f"{v['stability']} / 5")}
  </div>
  <div class="d-body">
    <h2 style="font-size:15px">中文摘要</h2><p>{e(v['summary_zh'])}</p>
    {('<h2 style="font-size:15px">正文要点</h2><ul class="points">' + "".join(f"<li>{e(k)}</li>" for k in points) + "</ul>") if points else ""}
    <h2 style="font-size:15px">要点速览</h2><dl class="facts">{facts_html}</dl>
    {f'<h2 style="font-size:15px">生命周期</h2><div class="timeline">{tl}</div>' if tl else ''}
    {f'<h2 style="font-size:15px">关联文件</h2><ul>{rels}</ul>' if rels else ''}
    {f'<p class="in-colls"><b>收录于汇总页</b> {colls}</p>' if colls else ''}
  </div>
  <div class="origin">{origin}<br>字段可信度:日期 {e(CONF_ZH.get(v['confidence']['dates'], ''))}
    · 文号 {e(CONF_ZH.get(v['confidence']['doc_no'], ''))}</div>
  <div class="cite">引用本页:{e(citation)}</div>
  <div class="disclaim">免责声明:本页为非官方翻译,仅供参考,如与泰文原文有出入,以泰文原文为准;
    本内容不构成法律或税务意见。本站与泰国政府无隶属关系。</div>
</article>
{f'<section class="related"><h2 class="mod">同名系列</h2><p class="lib-date">同一机关以同一标题先后刊登的文件;后一份是否取代前一份,以各份原文为准。</p><ul>{same}</ul></section>{chr(10)}' if same else ''}{f'<section class="related"><h2 class="mod">同领域政策 · {e(dom[1])}</h2><ul>{near}</ul><a href="topic/{e(dom[0])}.html">查看{e(dom[1])}全部政策 →</a></section>' if near else ''}
<div class="support-slot"></div>
<div class="ad-slot" data-slot="landing_bottom" style="margin-top:18px"></div>
<p style="margin-top:18px"><a href="../index.html">{BACK_HOME()}</a></p>
"""
    return _head(title, desc, canonical, [legislation, breadcrumb], og_type="article") + body + _foot()


def _rows_html(items, up: str = "") -> str:
    return "".join(f'<div class="lib-row"><span class="lib-date">{e(dt)}</span>'
                   f'<div class="lib-title"><a href="{up}{e(slug(uid))}.html">{e(t)}</a></div></div>'
                   for dt, uid, t in items)


def render_index(rows: list[tuple[str, str, str, str]], topics: list[tuple[str, str, int]] = (),
                 collections: list[dict] = (), who: list[dict] = ()) -> str:
    """rows: (领域中文名, 日期, uid, 标题),已按日期倒序。按领域分组的纯 HTML 目录,给爬虫一个入口。"""
    groups: dict[str, list] = {}
    for dom, date, uid, title in rows:
        groups.setdefault(dom, []).append((date, uid, title))
    nav = " · ".join(f'<a href="topic/{e(i)}.html">{e(zh)}({n})</a>' for i, zh, n in topics)
    coll = " · ".join(f'<a href="{e(x["href"][2:])}">{e(x["zh"])}({x["n"]})</a>' for x in collections)
    whos = " · ".join(f'<a href="{e(x["href"][2:])}">{e(x["zh"])}({x["n"]})</a>' for x in who)
    body = ('<h1 class="page">全部政策</h1><div class="page-sub">按领域分组 · 每条均附泰文原文(官方)溯源'
            + (f"<br>按领域浏览:{nav}" if nav else "")
            + (f"<br>专题汇总:{coll}" if coll else "")
            + (f"<br>按影响对象:{whos}" if whos else "")
            + '<br><a href="week/index.html">按周汇总</a> · <a href="guide/royal-gazette.html">泰国皇家公报指南</a></div>')
    for dom in sorted(groups):
        body += f'<h2 class="mod" style="margin-top:24px">{e(dom)}</h2><div class="lib-wrap">{_rows_html(groups[dom])}</div>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "全部政策",
          "url": f"{_base()}/p/index.html", "inLanguage": _lang(),
          "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _home()}}
    return (_head("泰国政策中文目录:皇家公报、内阁决议全部条目 | 政策脉络",
                  f"泰国皇家公报、内阁决议与各部委政策的中文目录,共 {len(rows)} 条,按签证、税务、劳工、"
                  "海关贸易等领域分组;每条附泰文原文(泰国政府网站)链接,非官方翻译。",
                  f"{_base()}/p/index.html", ld) + body + _foot())


# 各领域收什么:与 about.html 的「领域说明」同一口径。领域页的开场白用它,
# 搜「泰国 个人所得税 / 工作许可 / 公寓」这类具体词的人才知道这一页管不管用
DOMAIN_SCOPE = {
    "visa": "签证、居留许可、入境与停留规定",
    "tax": "个人所得税、企业所得税、增值税、消费税等税费",
    "biz": "公司设立、外资准入、投资促进(BOI)与营商规则",
    "labor": "工作许可、最低工资、社会保险与用工规定",
    "land": "土地、公寓、建筑与城市规划",
    "customs": "进出口管制、配额、关税与贸易救济",
    "finance": "银行、证券、保险、外汇与支付",
    "digital": "个人资料保护(PDPA)、电子交易与数字平台",
    "education": "学校、学历与留学相关规定",
    "health": "药品、食品、医疗器械、医疗服务与卫生管理",
}
TOPIC_LATEST = 10           # 领域页开头带摘要展示的最新条数


def _item_card(x: dict, up: str = "../", tag: str = "h2", points: int = 3, lead: str = "",
               sub: str = "") -> str:
    """汇总页里的一条:日期 · 机关 · 编号 / 标题 / 摘要 / 要点 / 泰文原文链接。
    lead 是标题前的标记(已转义的 HTML),sub 覆盖第一行的说明(已转义的 HTML)。"""
    pts = "".join(f"<li>{e(k)}</li>" for k in x["points"][:points])
    head = sub or " · ".join(e(t) for t in (x["date"] or "—", x["org"], x["doc_no"]) if t)
    return (f'<div class="coll-item"><div class="lib-sub">{head}</div>'
            f'<{tag} class="coll-title">{lead}<a href="{up}{e(slug(x["uid"]))}.html">{e(x["title"])}</a></{tag}>'
            f'<p>{e(x["summary"])}</p>' + (f'<ul class="points">{pts}</ul>' if pts else "")
            + (f'<div class="lib-sub"><a href="{e(x["official"])}" rel="noopener" target="_blank">泰文原文 ↗</a></div>'
               if x["official"] else "") + "</div>")


def render_topic(dom_id: str, zh: str, en: str, items: list[dict],
                 colls: list[tuple[str, str]] = (), others: list[tuple[str, str, int]] = ()) -> str:
    """领域专题页:某一领域的全部政策。长尾词「泰国 + 领域 + 政策」的落地页。
    items 是该领域的条目(已按日期倒序);colls = 与本领域相关的汇总页 [(相对 p/ 的地址, 名称)];
    others = 其他领域 [(id, 中文名, 条数)]。
    开头是最新几条的摘要与原文链接 —— 搜索引擎和 AI 抓到这一页就能回答「泰国××最近出了什么政策」;
    后面才是按年份分组的完整目录。原先整页只有日期和标题,读不出任何内容。"""
    url = topic_url(dom_id)
    dates = [x["date"] for x in items if x["date"]]
    latest, oldest = (max(dates), min(dates)) if dates else ("", "")
    scope = DOMAIN_SCOPE.get(dom_id, "")
    title = f"泰国{zh}政策汇总(中文" + (f",更新至 {latest[:7]}" if latest else "") + f") | {SITE_NAME}"
    desc = clip(f"泰国{zh}({en})政策中文汇总" + (f":{scope}" if scope else "") + f"。共 {len(items)} 条皇家公报、内阁决议与部委公告"
                + (f",收录至 {latest}" if latest else "") + ",每条附中文摘要与泰文原文(官方)链接。")
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"泰国{zh}政策",
           "url": url, "inLanguage": _lang(), "about": zh, "description": desc,
           **({"dateModified": latest} if latest else {}),
           "isPartOf": {"@type": "WebSite", "@id": f"{_home()}#website", "name": SITE_NAME,
                        "url": _home()},
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                          "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                               "url": x["url"], "name": x["title"]}
                                              for i, x in enumerate(items[:50])]}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList",
           "itemListElement": [
               {"@type": "ListItem", "position": 1, "name": "首页", "item": _home()},
               {"@type": "ListItem", "position": 2, "name": "全部政策", "item": f"{_base()}/p/index.html"},
               {"@type": "ListItem", "position": 3, "name": zh, "item": url}]}]
    intro = (f"收录泰国{e(zh)}({e(en)})相关的皇家公报、内阁决议与部委公告"
             + (f",范围包括{e(scope)}" if scope else "") + f"。共 <b>{len(items)}</b> 条"
             + (f",日期从 {e(oldest)} 到 {e(latest)}" if latest else "")
             + "。每条有中文摘要并附泰国政府网站上的泰文原文链接;译文为非官方翻译,以泰文原文为准。"
             + f'<br><a href="../../feed/{e(dom_id)}.xml">用 RSS 订阅本领域更新</a>')
    head_items = items[:TOPIC_LATEST]
    body = (f'<div class="crumb"><a href="../index.html">全部政策</a> / {e(zh)}</div>'
            f'<h1 class="page">泰国{e(zh)}政策</h1>'
            f'<div class="page-sub">{intro}</div>'
            f'<h2 class="mod sec">最新收录</h2>'
            + "".join(_item_card(x, "../", tag="h3") for x in head_items))
    if len(items) > len(head_items):
        by_year: dict[str, list] = {}
        for x in items:
            by_year.setdefault(x["date"][:4] or "日期不详", []).append((x["date"], x["uid"], x["title"]))
        years = sorted(by_year, reverse=True)
        jump = " · ".join(f'<a href="#y{e(y)}">{e(y)} 年({len(by_year[y])})</a>' for y in years)
        body += (f'<h2 class="mod sec">全部{e(zh)}政策({len(items)} 条)</h2>'
                 + (f'<div class="mod-sub">按年份:{jump}</div>' if len(years) > 1 else ""))
        for y in years:
            body += (f'<h3 class="mod yr" id="y{e(y)}">{e(y)} 年 · {len(by_year[y])} 条</h3>'
                     f'<div class="lib-wrap">{_rows_html(by_year[y], "../")}</div>')
    rel = " · ".join(f'<a href="../{e(h)}">{e(n)}</a>' for h, n in colls)
    oth = " · ".join(f'<a href="{e(i)}.html">{e(n)}({c})</a>' for i, n, c in others)
    body += ('<nav class="coll-related">' + (f"<div><b>相关专题</b> {rel}</div>" if rel else "")
             + (f"<div><b>其他领域</b> {oth}</div>" if oth else "")
             + '<div><a href="../week/index.html">按周汇总</a> · <a href="../index.html">全部政策</a> · '
               '<a href="../guide/royal-gazette.html">泰国皇家公报指南</a></div></nav>')
    feed = (f'<link rel="alternate" type="application/atom+xml" title="{SITE_NAME} · {e(zh)}" '
            f'href="../../feed/{e(dom_id)}.xml">')
    return _head(title, desc, url, ld, up="../../", extra=feed) + body + _foot("../../")


# ───────────────────── 专题汇总:影响对象页 p/who/、配置专题 p/t/ ─────────────────────

STANCE_ZH = {"constrain": "约束", "support": "利好", "neutral": ""}


def th_title_matches(title_th: str, match: dict) -> bool:
    """泰文标题按正则匹配(title_th_patterns 任一命中,且 title_th_exclude 都不命中)。
    采集环节回填专题(collect --backfill-topic)用的也是这一条规则。"""
    pats = match.get("title_th_patterns") or []
    if not any(re.search(p, title_th or "") for p in pats):
        return False
    return not any(re.search(p, title_th or "") for p in match.get("title_th_exclude") or [])


def topic_matches(x: dict, match: dict) -> bool:
    """配置专题的匹配规则:中文标题含任一关键词、泰文标题命中正则,或 uid 在名单里;再与领域 / 影响对象取交集。"""
    kws = match.get("title_keywords") or []
    uids = set(match.get("uids") or [])
    if not (any(k and k in x["title"] for k in kws) or x["uid"] in uids
            or th_title_matches(x.get("title_th", ""), match)):
        return False
    if match.get("domains") and x["domain_id"] not in match["domains"]:
        return False
    if match.get("parties") and not ({p["id"] for p in x["parties"]} & set(match["parties"])):
        return False
    return True


COLL_LATEST = 20            # 专题页 / 影响对象页开头带摘要展示的最新条数
COLL_KEEP_WHOLE = 5         # 只比上面多出这么几条以内就整页都带摘要,不为三五条另起一个目录


def render_collection(url: str, title: str, h1: str, scope: str, items: list[dict], crumb: str,
                      party: str | None = None, related: str = "", desc_lead: str = "") -> str:
    """汇编页:列出已收录条目的日期、机关、标题、摘要、要点与泰文原文链接。
    刻意不写任何综述 —— 页面上的每一句都来自某一条有官方原文的条目。

    条目多的页面(「影响外资企业」440 条、BOI 91 条)原先每一条都带摘要和要点,一页 580 KB、5100 个节点:
    手机上首屏要 2 秒多,AI 助手取页面时也只读得进开头一小段。现在与领域页同一结构 ——
    最新 COLL_LATEST 条带摘要与要点,更早的按年份列标题(连到各自的落地页,摘要在那里)。
    desc_lead:<meta description> 的开头,要带上「泰国」和主题词(搜索结果里先看到的是这一句)。"""
    items = sorted(items, key=lambda x: (x["date"] or "", x["uid"]), reverse=True)
    latest = items[0]["date"] if items else ""
    tail = f"共 {len(items)} 条" + (f",最新 {latest}" if latest else "") + ";每条附中文摘要与泰文原文链接。"
    desc = clip(f"{desc_lead}{scope}{tail}" if desc_lead else f"{scope} {tail}")

    def stance_of(x: dict) -> str:
        if not party:
            return ""
        st = next((p["stance"] for p in x["parties"] if p["id"] == party), "")
        return f'<span class="party {e(st)}">{e(STANCE_ZH.get(st, ""))}</span> ' if STANCE_ZH.get(st) else ""

    split = len(items) > COLL_LATEST + COLL_KEEP_WHOLE
    head_items, rest = (items[:COLL_LATEST], items[COLL_LATEST:]) if split else (items, [])
    cards = "".join(_item_card(x, "../", tag="h3" if split else "h2", lead=stance_of(x)) for x in head_items)
    older = ""
    if rest:
        by_year: dict[str, list[dict]] = {}
        for x in rest:
            by_year.setdefault(x["date"][:4] or "日期不详", []).append(x)
        years = sorted(by_year, reverse=True)
        jump = " · ".join(f'<a href="#y{e(y)}">{e(y)} 年({len(by_year[y])})</a>' for y in years)
        older = (f'<h2 class="mod sec">更早的 {len(rest)} 条</h2>'
                 + (f'<div class="mod-sub">按年份:{jump}</div>' if len(years) > 1 else ""))
        for y in years:
            rows = "".join(f'<div class="lib-row"><span class="lib-date">{e(x["date"])}</span>'
                           f'<div class="lib-title">{stance_of(x)}<a href="../{e(slug(x["uid"]))}.html">{e(x["title"])}</a>'
                           f'</div></div>' for x in by_year[y])
            older += (f'<h3 class="mod yr" id="y{e(y)}">{e(y)} 年 · {len(by_year[y])} 条</h3>'
                      f'<div class="lib-wrap">{rows}</div>')
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": h1, "url": url,
           "inLanguage": _lang(), "description": scope, **({"dateModified": latest} if latest else {}),
           "isPartOf": {"@type": "WebSite", "@id": f"{_home()}#website", "name": SITE_NAME, "url": _home()},
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                          "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": x["url"],
                                               "name": x["title"]} for i, x in enumerate(items[:50])]}},
          _crumbs_ld([(crumb.split(" / ", 1)[-1], url)])]
    how = (f"先列最新 {len(head_items)} 条的中文摘要、要点与泰文原文链接,更早的 {len(rest)} 条按年份列出标题(点开可读摘要)"
           if rest else "以下逐条摘录本站已收录条目的中文摘要")
    body = (f'<div class="crumb"><a href="../index.html">全部政策</a> / {e(crumb)}</div>'
            f'<h1 class="page">{e(h1)}</h1>'
            f'<div class="page-sub">{e(scope)}<br>共 <b>{len(items)}</b> 条' + (f",最新 {e(latest)}" if latest else "")
            + f"。{how},一切以泰文原文为准。</div>"
            + (f'<h2 class="mod sec">最新 {len(head_items)} 条</h2>' if rest else "")
            + cards + older + related)
    return _head(title, desc, url, ld, up="../../") + body + _foot("../../")


def collection_pages(entries: list[dict], parties_zh: dict[str, str]) -> tuple[list[tuple], list[dict]]:
    """算出要生成的汇总页:影响对象页 p/who/ 与配置专题 p/t/。
    返回 (pages, index):pages = [(kind, id, 中文名, 条目, 专题配置)],index = [{kind, id, zh, n, href, date}]。"""
    pages = []          # (kind, id, zh, items, extra)
    for pid in sorted(parties_zh):
        items = [x for x in entries if any(p["id"] == pid for p in x["parties"])]
        if len(items) >= MIN_COLLECTION:
            pages.append(("who", pid, parties_zh[pid], items, None))
    cfg = json.loads(TOPICS_CONFIG.read_text(encoding="utf-8")) if TOPICS_CONFIG.exists() else {}
    for t in cfg.get("topics") or []:
        items = [x for x in entries if topic_matches(x, t.get("match") or {})]
        if len(items) >= MIN_COLLECTION:
            pages.append(("t", t["id"], t["title_zh"], items, t))
    index = [{"kind": k, "id": i, "zh": zh, "n": len(items), "href": f"p/{k}/{i}.html",
              "date": max((x["date"] for x in items if x["date"]), default="")} for k, i, zh, items, _ in pages]
    return pages, index


def render_collections(pages: list[tuple], index: list[dict]) -> dict[str, str]:
    """渲染全部汇总页,返回 {相对 p/ 的地址: html}。
    先算出全部页面再渲染:每页页尾互相链接(相关专题、按影响对象),给读者和爬虫多一条路。"""
    def related(kind: str, pid: str) -> str:
        links = lambda k: " · ".join(f'<a href="../{e(x["kind"])}/{e(x["id"])}.html">{e(x["zh"])}</a>'  # noqa: E731
                                     for x in index if x["kind"] == k and not (x["kind"] == kind and x["id"] == pid))
        t, w = links("t"), links("who")
        return ('<nav class="coll-related">' + (f"<div><b>相关专题</b> {t}</div>" if t else "")
                + (f"<div><b>按影响对象</b> {w}</div>" if w else "")
                + '<div><a href="../week/index.html">按周汇总</a> · <a href="../index.html">全部政策</a></div></nav>')

    out: dict[str, str] = {}
    for kind, pid, zh, items, t in pages:
        if kind == "who":
            html = render_collection(
                f"{_base()}/p/who/{pid}.html", f"影响{zh}的泰国政策汇总 | {SITE_NAME}",
                f"影响「{zh}」的泰国政策", f"收录本站标注为影响「{zh}」的公报与决议(含约束与利好)。",
                items, f"影响对象 / {zh}", party=pid, related=related(kind, pid),
                desc_lead=f"影响{zh}的泰国政策汇总:")
        else:
            html = render_collection(
                f"{_base()}/p/t/{pid}.html", f"泰国{zh}:历次公报汇总 | {SITE_NAME}",
                f"泰国{zh}:历次公报汇总", t["scope_zh"], items, f"专题 / {zh}", related=related(kind, pid),
                desc_lead=f"泰国{zh}:")
        out[f"{kind}/{pid}.html"] = html
    return out


def collection_members(pages: list[tuple]) -> dict[str, list[tuple[str, str]]]:
    """成员反查 {uid: [(相对 p/ 的地址, 名称)]},专题在前:落地页据此链回收录它的汇总页
    (否则汇总页只有首页和目录两处入口)。"""
    member_of: dict[str, list[tuple[str, str]]] = {}
    for kind, pid, zh, items, _ in sorted(pages, key=lambda x: x[0] != "t"):
        for x in items:
            member_of.setdefault(x["uid"], []).append(
                (f"{kind}/{pid}.html", zh if kind == "t" else f"影响{zh}"))
    return member_of


def _split_index(index: list[dict]) -> tuple[list[dict], list[dict]]:
    """index → (影响对象页, 专题页),各项 {id, zh, n, href, date}。"""
    strip = lambda x: {k: v for k, v in x.items() if k != "kind"}  # noqa: E731
    return [strip(x) for x in index if x["kind"] == "who"], [strip(x) for x in index if x["kind"] == "t"]


def build_collections(entries: list[dict], parties_zh: dict[str, str]
                      ) -> tuple[list[dict], list[dict], dict[str, list[tuple[str, str]]]]:
    """生成(简体)p/who/*.html 与 p/t/*.html,返回 (影响对象页, 专题页, 成员反查)。
    build() 自己分步调用上面三个函数(简繁各渲染一遍);这个包装留给单独生成汇总页的场合。"""
    pages, index = collection_pages(entries, parties_zh)
    for rel, html in render_collections(pages, index).items():
        (PAGES_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
        (PAGES_DIR / rel).write_text(html, encoding="utf-8")
    return (*_split_index(index), collection_members(pages))


def week_id(d: str) -> str:
    """YYYY-MM-DD → ISO 周编号 2026-W17(按公报刊登日分周,与采集时间无关,导出确定)。"""
    from datetime import date as _date
    y, w, _ = _date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def week_range(wid: str) -> tuple[str, str]:
    from datetime import date as _date
    y, w = wid.split("-W")
    mon = _date.fromisocalendar(int(y), int(w), 1)
    sun = _date.fromisocalendar(int(y), int(w), 7)
    return mon.isoformat(), sun.isoformat()


def render_week(wid: str, items: list[dict], prev_id: str | None, next_id: str | None) -> str:
    """某一周刊登或发布的全部政策(按条目日期分周)。逐条列标题、摘要与原文链接,不写综述。
    少于 MIN_COLLECTION 条的周只是一两个落地页的重复:设 noindex,也不进 sitemap(页面照常可访问,
    爬虫仍可顺着上面的链接走)。全站一半的周汇总都是这种页,留在索引里只会拉低整站的内容质量评价。"""
    a, b = week_range(wid)
    y, w = wid.split("-W")
    url = f"{_base()}/p/week/{wid}.html"
    title = f"泰国政策周汇总:{y} 年第 {int(w)} 周({a[5:]} 至 {b[5:]})"
    desc = clip(f"{a} 至 {b} 刊登或发布、本站已收录的 {len(items)} 条泰国政策,每条附中文摘要与泰文原文链接。"
                + (f"本周包括:{items[0]['title']}。" if items else ""))
    rows = "".join(
        _item_card(x, "../", points=0,
                   sub=(f'<span class="lib-date">{e(x["date"])}</span><span>{e(x["domain"] or "其他")}</span>'
                        + (f'<span>{e(x["org"])}</span>' if x["org"] else "")))
        for x in items)
    nav = " · ".join(t for t in (
        f'<a href="{e(prev_id)}.html">← 上一周</a>' if prev_id else "",
        '<a href="index.html">全部周汇总</a>',
        f'<a href="{e(next_id)}.html">下一周 →</a>' if next_id else "") if t)
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url,
           "inLanguage": _lang(), "temporalCoverage": f"{a}/{b}", "description": desc,
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                          "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": x["url"],
                                               "name": x["title"]} for i, x in enumerate(items[:50])]}},
          _crumbs_ld([("周汇总", f"{_base()}/p/week/index.html"), (f"{y} 年第 {int(w)} 周", url)])]
    body = (f'<div class="crumb"><a href="../index.html">全部政策</a> / 周汇总</div>'
            f'<h1 class="page">{e(title)}</h1><div class="page-sub">{a} 至 {b} 刊登或发布、本站已收录的 '
            f'<b>{len(items)}</b> 条政策。按条目日期(公报刊登日或发文机关发布日)分周;'
            f'官方数据集通常比刊登日晚几个月开放,新内容会补进对应的周。</div>'
            f'{rows}<p style="margin-top:16px">{nav}</p>')
    robots = ROBOTS_INDEX if len(items) >= MIN_COLLECTION else ROBOTS_NOINDEX
    return _head(title, desc, url, ld, up="../../", robots=robots) + body + _foot("../../")


def render_week_index(weeks: list[tuple[str, int]]) -> str:
    url = f"{_base()}/p/week/index.html"
    rows = "".join(f'<div class="lib-row"><span class="lib-date">{e(week_range(w)[0])}</span>'
                   f'<div class="lib-title"><a href="{e(w)}.html">{e(w.replace("-W", " 年第 "))} 周</a></div>'
                   f'<span class="pill st-draft">{n} 条</span></div>' for w, n in weeks)
    body = ('<div class="crumb"><a href="../index.html">全部政策</a> / 周汇总</div>'
            '<h1 class="page">泰国政策周汇总</h1><div class="page-sub">按公报刊登日(或发文机关发布日)分周,每周一页。'
            '也可以用 <a href="../../feed.xml">RSS</a> 订阅更新。</div>'
            f'<div class="lib-wrap">{rows}</div>')
    title = "泰国政策周汇总 | 政策脉络 · 泰国"
    desc = (f"按泰国皇家公报刊登日分周整理的政策中文汇总,目前共 {len(weeks)} 周、"
            f"{sum(n for _, n in weeks)} 条,每周一页,每条附中文摘要与泰文原文链接,可用 RSS 订阅更新。")
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "泰国政策周汇总",
           "url": url, "inLanguage": _lang(), "description": desc},
          _crumbs_ld([("周汇总", url)])]
    return _head(title, desc, url, ld, up="../../") + body + _foot("../../")


def render_404() -> str:
    """/p/ 下不存在的地址(已下线的政策、打错的链接)显示这一页,状态码仍是 404 ——
    StaticFiles(html=True) 的约定:找不到文件时返回挂载目录根上的 404.html。
    这一页会出现在任意层级的地址上,所以链接一律从站点根路径写起(繁体版从 /zh-hant/ 写起)。"""
    r = f"/{HANT_DIR}/" if _is_hant() else "/"
    body = ('<h1 class="page">页面不存在</h1>'
            '<div class="page-sub">这个地址没有内容:可能是链接有误,也可能是这条政策已经下线'
            '(与别的条目重复、判定为与在泰华人无关,或官方原文链接失效)。</div>'
            f'<p style="line-height:2.2"><a href="{r}p/index.html">全部政策目录</a> · '
            + (f'<a href="{r}">回繁体首页</a> · <a href="/" hreflang="zh-Hans">简体版检索</a> · ' if _is_hant() else '<a href="/">回首页检索</a> · ')
            + f'<a href="{r}p/week/index.html">按周汇总</a> · <a href="{r}{GUIDE_PATH}">泰国皇家公报指南</a></p>')
    return (_head(f"页面不存在 | {SITE_NAME}",
                  "这个地址没有内容。可以从全部政策目录或首页检索继续查找泰国政策的中文摘要与泰文原文。",
                  "", up=r, robots=ROBOTS_NOINDEX) + body + _foot(r))


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


def render_feed(entries: list[dict], title: str = "最新政策", self_path: str = "feed.xml",
                alt_url: str | None = None) -> str:
    """Atom 订阅:最新 50 条。updated 取数据自身日期,保证导出可重复。
    全站一份(feed.xml),每个领域一份(feed/<领域>.xml)。"""
    entries = sorted(entries, key=lambda x: (x["date"] or "", x["uid"]), reverse=True)
    upd = (entries[0]["date"] if entries and entries[0]["date"] else "2026-01-01") + "T00:00:00+07:00"
    alt = alt_url or _home()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{_lang()}">',
           f"  <title>{SITE_NAME} · {e(title)}</title>",
           f"  <subtitle>{e(SITE_DESC)}</subtitle>",
           f'  <link href="{e(_base())}/{e(self_path)}" rel="self"/>',
           f'  <link href="{e(alt)}"/>',
           f"  <id>{e(_base())}/{e(self_path)}</id>", f"  <updated>{upd}</updated>",
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


def render_llms(entries: list[dict], topics: list[tuple[str, str, int]], full: bool = False,
                collections: list[dict] = (), who: list[dict] = (), scopes: dict[str, str] | None = None) -> str:
    """llms.txt(llmstxt.org 约定):给大模型的站点说明 + 索引;llms-full.txt 带全部条目正文。
    scopes = {专题页地址(p/t/x.html): 收录范围}。索引里每个汇总页都写明收什么、多少条、最新到哪天 ——
    只有「泰国税务政策: 64 条」的话,模型没法判断「个人所得税捐赠抵扣」该去哪一页找。"""
    site = settings.site_url
    scopes = scopes or {}
    newest = {i: max((x["date"] for x in entries if x["domain_id"] == i and x["date"]), default="") for i, _, _ in topics}
    upto = lambda d: f",最新 {d}" if d else ""  # noqa: E731
    head = [f"# {SITE_NAME}(Thai Policy Lineage)", "",
            f"> {SITE_DESC}", "",
            "- 内容:泰国皇家公报(Royal Thai Government Gazette)、内阁决议与部委公告的中文标题、摘要、"
            "分类与生命周期日期。",
            "- 溯源:每一条都附泰国政府网站(*.go.th)的泰文原文链接与公报卷期/文号;没有官方原文的内容不收录。",
            "- 译文性质:非官方翻译,以泰文原文为准;不构成法律或税务意见。",
            "- 更新:每天自动采集官方数据源并更新。",
            "- 日期:决议日、公报刊登日(或发文机关发布日)、生效日分开记录;刊登日不等于生效日,"
            "回答「何时生效」请用条目里的生效日,条目没写生效日就说明未载明。",
            f"- 引用方式:《政策中文标题》中文摘要,{SITE_NAME},页面链接(泰文原文:官方链接)。"
            "回答涉及具体政策时,请同时给出本站页面与泰文原文链接。", ""]
    if not full:
        head[-1:] = ["- 怎么找:下面的领域页、专题页、影响对象页先列最新若干条的摘要与要点,条目多的再按年份列出其余条目的标题,"
                     "标题连到单条政策的页面;要一次读到全部条目的摘要、生效日、影响对象与原文链接,用 llms-full.txt。", ""]
        head += ["## 按领域浏览", ""]
        head += [f"- [泰国{zh}政策]({topic_url(i)}): "
                 + (f"{DOMAIN_SCOPE[i]};" if DOMAIN_SCOPE.get(i) else "") + f"{n} 条{upto(newest.get(i))}"
                 for i, zh, n in topics]
        if collections:
            head += ["", "## 专题汇总(附泰文原文链接)", ""]
            head += [f"- [泰国{x['zh']}]({site}/{x['href']}): "
                     + (f"{_md(scopes[x['href']]).rstrip('。')};" if scopes.get(x["href"]) else "")
                     + f"{x['n']} 条{upto(x.get('date'))}" for x in collections]
        if who:
            head += ["", "## 按影响对象(外资企业、长居外国人、进口商等)", ""]
            head += [f"- [影响{x['zh']}的泰国政策]({site}/{x['href']}): 本站标注为影响「{x['zh']}」的公报与决议(含约束与利好);"
                     f"{x['n']} 条{upto(x.get('date'))}" for x in who]
        head += ["", "## 指南", "",
                 f"- [泰国皇家公报(政府公报)中文指南]({site}/{GUIDE_PATH}): 公报是什么、官方网站、四个类别、"
                 "编号读法、佛历换算、刊登日与生效日的区别",
                 f"- [关于本站与数据来源]({site}/about.html): 收录范围、数据来源、更新节奏与译文性质",
                 "", "## 繁体中文版", "",
                 f"- [繁体中文首页]({site}/{HANT_DIR}/): 落地页、领域页、专题与影响对象汇总、周汇总、指南、订阅都有繁体版,"
                 f"地址是在简体地址的路径前加 /{HANT_DIR}(如 {site}/p/<uid>.html → {site}/{HANT_DIR}/p/<uid>.html);"
                 "内容与简体版相同,只做字形转换。检索与图表只有简体版"]
        head += ["", "## 最新政策", ""]
        head += [f"- [{_md(x['title'])}]({x['url']}): {x['date']}"
                 + (f" · {x['doc_no']}" if x["doc_no"] else "") + f" · {clip(x['summary'], 90)}"
                 for x in entries[:40]]
        head += ["", "## 数据", "",
                 f"- [全部政策目录]({site}/p/index.html): 纯 HTML,按领域分组",
                 f"- [全部条目全文]({site}/llms-full.txt): 本文件的完整版,每条含摘要与原文链接",
                 f"- [结构化数据 JSON]({site}/data/site/policies.json): 首页数据,字段见 API",
                 f"- [Atom 订阅]({site}/feed.xml): 最新 50 条;各领域另有 {site}/feed/<领域 id>.xml",
                 f"- [按周汇总]({site}/p/week/index.html): 每周一页", "",
                 "## Optional", "", f"- [隐私政策]({site}/privacy.html)"]
        return "\n".join(head) + "\n"
    body = head + ["## 全部条目", ""]
    for x in entries:
        body += [f"### {_md(x['title'])}", "",
                 f"- 页面:{x['url']}",
                 *([f"- 泰文原题:{_md(x['title_th'])}"] if x["title_th"] else []),
                 *([f"- 编号:{x['doc_no']}"] if x["doc_no"] else []),
                 f"- 日期:{x['date'] or '—'} · 领域:{x['domain'] or '—'} · 状态:{x['status']}",
                 *([f"- 生效日:{x['effective']}"] if x.get("effective") else []),
                 *([f"- 影响对象:{'、'.join(x['parties_zh'])}"] if x.get("parties_zh") else []),
                 *([f"- {x.get('org_label') or '发文机关'}:{x['org']}"] if x["org"] else []),
                 f"- 泰文原文(官方):{x['official']}", "",
                 _md(x["summary"]), *([""] + [f"- {_md(k)}" for k in x["points"]] if x["points"] else []), ""]
    return "\n".join(body) + "\n"


# ───────────────────── index.html 受管区块 ─────────────────────

def _replace_block(text: str, name: str, content: str) -> str:
    """替换 <!-- seo:name --> … <!-- /seo:name --> 之间的内容;没有标记就原样返回。"""
    pat = re.compile(rf"(<!-- seo:{name} [^>]*-->\n?).*?(\s*<!-- /seo:{name} -->)", re.S)
    return pat.sub(lambda m: m.group(1) + content + m.group(2), text, count=1)


def _coverage(entries: list[dict]) -> str | None:
    """数据集的时间覆盖范围(最早条目日期/最新条目日期),给 Dataset 结构化数据用。"""
    dates = [x["date"] for x in entries if x["date"]]
    return f"{min(dates)}/{max(dates)}" if dates else None


def update_index_html(entries: list[dict], topics: list[tuple[str, str, int]], cfg: dict,
                      collections: list[dict] = (), who: list[dict] = (),
                      overview: dict | None = None) -> bool:
    """overview:A.overview 的结果(与 data/site/policies.json 同一份)。首页「最新收录」实际显示的
    featured 条目预渲染进 <!-- seo:feed -->,页头时间戳、条数与数据说明预渲染进 seo:stamp / seo:today-sub /
    seo:lag-note —— 与 js/data.js 的 renderOverview 同一口径,前端加载后替换成同样的文字,版面不跳。
    None 表示不动这几个区块。"""
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
        {"@type": "Organization", "@id": f"{site}/#org", "name": SITE_NAME,
         "alternateName": "Thai Policy Lineage", "url": f"{site}/",
         "logo": f"{site}/favicon.svg", "image": f"{site}/{OG_IMAGE}", "description": SITE_DESC},
        {"@type": "Dataset", "name": "泰国政策中文结构化数据", "description": SITE_DESC,
         "url": f"{site}/p/index.html", "inLanguage": "zh-CN", "isAccessibleForFree": True,
         "keywords": ["泰国政策", "泰国皇家公报", "泰国内阁决议", "Royal Thai Government Gazette",
                      *[f"泰国{zh}" for _, zh, _ in topics]],
         "temporalCoverage": _coverage(entries),
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
    head = "\n".join(x for x in [
        f'<link rel="canonical" href="{e(site)}/">',
        hreflang_links(f"{site}/"),
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
        f'<link rel="alternate" type="application/atom+xml" title="{SITE_NAME} · 最新政策" href="feed.xml">',
        f'<meta property="og:url" content="{e(site)}/">',
        '<meta property="og:locale" content="zh_CN">',
        f'<meta property="og:image" content="{e(site)}/{OG_IMAGE}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{OG_ALT}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{e(site)}/{OG_IMAGE}">',
        *[f'<meta name="{metas[k]}" content="{e(ver[k])}">' for k in metas if ver.get(k)],
        _ld(graph)] if x)
    nav = " · ".join(f'<a href="p/topic/{e(i)}.html">{e(zh)}</a>' for i, zh, _ in topics)
    latest = " · ".join(f'<a href="p/{e(slug(x["uid"]))}.html">{e(x["title"])}</a>' for x in entries[:12])
    coll = " · ".join(f'<a href="{e(x["href"])}">{e(x["zh"])}</a>' for x in collections)
    whos = " · ".join(f'<a href="{e(x["href"])}">{e(x["zh"])}</a>' for x in who)
    links = (f'<nav class="seo-nav" aria-label="站内导航">'
             + (f"<div><b>按领域浏览</b> {nav}</div>" if nav else "")
             + (f"<div><b>专题汇总</b> {coll}</div>" if coll else "")
             + (f"<div><b>按影响对象</b> {whos}</div>" if whos else "")
             + f'<div><b>指南与汇总</b> <a href="{GUIDE_PATH}">泰国皇家公报(政府公报)中文指南</a> · '
               '<a href="p/week/index.html">按周汇总</a> · <a href="p/index.html">全部政策目录</a></div>'
             + (f"<div><b>最新收录</b> {latest}</div>" if latest else "") + "</nav>")
    old = path.read_text(encoding="utf-8")
    new = _replace_block(_replace_block(old, "head", head), "links", links)
    if overview is not None:
        featured = [p for p in overview.get("policies") or [] if p.get("featured")]
        new = _replace_block(new, "feed", render_home_feed(featured))
        for name, text in home_texts(overview).items():
            new = _replace_block(new, name, text)
    if new != old:
        path.write_text(new, encoding="utf-8")

    # 手写的静态页(隐私政策、怎么用本站):canonical + WebPage 结构化数据
    for fname, name, kind in STATIC_PAGES:
        page = REPO_ROOT / fname
        if not page.exists():
            continue
        old = page.read_text(encoding="utf-8")
        new = _replace_block(old, "head", _static_head(old, fname, name, kind))
        if new != old:
            page.write_text(new, encoding="utf-8")
    return True


STATIC_PAGES = (("privacy.html", "隐私政策", "WebPage"), ("about.html", "怎么用本站", "AboutPage"))


def _static_head(text: str, fname: str, name: str, kind: str) -> str:
    """手写静态页的 <!-- seo:head --> 区块(按当前字形):canonical、hreflang、分享信息、结构化数据。"""
    site, url = settings.site_url, f"{_base()}/{fname}"
    ld = {"@context": "https://schema.org", "@type": kind, "name": name,
          "url": url, "inLanguage": _lang(),
          "isPartOf": {"@type": "WebSite", "@id": f"{_home()}#website", "name": SITE_NAME, "url": _home()},
          **({"about": {"@type": "Organization", "@id": f"{site}/#org", "name": SITE_NAME}}
             if kind == "AboutPage" else {})}
    t = re.search(r"<title>(.*?)</title>", text, re.S)
    dsc = re.search(r'<meta name="description" content="([^"]*)"', text)
    og = [f'<link rel="canonical" href="{e(url)}">',
          hreflang_links(url),
          f'<meta property="og:url" content="{e(url)}">',
          '<meta property="og:type" content="website">',
          f'<meta property="og:locale" content="{"zh_TW" if _is_hant() else "zh_CN"}">',
          f'<meta property="og:site_name" content="{SITE_NAME}">',
          *([f'<meta property="og:title" content="{t.group(1).strip()}">'] if t else []),      # 页面里已是转义过的文本
          *([f'<meta property="og:description" content="{dsc.group(1)}">'] if dsc else []),
          f'<meta property="og:image" content="{e(site)}/{_og_image()}">',
          '<meta name="twitter:card" content="summary_large_image">']
    return "\n".join(x for x in og if x) + "\n" + _ld(ld)


# ───────────────────── 首页「最新收录」预渲染(<!-- seo:feed -->) ─────────────────────

_DIR_LABEL = {"tight": "▲ 收紧", "loose": "▼ 放宽"}
_STANCE_PREFIX = {"constrain": "约束 · ", "support": "利好 · ", "neutral": ""}


def _cut(t: str, n: int) -> str:
    t = str(t or "")
    return t[:n] + "…" if len(t) > n else t


def render_policy_card(p: dict) -> str:
    """与 js/data.js 的 policyCard 同一结构、同一类名、同一处空白,前端加载后整体替换时版面不跳。
    只少了点击打开站内详情的 onclick:脚本还没加载完时点标题,直接去落地页,而不是调用还不存在的函数。"""
    dates = p.get("dates") or {}
    pub = dates.get("published_at") or p.get("date")
    verb = "刊登" if p.get("doc_no_label") == "公报" else ("发布" if dates.get("published_at") else "决议")
    points = (p.get("key_points") or [])[:2]
    meta = "".join(x for x in [
        f'<span>{e(p["org"])}</span>' if p.get("org") else "",
        f'<span>{e(p.get("doc_no_label") or "文号")} <b>{e(p["doc_no"])}</b></span>' if p.get("doc_no") else "",
        f"<span>{verb} {e(pub)}</span>" if pub else "",
        (f'<span><a href="{e(p["source_url"])}" target="_blank" rel="noopener"\n'
         f'    onclick="event.stopPropagation()">泰文原文 ↗</a></span>') if p.get("source_url") else ""])
    d = p.get("direction")
    dir_ = f'<span class="dir {e(d)}">{_DIR_LABEL[d]}</span>' if d in _DIR_LABEL else ""
    chips = "".join(f'<span class="party {e(x.get("stance"))}">{e(_STANCE_PREFIX.get(x.get("stance"), ""))}'
                    f'{e(x.get("label"))}</span>' for x in (p.get("parties") or [])[:2])
    body = (f'<div class="pc-sum">{e(p.get("summary_zh"))}</div><ul class="pc-points">'
            + "".join(f"<li>{e(k)}</li>" for k in points) + "</ul>" if points
            else f'<div class="pc-sum"><span class="thin-tag">摘要仅据标题</span>{e(_cut(p.get("summary_zh"), 90))}</div>')
    return f"""<div class="card policy-card">
    <div class="pc-top">
      <span class="chip {e(p.get("domain"))}">{e(p.get("domain_label"))}</span>
      {dir_}{chips}
      {'<span class="verified">已人工复核</span>' if p.get("verified") else ''}
    </div>
    <a class="pc-title" href="p/{e(str(p["uid"]).lower())}.html">{e(p.get("title_zh"))}</a>
    {body}
    <div class="pc-meta">{meta}</div>
  </div>"""


def _bkk_stamp(iso: str) -> str:
    """js/data.js 的 fmtStamp:按曼谷时间显示到分钟,如「2026-11-18 07:07 曼谷时间」。"""
    from datetime import datetime
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return e(iso)
    if d.tzinfo is not None:
        from zoneinfo import ZoneInfo
        d = d.astimezone(ZoneInfo("Asia/Bangkok"))
    return d.strftime("%Y-%m-%d %H:%M") + " 曼谷时间"


def home_texts(d: dict) -> dict[str, str]:
    """首页几处由 js/data.js renderOverview 填写的文字,导出时按同一口径预先写好(受管区块名 → HTML)。"""
    st = d.get("stats") or {}
    total = st.get("total") or len(d.get("policies") or [])
    updated = _bkk_stamp(d["updated_at"])[:10] if d.get("updated_at") else "—"
    gz = st.get("gazette_to") or st.get("date_to")
    lag = (f"泰国官方公报数据集(data.go.th)通常比刊登日晚几个月开放,目前收录到 <b>{e(str(gz)[:10] if gz else '—')}</b> 刊登的公报。"
           + (f"更新的规定来自税务厅、BOI 官网(已收 {st['agency_n']} 条,每日同步)。" if st.get("agency_n") else "")
           + f"最近一次采集 {e(updated)}。")
    return {"stamp": f"数据更新 {_bkk_stamp(d['updated_at'])}" if d.get("updated_at") else "加载中……",
            "today-sub": f"最近收录的 <b>{total}</b> 条公报,读过原文、有要点的排在前面。",
            "lag-note": lag}


def render_home_feed(featured: list[dict]) -> str:
    """不跑 JS 的爬虫(Bing、百度、AI 爬虫)在首页主体里读到的就是这几条;前端加载后 set('feed', …) 整体替换。"""
    return "".join(render_policy_card(p) for p in featured) or \
        '<div class="card"><div class="pc-sum">暂无可展示的政策。</div></div>'


# ───────────────────── 繁体版:首页门户、手写静态页 ─────────────────────

HANT_LATEST = 20            # 繁体首页带摘要展示的最新条数
# 繁体首页的描述与开场白。不能照抄 SITE_DESC:那句话里的「七维政策分析与趋势看板」是简体单页应用的功能,
# 繁体首页是静态门户页,没有这些;搜索结果里许诺了页面上没有的东西,点进来的人会直接走
HANT_HOME_DESC = ("泰国皇家公报、内阁决议与各部委公告的中文摘要与正文要点:按签证、税务、公司投资、劳工、房产土地、"
                  "海关贸易等领域整理,每条附泰国政府网站上的泰文原文链接。非官方翻译,以泰文原文为准。")


def render_hant_home(entries: list[dict], topics: list[tuple[str, str, int]], collections: list[dict],
                     who: list[dict], weeks: list[tuple[str, int]], telegram: str = "") -> str:
    """/zh-hant/ 首页:静态门户页(单页应用只有简体)。entries 的 url 已是繁体地址;文字仍是简体,写盘前统一转换。"""
    url = _home()
    latest = entries[:HANT_LATEST]
    nav = " · ".join(f'<a href="p/topic/{e(i)}.html">{e(zh)}({n})</a>' for i, zh, n in topics)
    coll = " · ".join(f'<a href="{e(x["href"])}">{e(x["zh"])}({x["n"]})</a>' for x in collections)
    whos = " · ".join(f'<a href="{e(x["href"])}">{e(x["zh"])}({x["n"]})</a>' for x in who)
    wk = " · ".join(f'<a href="p/week/{e(w)}.html">{e(week_range(w)[0])} 起({n} 条)</a>' for w, n in weeks)
    feeds = " · ".join(f'<a href="feed/{e(i)}.xml">{e(zh)}</a>' for i, zh, _ in topics)
    total = len(entries)
    dates = [x["date"] for x in entries if x["date"]]
    body = (f'<h1 class="page">泰国政策中文数据库:皇家公报与内阁决议</h1>'
            f'<div class="page-sub">{e(HANT_HOME_DESC)}<br>目前收录 <b>{total}</b> 条'
            + (f",文件日期从 {e(min(dates))} 到 {e(max(dates))}" if dates else "") + "。"
            '本页是繁体中文版入口;互动检索、筛选与趋势图表目前只有简体版:'
            '<a href="../" hreflang="zh-Hans">简体版首页</a> · <a href="../#search" hreflang="zh-Hans">找政策</a>。</div>'
            '<nav class="coll-related">'
            + (f"<div><b>按领域浏览</b> {nav}</div>" if nav else "")
            + (f"<div><b>专题汇总</b> {coll}</div>" if coll else "")
            + (f"<div><b>按影响对象</b> {whos}</div>" if whos else "")
            + f'<div><b>指南</b> <a href="{GUIDE_PATH}">泰国皇家公报(政府公报)中文指南</a> · '
              '<a href="about.html">怎么用本站</a> · <a href="p/index.html">全部政策目录</a></div>'
            + '<div><b>周汇总</b> ' + (f"{wk} · " if wk else "") + '<a href="p/week/index.html">全部周汇总</a></div>'
            + '<div><b>订阅更新</b> <a href="feed.xml">RSS 订阅全站更新</a>'
            + (f" · 按领域:{feeds}" if feeds else "")
            + (f' · <a href="{e(telegram)}" rel="noopener" target="_blank">Telegram 频道</a>' if telegram else "")
            + "</div></nav>"
            + f'<h2 class="mod sec">最新收录</h2>'
            + "".join(_item_card(x, "p/", tag="h3") for x in latest)
            + f'<p style="margin-top:16px"><a href="p/index.html">查看全部 {total} 条 →</a></p>')
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "@id": f"{url}#website", "name": SITE_NAME,
           "alternateName": ["Thai Policy Lineage", "泰国政策中文库"], "url": url, "inLanguage": _lang(),
           "description": HANT_HOME_DESC, "publisher": {"@id": f"{settings.site_url}/#org"}},
          {"@context": "https://schema.org", "@type": "CollectionPage", "name": "泰国政策 · 最新收录", "url": url,
           "inLanguage": _lang(), "isPartOf": {"@id": f"{url}#website"},
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(latest),
                          "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": x["url"],
                                               "name": x["title"]} for i, x in enumerate(latest)]}}]
    return (_head("泰国政策中文数据库:皇家公报、内阁决议中文摘要与原文 | 政策脉络", clip(HANT_HOME_DESC), url, ld, up="")
            + body + _foot(""))


_ASSET_REF_RE = re.compile(r'((?:href|src)=")(css/|js/|assets/|favicon\.svg)')
_DATA_BASE_RE = re.compile(r'data-base="(?!/|https?:)([^"]*)"')     # 相对的站点根前缀,繁体页多退一级
_HTML_LANG_RE = re.compile(r'(<html\b[^>]*?\blang=")zh-CN(")')
# 繁体 about.html 的提示:页面里说的检索框、领域按钮、「数据覆盖」都在简体首页
HANT_ABOUT_NOTE = ('<p class="hant-note">繁体版说明:下文提到的首页检索框、「找政策」、领域按钮、「各领域条数」与「数据覆盖」'
                   '都在<a href="../" hreflang="zh-Hans">简体版首页</a>;繁体版提供'
                   '<a href="index.html">繁体首页</a>(按领域、专题、最新收录浏览)与'
                   '<a href="p/index.html">全部政策目录</a>。</p>')
_SWITCH_RE = re.compile(r'<a class="lang-switch"[^>]*>.*?</a>', re.S)


def render_hant_static(text: str, fname: str, name: str, kind: str) -> str:
    """手写的 about.html / privacy.html → 繁体版(仍是简体文字,写盘前统一转换):
    换掉受管的 <head> 区块、语言标记与页头切换链接;资源文件多退一级到站点根目录,
    其余相对链接(index.html、p/…、feed.xml)两边结构相同,原样留在 /zh-hant/ 内。"""
    text = _replace_block(text, "head", _static_head(text, fname, name, kind))
    text = _replace_block(text, "hant-note", HANT_ABOUT_NOTE)
    text, n = _HTML_LANG_RE.subn(r"\1zh-Hant\2", text, count=1)
    if not n:
        raise ValueError(f"{fname}:找不到 <html lang=…>,无法标成繁体")
    text = _ASSET_REF_RE.sub(r"\1../\2", text)
    text = _DATA_BASE_RE.sub(lambda m: f'data-base="../{m.group(1)}"', text)
    return _SWITCH_RE.sub(lambda m: lang_switch("", f"{_base()}/{fname}"), text, count=1)


def build(s: Session, overview: dict | None = None) -> dict[str, int]:
    """overview:A.overview(s) 的结果(app.export 已经算过,传进来省一次);首页预渲染用其中 featured 的条目。"""
    from . import hant, seo_guide
    today = A._today(s)
    docs = s.scalars(select(Document).order_by(Document.display_date.desc().nullslast(),
                                               Document.uid)).all()
    titles = {d.uid: d.title_zh for d in docs}
    domains = {d.id: d for d in s.scalars(select(Domain)).all()}
    views = {d.uid: A.document_view(s, d, today) for d in docs}    # 简繁两遍渲染共用
    # 机关一栏能不能当「发文机关」说(见 issuer_info);官网来源的条目,原文在哪个机关的官网上
    th_names = agency_th_names()
    agencies_zh = {a.id: a.zh for a in s.scalars(select(Agency)).all()}
    issuers = {d.uid: issuer_info(d, views[d.uid]["org"], th_names) for d in docs}
    sites = {d.uid: source_site(d, agencies_zh) for d in docs}

    def dom_of(doc: Document) -> tuple[str, str]:
        dom = min(doc.domains, key=lambda x: x.seq).domain_id if doc.domains else ""
        return (dom, domains[dom].zh) if dom in domains else ("", "其他")

    # 整目录重建:已删除或被标 skip 的政策,其落地页(简繁两份)也要消失。
    # 先把简繁全部页面渲染、转换到内存,最后才清空目录、写盘:中途出错时两套旧文件原样保留。
    # 只清空内容、不删目录本身 —— 生产环境 p/ 是 docker 挂载点,删挂载点会 EBUSY,
    # 导出失败会让容器启动命令(ingest && export && uvicorn)永远起不来
    hant_root = REPO_ROOT / HANT_DIR

    by_dom: dict[str, list[tuple[str, str, str]]] = {}
    for doc in docs:
        dom = dom_of(doc)
        by_dom.setdefault(dom[0], []).append(
            (doc.display_date.isoformat() if doc.display_date else "", doc.uid, doc.title_zh))
    # 中文标题完全相同的条目(同名系列):<title> 带上日期,否则搜索结果里是两条一模一样的标题
    seen: dict[str, int] = {}
    for doc in docs:
        seen[doc.title_zh] = seen.get(doc.title_zh, 0) + 1
    dup_titles = {t for t, n in seen.items() if n > 1}
    parties_zh = {p.id: p.zh for p in s.scalars(select(Party)).all()}

    # 同名系列:与「脉络」页同一口径(A.series_lineage),落地页之间互相链接
    in_series: dict[str, list[tuple[str, str, str]]] = {}
    for it in A.series_lineage(s):
        members = [(st["uid"], st["stage"][:10], st["title"]) for st in it["stages"]]
        for u, _, _ in members:
            in_series[u] = [m for m in members if m[0] != u]

    rows, entries, pending = [], [], []
    for doc in docs:
        dom = dom_of(doc)
        peers = by_dom.get(dom[0], [])
        i = next(k for k, x in enumerate(peers) if x[1] == doc.uid)
        related = [(u, dt, t) for dt, u, t in (peers[max(0, i - 3):i] + peers[i + 1:i + 4])][:6]
        pending.append((doc, dom if dom[0] else ("", ""), related))   # 等汇总页成员算出来再渲染
        date_s = doc.display_date.isoformat() if doc.display_date else ""
        rows.append((dom[1], date_s, doc.uid, doc.title_zh))
        official = next((x.url for x in doc.sources if x.role == "official" and x.url), "")
        entries.append({"uid": doc.uid, "title": doc.title_zh, "title_th": doc.title_th or "",
                        "url": page_url(doc.uid), "date": date_s, "domain": dom[1] if dom[0] else "",
                        "domain_id": dom[0],
                        "parties": [{"id": x.party_id, "stance": x.stance}
                                    for x in sorted(doc.parties, key=lambda x: x.party_id)],
                        "doc_no": doc.doc_no or "", "summary": split_summary(doc.summary_zh)[0],
                        "points": sound_points(split_summary(doc.summary_zh)[1]),
                        "status": doc.status.zh, "official": official,
                        "effective": doc.effective_from.isoformat() if doc.effective_from else "",
                        "parties_zh": [parties_zh[x.party_id] for x in sorted(doc.parties, key=lambda x: x.party_id)
                                       if x.party_id in parties_zh],
                        "org": issuers[doc.uid][1], "org_label": issuers[doc.uid][0]})

    topics = sorted(((i, domains[i].zh, len(items)) for i, items in by_dom.items() if i),
                    key=lambda t: (-t[2], t[0]))

    # 专题汇总:影响对象页 + 配置专题(只汇编已收录条目,不写综述)
    coll_pages, coll_index = collection_pages(entries, parties_zh)
    who_pages, topic_pages = _split_index(coll_index)
    member_of = collection_members(coll_pages)

    # 领域页要用到汇总页的成员关系(哪些专题与本领域相关)
    dom_colls: dict[str, list[tuple[str, str]]] = {}
    for i, zh, _ in topics:
        hits: dict[tuple[str, str], int] = {}
        for x in entries:
            if x["domain_id"] == i:
                for c in member_of.get(x["uid"], []):
                    if c[0].startswith("t/"):
                        hits[c] = hits.get(c, 0) + 1
        dom_colls[i] = [c for c, n in sorted(hits.items(), key=lambda kv: (-kv[1], kv[0])) if n >= MIN_COLLECTION]

    # 指南页:泰国皇家公报是什么(数字与编号示例从数据现算)
    gaz = [d for d in docs if d.gazette_series]
    series_n: dict[str, int] = {}
    for d in gaz:
        series_n[d.gazette_series] = series_n.get(d.gazette_series, 0) + 1
    ex = next((d for d in gaz if d.gazette_volume and d.gazette_part and d.doc_no and d.display_date
               and "พิเศษ" in d.gazette_series), None)
    guide_stats = {
        "total": len(docs), "gazette_total": len(gaz), "series": series_n,
        "example": ({"uid": ex.uid, "title": ex.title_zh, "doc_no": ex.doc_no, "series": ex.gazette_series,
                     "volume": ex.gazette_volume, "part": ex.gazette_part,
                     "date": ex.display_date.isoformat()} if ex else None),
        "topics": topics, "collections": topic_pages}

    # 周汇总:p/week/<YYYY-Www>.html,按公报刊登日分周
    by_week: dict[str, list[dict]] = {}
    for x in entries:
        if x["date"]:
            by_week.setdefault(week_id(x["date"]), []).append(x)
    week_ids = sorted(by_week, reverse=True)

    sub = json.loads(SUBSCRIBE_CONFIG.read_text(encoding="utf-8")) if SUBSCRIBE_CONFIG.exists() else {}
    telegram = str(sub.get("telegram_channel_url") or "")
    telegram = telegram if telegram.startswith("https://t.me/") else ""

    def render_site(ents: list[dict]) -> dict[str, str]:
        """按当前字形渲染全部静态页,返回 {相对字形根目录的路径: 内容}。ents 的 url 已按当前字形算好。"""
        by_uid = {x["uid"]: x for x in ents}
        swap = lambda items: [by_uid[x["uid"]] for x in items]  # noqa: E731
        out: dict[str, str] = {}
        cps = [(k, i, zh, swap(items), t) for k, i, zh, items, t in coll_pages]
        out.update({f"p/{rel}": html for rel, html in render_collections(cps, coll_index).items()})
        for doc, dom, related in pending:
            out[f"p/{slug(doc.uid)}.html"] = render_page(
                s, doc, today, titles, dom, related, in_series.get(doc.uid, []),
                member_of.get(doc.uid, []), dup_title=doc.title_zh in dup_titles, view=views[doc.uid],
                issuer=issuers[doc.uid], site=sites[doc.uid])
        for i, zh, _ in topics:
            out[f"p/topic/{i}.html"] = render_topic(i, zh, domains[i].en or "",
                                                    [x for x in ents if x["domain_id"] == i],
                                                    dom_colls[i], [t for t in topics if t[0] != i])
        out["p/index.html"] = render_index(rows, topics, topic_pages, who_pages)
        out[GUIDE_PATH] = seo_guide.render(guide_stats)
        for k, wid in enumerate(week_ids):
            items = sorted(swap(by_week[wid]), key=lambda x: (x["date"], x["uid"]), reverse=True)
            out[f"p/week/{wid}.html"] = render_week(wid, items, week_ids[k + 1] if k + 1 < len(week_ids) else None,
                                                    week_ids[k - 1] if k > 0 else None)
        out["p/week/index.html"] = render_week_index([(w, len(by_week[w])) for w in week_ids])
        out["feed.xml"] = render_feed(ents)
        # 按领域订阅:feed/<领域>.xml,整目录重建(领域没有条目了,订阅文件也要消失)
        for i, zh, _ in topics:
            out[f"feed/{i}.xml"] = render_feed([x for x in ents if x["domain_id"] == i], f"{zh} · 最新政策",
                                               f"feed/{i}.xml", topic_url(i))
        return out

    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    if overview is None:
        overview = A.overview(s)

    # ── 繁体:同样的页面在 /zh-hant/ 下各一份,渲染完整页再转换字形(全部在内存里)──
    hant_pages: dict[str, str] | None = None
    try:
        conv = hant.Converter()
        with _variant(True):
            ents_h = [{**x, "url": page_url(x["uid"])} for x in entries]
            raw = render_site(ents_h)
            raw["404.html"] = render_404()
            raw["index.html"] = render_hant_home(
                ents_h, topics, topic_pages, who_pages,
                [(w, len(by_week[w])) for w in week_ids if len(by_week[w]) >= MIN_COLLECTION][:8], telegram)
            # 手写静态页的繁体版:从简体文件转换(受管的 head 区块按繁体重写,与简体文件里的旧区块无关)
            if (REPO_ROOT / "index.html").exists():
                for fname, name, kind in STATIC_PAGES:
                    if (REPO_ROOT / fname).exists():
                        raw[fname] = render_hant_static((REPO_ROOT / fname).read_text(encoding="utf-8"),
                                                        fname, name, kind)
        hant_pages = {rel: conv.html(text) for rel, text in raw.items()}
    except Exception:
        if hant_strict():
            raise
        log.exception("繁体版生成失败(HANT_STRICT=0):保留旧的 zh-hant/,简体照常导出")

    # 繁体没生成时,简体页与 sitemap 只引用旧 zh-hant/ 里确实存在的繁体页
    avail = None if hant_pages is not None else frozenset(
        str(p.relative_to(hant_root)) for p in hant_root.rglob("*.html")) if hant_root.is_dir() else frozenset()
    token = _HANT_AVAIL.set(avail)
    try:
        # ── 简体 ──
        hans = render_site(entries)
        hans["p/404.html"] = render_404()

        # sitemap:lastmod 用数据自身的日期,保证导出可重复
        newest = entries[0]["date"] if entries else None
        urls = [(f"{settings.site_url}/", newest), (f"{settings.site_url}/p/index.html", newest),
                (f"{settings.site_url}/about.html", None), (f"{settings.site_url}/privacy.html", None)]
        urls += [(topic_url(i), by_dom[i][0][0] or None) for i, _, _ in topics]
        urls += [(f"{settings.site_url}/{x['href']}", x["date"] or None) for x in topic_pages + who_pages]
        urls += [(f"{settings.site_url}/{GUIDE_PATH}", newest)]
        urls += [(f"{settings.site_url}/p/week/index.html", newest)]
        # 条目太少的周是 noindex(见 render_week),不进 sitemap
        urls += [(f"{settings.site_url}/p/week/{w}.html", by_week[w][0]["date"]) for w in week_ids
                 if len(by_week[w]) >= MIN_COLLECTION]
        urls += [(x["url"], x["date"] or None) for x in entries]
        # 繁体版:同一批页面,地址多一级 /zh-hant;只列真的有的(about / privacy 要 index.html 在才生成)
        have = set(hant_pages) if hant_pages is not None else set(avail or ())
        for u, lm in list(urls):
            hu = _alternates(u)[1]
            rel = hu[len(f"{settings.site_url}/{HANT_DIR}/"):] or "index.html"
            if rel in have:
                urls.append((hu, lm))

        # ── 写盘:渲染全部成功之后才动目录 ──
        clear_dir(PAGES_DIR)
        clear_dir(REPO_ROOT / "feed")
        for rel, text in hans.items():
            write(PAGES_DIR / rel[2:] if rel.startswith("p/") else REPO_ROOT / rel, text)
        if hant_pages is not None:
            clear_dir(hant_root)
            for rel, text in hant_pages.items():
                write(hant_root / rel, text)

        (SITE_DIR / "collections.json").write_text(json.dumps(
            {"topics": topic_pages, "who": who_pages}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (REPO_ROOT / "robots.txt").write_text(render_robots(), encoding="utf-8")
        (REPO_ROOT / "llms.txt").write_text(
            render_llms(entries, topics, collections=topic_pages, who=who_pages,
                        scopes={f"p/t/{i}.html": t["scope_zh"] for k, i, _, _, t in coll_pages if k == "t"}),
            encoding="utf-8")
        (REPO_ROOT / "llms-full.txt").write_text(render_llms(entries, topics, full=True), encoding="utf-8")
        update_index_html(entries, topics, seo_config(), topic_pages, who_pages, overview)
        (REPO_ROOT / "sitemap.xml").write_text(render_sitemap(urls), encoding="utf-8")
    finally:
        _HANT_AVAIL.reset(token)

    # 广告配置:config/ads.json → data/site/ads.json;启用 AdSense 时生成 ads.txt
    ads = json.loads(ADS_CONFIG.read_text(encoding="utf-8")) if ADS_CONFIG.exists() else {"enabled": False}
    (SITE_DIR / "ads.json").write_text(json.dumps(ads, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    (SITE_DIR / "subscribe.json").write_text(json.dumps({
        "telegram_channel_url": telegram,
        "feeds": [{"id": i, "zh": zh, "href": f"feed/{i}.xml"} for i, zh, _ in topics],
        "weeks": [{"id": w, "from": week_range(w)[0], "to": week_range(w)[1], "n": len(by_week[w]),
                   "href": f"p/week/{w}.html"} for w in [w for w in week_ids if len(by_week[w]) >= 5][:6]],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
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
    return {"pages": len(docs) + 1, "topics": len(topics), "sitemap_urls": len(urls),
            "hant_pages": sum(1 for _ in hant_root.rglob("*.html")), "hant_ok": hant_pages is not None}
