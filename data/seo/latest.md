# SEO / GEO 日报 · 2026-10-13

站点 https://www.thaipolicy.com · 生成于 2026-10-13T03:15:39+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 2 个,建议 3 个。
- Google 收录:已检查 667 页,确认收录 332 页(sitemap 共 667 页)。
- 近 7 天抓取:Googlebot 539 · Bingbot 451 · 百度 4 · AI 爬虫 408;来访:搜索 1 · AI 0。

## 待处理问题

- **🟠 需处理** `crawl_errors` 爬虫近两天遇到 2 个报错路径
  - 建议:404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志
  - 404 /p/th-gaz-20260326-2569.html(Bingbot,ChatGPT-User,Googlebot,Meta-AI,最近 2026-10-12)
  - 410 /comments/feed/(Googlebot,最近 2026-10-12)
- **🟠 需处理** `gsc_not_indexed` 已检查 667 页,335 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/about.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/boi.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/data-protection.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/excise.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/financial-regulation.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/food-drug.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/import-control.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/land-property.html(已发现 - 尚未编入索引)
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
  - /p/th-boi-20241024-136366.html
  - /p/th-boi-20241025-136110.html
  - /p/th-boi-20241101-136141.html
  - /p/th-boi-20241101-136142.html
  - /p/th-boi-20241104-136149.html
  - /p/th-boi-20241118-136216.html
  - /p/th-boi-20241125-136239.html
  - /p/th-boi-20241209-136276.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 24 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-cabx-20241217-b149779c19.html
  - https://www.thaipolicy.com/p/th-cabx-20250107-cadb7e7b6c.html
  - https://www.thaipolicy.com/p/th-cabx-20250107-sme-beyond-sme.html
  - https://www.thaipolicy.com/p/th-cabx-20250113-2f8b31f8e8.html
  - https://www.thaipolicy.com/p/th-cabx-20250113-bdb9e408ef.html
  - https://www.thaipolicy.com/p/th-cabx-20250121-69ba3ee260.html
  - https://www.thaipolicy.com/p/th-cabx-20250121-carbon-pricing.html
  - https://www.thaipolicy.com/p/th-cabx-20250128-cctv-system.html
  - ……共 20 项,完整列表见 latest.json

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 667  |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 24 (+22) |
| Google 已确认收录 | 332 (+38) |
| Google 已检查 | 667 (+35) |
| Google 曝光(28 天) | 81 (+4) |
| Google 点击(28 天) | 0  |
| Google 平均排名 | 8.7 (+0.1) |
| Bing 已收录 | 178 (+23) |
| Bing 曝光 | 6  |
| Googlebot 抓取(7 天) | 539 (+70) |
| Bingbot 抓取(7 天) | 451 (-23) |
| 百度蜘蛛抓取(7 天) | 4  |
| AI 爬虫抓取(7 天) | 408 (+150) |
| 落地页被搜索爬虫抓取占比 % | 81.5 (+1.8) |
| 搜索来源访问(7 天) | 1  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 0  |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| 泰國變更土地用途 限制 | 2 | 0 | 50 |

## Google 收录状态分布(已检查页面)

- 已提交，且已编入索引:332
- 已发现 - 尚未编入索引:205
- Google 无法识别此网址:126
- 已抓取 - 尚未编入索引:3
- 服务器错误 (5xx):1

## Bing 搜索词

- 泰国发电厂烟气排放标准:曝光 2 · 点击 0
- 曼谷市政府网站所载《皇家公报》pdf。:曝光 1 · 点击 1
- 泰国 海关 公告 2569 关税 2026年10月:曝光 1 · 点击 0
- 泰国sure有限公司:曝光 1 · 点击 0
- 曼谷市政府网站所载《皇家公报》:曝光 1 · 点击 0

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 页面数 | 最近 |
|---|---|---|---|---|
| Applebot | 搜索 | 1837 | 362 | 2026-10-13 |
| Googlebot | 搜索 | 539 | 348 | 2026-10-13 |
| Bingbot | 搜索 | 451 | 238 | 2026-10-13 |
| Meta-AI | AI | 294 | 178 | 2026-10-12 |
| ClaudeBot | AI | 42 | 3 | 2026-10-11 |
| OAI-SearchBot | AI | 38 | 20 | 2026-10-12 |
| PerplexityBot | AI | 8 | 8 | 2026-10-11 |
| Baiduspider | 搜索 | 4 | 4 | 2026-10-11 |
| Bytespider | AI | 4 | 4 | 2026-10-11 |
| DuckAssistBot | AI | 4 | 4 | 2026-10-11 |
| GPTBot | AI | 4 | 4 | 2026-10-11 |
| Amazonbot | AI | 3 | 3 | 2026-10-11 |
| Claude-SearchBot | AI | 3 | 3 | 2026-10-11 |
| cohere-ai | AI | 3 | 3 | 2026-10-11 |
| 360Spider | 搜索 | 2 | 1 | 2026-10-11 |
| CCBot | AI | 2 | 2 | 2026-10-11 |
| ChatGPT-User | AI | 2 | 2 | 2026-10-11 |
| Claude-User | AI | 1 | 1 | 2026-10-11 |

## 来访渠道(近 7 天)

- 搜索 · Bing:1

## GEO 实测(Perplexity)

- ❌ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— 引用:kpmg.com, moscow.thaiembassy.org, thailand.go.th, thailand.prd.go.th, www.ey.com
- ❌ 泰国境外所得汇入课税新规有哪些豁免措施? —— 引用:flytorelocation.com, thailand.acclime.com, thethaiger.com, www.bdo.global, www.bdo.th
- ❌ 泰国代持股(Nominee)公司如何被排查?外国人买公寓的外资配额是多少? —— 引用:stanbrinkman.com, thailand.acclime.com, thailand.go.th, www.bdo.th, www.dbd.go.th
- ❌ 泰国 PDPA 个人资料跨境传输有什么要求? —— 引用:resourcehub.bakermckenzie.com, www.dlapiperdataprotection.com, www.lexology.com, www.nagashima.com, www.nishimura.com
- ❌ 泰国 LTR 长期居留签证的税务待遇是什么? —— 引用:globallawexperts.com, kpmg.com, ltr.boi.go.th, osos.boi.go.th, thethaiger.com
- ❌ 泰国 BOI 2026 投资促进措施有哪些?数据中心有什么税收激励? —— 引用:en.thairath.co.th, osos.boi.go.th, www.boi.go.th, www.luther-lawfirm.com, www.thebetter.co.th
- ❌ 泰国个人所得税 PND 90/91 和半年申报 PND 94 的截止日期是什么时候? —— 引用:en.thairath.co.th, phuket.thainotary.co.th, taxsummaries.pwc.com, thailand.go.th, vbapartners.com
- ❌ 在哪里可以查到泰国皇家公报政策的中文翻译和官方原文链接? —— 引用:data.go.th, lib-km.hcu.ac.th, ndlsearch.ndl.go.jp, ratchakitcha.soc.go.th, soc.gdcatalog.go.th
- 被引用最多的其他站点:www.thailand.go.th(4)、thailand.go.th(3)、www.nishimura.com(3)、kpmg.com(2)、www.rd.go.th(2)、www.chiangraitimes.com(2)、www.forvismazars.com(2)、www.bdo.global(2)

## 今日提交

- IndexNow:0 个 URL
- GSC sitemap:已存在
