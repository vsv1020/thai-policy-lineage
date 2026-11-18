# -*- coding: utf-8 -*-
"""指南页 p/guide/royal-gazette.html:泰国皇家公报是什么、官网在哪、怎么读编号、有没有中文版。

为什么要有这一页:Bing 给本站带来曝光的搜索词几乎全是「泰国皇家公报」「泰国政府公报」「泰国政府公报网」
这类问公报本身的词,站内却没有一页正面回答;config/seo.json 的 GEO 实测题里也有
「在哪里可以查到泰国皇家公报政策的中文翻译和官方原文链接?」。

写法约束(与专题页「不写综述」同一精神):
- 只写公报制度本身、可在官方网站核对的事实,以及本站自己的做法;不评论任何一条政策。
- ข 类只提名称并说明本站不收录,不展开 —— 王室相关内容零加工是红线。
- 涉及本站数据的数字(收录条数、各类条数、编号示例)全部由调用方从数据库现算,不写死。

由 app.seo.build 调用,与其他落地页一样是派生产物。
"""
from __future__ import annotations

from .config import settings

GUIDE_TITLE = "泰国皇家公报(政府公报)中文指南"
OFFICIAL_SITE = "https://ratchakitcha.soc.go.th/"
OPEN_DATA_SITE = "https://data.go.th/"


def thai_citation(series: str, volume: int, part: str) -> str:
    """本站编号「ง พิเศษ 143/52」对应的泰文原文写法「เล่ม 143 ตอนพิเศษ 52 ง」。"""
    letter = series.split()[0]
    kind = "ตอนพิเศษ" if "พิเศษ" in series else "ตอนที่"
    return f"เล่ม {volume} {kind} {part} {letter}"


def series_zh(series: str) -> str:
    return f"{series.split()[0]} 类" + ("特刊" if "พิเศษ" in series else "")


def faq(stats: dict) -> list[tuple[str, str]]:
    """常见问题:页面正文与 FAQPage 结构化数据用同一份文字。"""
    out = [
        ("泰国皇家公报和「泰国政府公报」是一回事吗?",
         "是。两者都指 ราชกิจจานุเบกษา(Royal Thai Government Gazette),只是中文译法不同,"
         "也有人译作「泰国皇家政府公报」。"),
        ("泰国皇家公报的官方网站是哪个?",
         "官方网站是 ratchakitcha.soc.go.th,由出版公报的内阁秘书处运营,可以检索并下载每一期的 PDF 原文,内容为泰文。"),
        ("泰国皇家公报有中文版吗?",
         "没有官方中文版。政策脉络 · 泰国(www.thaipolicy.com)提供非官方的中文标题、摘要与正文要点,"
         "每条都附泰国政府网站上的泰文原文链接;译文如与原文有出入,以泰文原文为准。"),
        ("文件在公报上刊登后就马上生效吗?",
         "不一定。什么时候生效以每份文件自己的条款为准,常见的写法是「自公报刊登之日的次日起施行」,"
         "也有指定具体日期的。所以刊登日和生效日要分开看。"),
        ("佛历年份怎么换算成公历?",
         "佛历(พ.ศ.,B.E.)年份减去 543 就是公历年份,例如佛历 2569 年是公历 2026 年。"),
    ]
    ex = stats.get("example")
    if ex:
        out.insert(4, (
            f"公报编号「{ex['doc_no']}」是什么意思?",
            f"这是本站的简写:{series_zh(ex['series'])},第 {ex['volume']} 卷第 {ex['part']} 期。"
            f"泰文原文里的写法是「{thai_citation(ex['series'], ex['volume'], ex['part'])}」。"))
    return out


def render(stats: dict) -> str:
    """stats = {total, gazette_total, series: {系列: 条数}, example: {...}|None,
    topics: [(领域 id, 中文名, 条数)], collections: [{zh, href, n}]}"""
    from .seo import GUIDE_PATH, SITE_NAME, _foot, _head, clip, e, slug   # 延迟导入,避免与 seo 循环依赖

    site = settings.site_url
    url = f"{site}/{GUIDE_PATH}"
    title = "泰国皇家公报(政府公报)是什么:官网、分类、编号与中文查询 | 政策脉络"
    desc = clip("泰国皇家公报(ราชกิจจานุเบกษา,Royal Thai Government Gazette,也译泰国政府公报)是泰国政府的官方公报,"
                "由内阁秘书处出版,官网 ratchakitcha.soc.go.th,只有泰文。本页说明公报的四个类别、编号读法、"
                "佛历换算、刊登日与生效日的区别,以及在哪里查中文摘要与官方原文。")
    series = stats.get("series") or {}
    n_k = series.get("ก", 0)
    n_ng = sum(n for k, n in series.items() if k.split()[0] == "ง")
    n_special = sum(n for k, n in series.items() if k.split()[0] == "ง" and "พิเศษ" in k)
    ex = stats.get("example")
    qa = faq(stats)

    lede = ("泰国皇家公报(泰文 ราชกิจจานุเบกษา,英文 Royal Thai Government Gazette,中文也译作「泰国政府公报」"
            "「泰国皇家政府公报」)是泰国政府的官方公报:法律、皇家法令和各机关的公告都在这里刊登,法律须经公报刊登才能生效。"
            "公报由内阁秘书处出版,官方网站是 ratchakitcha.soc.go.th,只有泰文、没有官方中文版。"
            "本站把其中与在泰华人相关的文件整理成中文摘要,每条附官方泰文原文链接。")

    facts = [("泰文名", "ราชกิจจานุเบกษา"),
             ("英文名", "Royal Thai Government Gazette(也作 Royal Gazette)"),
             ("常见中文译名", "泰国皇家公报、泰国政府公报、泰国皇家政府公报"),
             ("出版机关", "内阁秘书处(สำนักเลขาธิการคณะรัฐมนตรี,The Secretariat of the Cabinet)"),
             ("创刊", "1858 年 3 月 15 日"),
             ("语言", "泰文;没有官方中文版")]
    facts_html = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in facts)
    facts_html += (f'<dt>官方网站</dt><dd><a href="{OFFICIAL_SITE}" rel="noopener" target="_blank">'
                   f'ratchakitcha.soc.go.th</a>(泰文)</dd>')

    counts = ""
    if stats.get("gazette_total"):
        counts = (f'<p>本站目前收录的 <b>{stats["gazette_total"]}</b> 条公报文件里:ก 类 {n_k} 条,'
                  f'ง 类 {n_ng} 条(其中特刊 {n_special} 条)。</p>')

    cite = ""
    if ex:
        cite = (f'<h2 id="citation">怎么读公报编号</h2>'
                f'<p>本站每条公报文件都标有编号,写作「<b>{e(ex["doc_no"])}</b>」这样的形式:'
                f'{e(series_zh(ex["series"]))},第 {ex["volume"]} 卷(เล่ม)第 {e(ex["part"])} 期(ตอน)。'
                f'泰文原文里的写法是「<span lang="th">{e(thai_citation(ex["series"], ex["volume"], ex["part"]))}</span>」。'
                f'卷号每年递增一卷:{e(ex["date"][:4])} 年(佛历 {int(ex["date"][:4]) + 543} 年)是第 {ex["volume"]} 卷。</p>'
                f'<p>例:<a href="../{e(slug(ex["uid"]))}.html">{e(ex["title"])}</a>'
                f'({e(ex["date"])} 刊登,公报 {e(ex["doc_no"])})。拿着卷号、期号和类别,就能在官方网站上找到同一份 PDF。</p>')

    topics = " · ".join(f'<a href="../topic/{e(i)}.html">{e(zh)}({n})</a>' for i, zh, n in stats.get("topics") or [])
    colls = " · ".join(f'<a href="../../{e(x["href"])}">{e(x["zh"])}({x["n"]})</a>'
                       for x in stats.get("collections") or [])
    faq_html = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)

    body = f"""
<div class="crumb"><a href="../index.html">全部政策</a> / 指南</div>
<article class="card d-body" style="padding:26px 30px">
<h1 class="d-title">{GUIDE_TITLE}</h1>
<p class="lede">{e(lede)}</p>

<h2 id="facts">速览</h2>
<dl class="facts">{facts_html}</dl>

<h2 id="types">公报上刊登什么:四个类别</h2>
<p>公报按内容分成四类,编号里的泰文字母就是类别:</p>
<ul>
  <li><b>ก 类</b>(<span lang="th">ฉบับกฤษฎีกา</span>,法规类):宪法、法令(<span lang="th">พระราชบัญญัติ</span>)、紧急法令(<span lang="th">พระราชกำหนด</span>)、皇家法令(<span lang="th">พระราชกฤษฎีกา</span>)等有直接法律效力的文件。</li>
  <li><b>ข 类</b>(<span lang="th">ฉบับทะเบียนฐานันดร</span>):本站不收录。</li>
  <li><b>ค 类</b>(<span lang="th">ฉบับทะเบียนการค้า</span>,商业登记类):合伙与公司的设立、变更、撤销登记公告。本站不收录。</li>
  <li><b>ง 类</b>(<span lang="th">ฉบับประกาศและงานทั่วไป</span>,公告与一般事务类):不属于前三类的公告,各部委与机关的公告大多在这一类。编号里带「<span lang="th">พิเศษ</span>」的是特刊(<span lang="th">ตอนพิเศษ</span>)。</li>
</ul>
{counts}
{cite}
<h2 id="be">佛历与公历</h2>
<p>泰国官方文件使用佛历(<span lang="th">พ.ศ.</span>,英文 B.E.):<b>佛历年份 − 543 = 公历年份</b>,例如佛历 2569 年是公历 2026 年。
文件标题里常见的「<span lang="th">พ.ศ. 2569</span>」就是年份。本站的日期一律换算成公历。</p>

<h2 id="effective">刊登日不等于生效日</h2>
<p>什么时候生效,以每份文件自己的条款为准。常见的写法是「自公报刊登之日的次日起施行」,也有指定具体日期的。
本站把内阁决议日、公报刊登日、生效日、征求意见截止日分开记录;生效日来自文件正文,没读到正文的条目不填。</p>

<h2 id="cabinet">内阁决议和公报的区别</h2>
<p>内阁决议(<span lang="th">มติคณะรัฐมนตรี</span>)是内阁会议作出的决定。决议通过不等于规定已经生效:需要立法或发布公告的事项,
要等相应文件在公报上刊登。所以同一件事常常处在「决议已过、公报未刊、尚未生效」的状态。本站两者都收录,每条都标明是决议还是公报文件。</p>

<h2 id="where">在哪里查原文,有没有中文版</h2>
<ul>
  <li><b>官方原文</b>:<a href="{OFFICIAL_SITE}" rel="noopener" target="_blank">ratchakitcha.soc.go.th</a> 可以检索并下载每一期的 PDF,全部是泰文。</li>
  <li><b>开放数据</b>:泰国政府开放数据平台 <a href="{OPEN_DATA_SITE}" rel="noopener" target="_blank">data.go.th</a> 上有内阁秘书处维护的公报与内阁决议数据集,
    本站的数据主要来自这里;数据集按月批量开放,通常比刊登日晚几个月。</li>
  <li><b>中文</b>:公报没有官方中文版。本站提供非官方的中文标题、摘要与正文要点,目前共 <b>{stats.get("total", 0)}</b> 条,
    每条都附泰国政府网站(*.go.th)上的泰文原文链接,没有官方原文的内容不收录。译文仅供参考,以泰文原文为准,不构成法律或税务意见。</li>
</ul>
<p><b>按领域查</b> {topics}</p>
{f'<p><b>按专题查</b> {colls}</p>' if colls else ''}
<p><a href="../index.html">全部政策目录</a> · <a href="../week/index.html">按周汇总</a> · <a href="../../feed.xml">RSS 订阅</a> ·
<a href="../../about.html">关于本站与数据来源</a></p>

<h2 id="faq">常见问题</h2>
{faq_html}
<div class="disclaim">本页说明泰国皇家公报的一般情况与本站的整理方式,不构成法律意见;具体文件的效力与适用,以泰文原文为准。本站与泰国政府无隶属关系。</div>
</article>
<p style="margin-top:18px"><a href="../../index.html">← 返回政策脉络首页(检索、趋势、七维分析)</a></p>
"""
    ld = [
        {"@context": "https://schema.org", "@type": "Article", "headline": GUIDE_TITLE, "name": GUIDE_TITLE,
         "description": desc, "url": url, "mainEntityOfPage": url, "inLanguage": "zh-CN",
         "image": f"{site}/assets/og.png",
         "about": {"@type": "Thing", "name": "Royal Thai Government Gazette",
                   "alternateName": ["ราชกิจจานุเบกษา", "泰国皇家公报", "泰国政府公报"], "url": OFFICIAL_SITE},
         "author": {"@type": "Organization", "@id": f"{site}/#org", "name": SITE_NAME, "url": f"{site}/"},
         "publisher": {"@type": "Organization", "@id": f"{site}/#org", "name": SITE_NAME, "url": f"{site}/"},
         "isPartOf": {"@type": "WebSite", "@id": f"{site}/#website", "name": SITE_NAME, "url": f"{site}/"}},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "首页", "item": f"{site}/"},
             {"@type": "ListItem", "position": 2, "name": "全部政策", "item": f"{site}/p/index.html"},
             {"@type": "ListItem", "position": 3, "name": GUIDE_TITLE, "item": url}]},
    ]
    return _head(title, desc, url, ld, up="../../", og_type="article") + body + _foot("../../")
