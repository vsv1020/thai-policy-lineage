# SEO / GEO 日报 · 2026-09-29

站点 https://www.thaipolicy.com · 生成于 2026-09-29T03:15:04+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 3 个,建议 3 个。
- Google 收录:已检查 79 页,确认收录 6 页(sitemap 共 105 页)。
- 近 7 天抓取:Googlebot 111 · Bingbot 3 · 百度 0 · AI 爬虫 1;来访:搜索 0 · AI 0。

## 待处理问题

- **🟠 需处理** `crawl_errors` 爬虫遇到 3 个报错路径
  - 建议:404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志
  - 404 /comments/feed/(Googlebot)
  - 404 /favicon.ico(Googlebot)
  - 404 /feed(Googlebot)
- **🟠 需处理** `gsc_not_indexed` 已检查 79 页,73 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/p/index.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-2-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-2569-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-2569.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-33-2569-1974-2.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-33-39.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-39-2569-revised-recommendations-for.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/th-gaz-20260401-4-2569-14.html(已发现 - 尚未编入索引)
  - ……共 20 项,完整列表见 latest.json
- **🟠 需处理** `page:description 过短` 1 个页面:description 过短
  - 建议:落地页模板在 backend/app/seo.py 的 render_page / _head
  - https://www.thaipolicy.com/p/th-gaz-20260403-3-2569.html
- **🔵 建议** `geo_not_cited` 5 个实测问题的 AI 回答都没有引用本站
  - 建议:对照被引用的来源(见 GEO 一节),补对应主题的专题页与问答式要点;确保 Bing 已收录
  - 泰国最新的签证政策有哪些变化?
  - 泰国对境外所得汇入征税的规定是什么?
  - 泰国外国人持有公司股份有什么限制?
  - 泰国最低工资最新标准是多少?
  - 在哪里可以查到泰国皇家公报的中文翻译?
- **🔵 建议** `never_crawled` 20+ 个落地页近 7 天未被搜索爬虫抓取
  - 建议:增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交
  - /p/index.html
  - /p/th-gaz-20260302-2-2569.html
  - /p/th-gaz-20260302-2552-2569.html
  - /p/th-gaz-20260302-2555-2569.html
  - /p/th-gaz-20260302-3-2569-2.html
  - /p/th-gaz-20260302-804-2569.html
  - /p/th-gaz-20260302-805-2569.html
  - /p/th-gaz-20260401-2-2569.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 20 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-gaz-20260422-fd1263e0ac.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-9-2568.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-5-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260422-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260302-2-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260302-2552-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260302-2555-2569.html
  - https://www.thaipolicy.com/p/th-gaz-20260302-3-2569-2.html
  - ……共 20 项,完整列表见 latest.json

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 105 (+86) |
| 今日抽查页数 | 40 (+21) |
| 抽查有问题页数 | 1 (+1) |
| 内容单薄页数(抽查) | 20 (+8) |
| Google 已确认收录 | 6 (+3) |
| Google 已检查 | 79 (+60) |
| Google 曝光(28 天) | 0  |
| Google 点击(28 天) | 0  |
| Bing 曝光 | 0  |
| Googlebot 抓取(7 天) | 111 (+46) |
| Bingbot 抓取(7 天) | 3  |
| 百度蜘蛛抓取(7 天) | 0  |
| AI 爬虫抓取(7 天) | 1 (+1) |
| 落地页被搜索爬虫抓取占比 % | 8.7 (-8.9) |
| 搜索来源访问(7 天) | 0  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 92 (+92) |

## Google 收录状态分布(已检查页面)

- 已发现 - 尚未编入索引:54
- Google 无法识别此网址:19
- 已提交，且已编入索引:6

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 页面数 | 最近 |
|---|---|---|---|---|
| Googlebot | 搜索 | 111 | 39 | 2026-09-29 |
| Applebot | 搜索 | 65 | 22 | 2026-09-27 |
| Bingbot | 搜索 | 3 | 3 | 2026-09-27 |
| OAI-SearchBot | AI | 1 | 1 | 2026-09-28 |

## GEO 实测(Perplexity)

- ❌ 泰国最新的签证政策有哪些变化? —— 引用:buenos-aires.thaiembassy.org, colombo.thaiembassy.org, hongkong.thaiembassy.org, london.thaiembassy.org, newyork.thaiembassy.org
- ❌ 泰国对境外所得汇入征税的规定是什么? —— 引用:assets.kpmg.com, globallawexperts.com, kpmg.com, taxsummaries.pwc.com, www.dfdl.com
- ❌ 泰国外国人持有公司股份有什么限制? —— 引用:corporate.findlaw.com, houseviser.com, th.usembassy.gov, www.boi.go.th, www.lorenz-partners.com
- ❌ 泰国最低工资最新标准是多少? —— 引用:knowledge.dlapiper.com, www.bdo.th, www.chiangraitimes.com, www.forvismazars.com, www.ilct.co.th
- ❌ 在哪里可以查到泰国皇家公报的中文翻译? —— 引用:dbpedia.org, de.wikipedia.org, en.wikipedia-on-ipfs.org, en.wikipedia.org, lawcat.berkeley.edu
- 被引用最多的其他站点:www.nishimura.com(3)、th.usembassy.gov(2)、www.thailawonline.com(2)、tehran.thaiembassy.org(1)、buenos-aires.thaiembassy.org(1)、colombo.thaiembassy.org(1)、thaiconsulatela.thaiembassy.org(1)、london.thaiembassy.org(1)

## 今日提交

- IndexNow:92 个 URL
- GSC sitemap:已存在
