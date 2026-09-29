# SEO / GEO 日报 · 2026-09-29

站点 https://www.thaipolicy.com · 生成于 2026-09-29T20:24:10+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 2 个,建议 3 个。
- Google 收录:已检查 139 页,确认收录 15 页(sitemap 共 194 页)。
- 近 7 天抓取:Googlebot 279 · Bingbot 46 · 百度 0 · AI 爬虫 2;来访:搜索 0 · AI 0。

## 待处理问题

- **🟠 需处理** `crawl_errors` 爬虫近两天遇到 2 个报错路径
  - 建议:404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志
  - 404 /comments/feed/(Googlebot,最近 2026-09-28)
  - 404 /feed(Googlebot,最近 2026-09-28)
- **🟠 需处理** `gsc_not_indexed` 已检查 139 页,124 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/p/index.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260302-2-2569.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/th-gaz-20260302-2552-2569.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/th-gaz-20260302-2555-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260302-3-2569-2.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260302-804-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260302-805-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-2-2569.html(已发现 - 尚未编入索引)
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `geo_not_cited` 8 个实测问题的 AI 回答都没有引用本站
  - 建议:对照被引用的来源(见 GEO 一节),补对应主题的专题页与问答式要点;确保 Bing 已收录
  - 泰国免签停留期最近有什么调整?内阁决议和公报是否一致?
  - 泰国境外所得汇入课税新规有哪些豁免措施?
  - 泰国代持股(Nominee)公司如何被排查?外国人买公寓的外资配额是多少?
  - 泰国 PDPA 个人资料跨境传输有什么要求?
  - 泰国 LTR 长期居留签证的税务待遇是什么?
  - 泰国 BOI 2026 投资促进措施有哪些?数据中心有什么税收激励?
  - 泰国个人所得税 PND 90/91 和半年申报 PND 94 的截止日期是什么时候?
  - 在哪里可以查到泰国皇家公报政策的中文翻译和官方原文链接?
- **🔵 建议** `never_crawled` 20+ 个落地页近 7 天未被搜索爬虫抓取
  - 建议:增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交
  - /p/th-gaz-20260302-2555-2569.html
  - /p/th-gaz-20260302-3-2569-2.html
  - /p/th-gaz-20260304-2-122-2568.html
  - /p/th-gaz-20260304-2-54-2568.html
  - /p/th-gaz-20260304-2-6-2568.html
  - /p/th-gaz-20260304-2-95-2568.html
  - /p/th-gaz-20260304-2568.html
  - /p/th-gaz-20260305-2-l-2568.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 18 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-gaz-20260422-fd1263e0ac.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-9-2568.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-5-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260305-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260306-2541-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260306-wto-2569-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260310-118.html
  - ……共 18 项,完整列表见 latest.json

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 194 (+175) |
| 今日抽查页数 | 40 (+21) |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 18 (+6) |
| Google 已确认收录 | 15 (+12) |
| Google 已检查 | 139 (+120) |
| Google 曝光(28 天) | 0  |
| Google 点击(28 天) | 0  |
| Bing 曝光 | 0  |
| Googlebot 抓取(7 天) | 279 (+214) |
| Bingbot 抓取(7 天) | 46 (+43) |
| 百度蜘蛛抓取(7 天) | 0  |
| AI 爬虫抓取(7 天) | 2 (+2) |
| 落地页被搜索爬虫抓取占比 % | 46.9 (+29.3) |
| 搜索来源访问(7 天) | 0  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 89 (+89) |

## Google 收录状态分布(已检查页面)

- Google 无法识别此网址:69
- 已发现 - 尚未编入索引:54
- 已提交，且已编入索引:15
- 已抓取 - 尚未编入索引:1

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 页面数 | 最近 |
|---|---|---|---|---|
| Googlebot | 搜索 | 279 | 99 | 2026-09-29 |
| Applebot | 搜索 | 65 | 22 | 2026-09-27 |
| Bingbot | 搜索 | 46 | 43 | 2026-09-29 |
| OAI-SearchBot | AI | 2 | 1 | 2026-09-29 |
| YandexBot | 搜索 | 2 | 2 | 2026-09-29 |

## GEO 实测(Perplexity)

- ❌ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— 引用:bsb.thaiembassy.org, indianexpress.com, moscow.thaiembassy.org, tdac.info, thailand.go.th
- ❌ 泰国境外所得汇入课税新规有哪些豁免措施? —— 引用:flytorelocation.com, globallawexperts.com, houseviser.com, rumavi.com, thailand.acclime.com
- ❌ 泰国代持股(Nominee)公司如何被排查?外国人买公寓的外资配额是多少? —— 引用:stanbrinkman.com, thethaiger.com, world.thaipbs.or.th, www.dbd.go.th, www.nationthailand.com
- ❌ 泰国 PDPA 个人资料跨境传输有什么要求? —— 引用:assets.kpmg.com, fpf.org, pdpathailand.com, resourcehub.bakermckenzie.com, www.aseanbriefing.com
- ❌ 泰国 LTR 长期居留签证的税务待遇是什么? —— 引用:assets.kpmg.com, ltr.boi.go.th, pattayavisahelp.com, phnompenh.thaiembassy.org, rumavi.com
- ❌ 泰国 BOI 2026 投资促进措施有哪些?数据中心有什么税收激励? —— 引用:osos.boi.go.th, www.boi.go.th
- ❌ 泰国个人所得税 PND 90/91 和半年申报 PND 94 的截止日期是什么时候? —— 引用:franklegaltax.com, houseviser.com, movetothai.land, phuketexpatguide.com, sherrings.com
- ❌ 在哪里可以查到泰国皇家公报政策的中文翻译和官方原文链接? —— 引用:dhaka.thaiembassy.org, en.wikipedia.org, hongkong.thaiembassy.org, tehran.thaiembassy.org, th.china-embassy.gov.cn
- 被引用最多的其他站点:www.thailawonline.com(4)、thethaiger.com(3)、www.nationthailand.com(2)、www.cero.agency(2)、www.forvismazars.com(2)、houseviser.com(2)、rumavi.com(2)、www.nishimura.com(2)

## 今日提交

- IndexNow:89 个 URL
- GSC sitemap:已存在
