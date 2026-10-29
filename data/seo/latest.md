# SEO / GEO 日报 · 2026-10-30

站点 https://www.thaipolicy.com · 生成于 2026-10-30T03:14:06+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 2 个,建议 3 个。
- Google 收录:已检查 673 页,确认收录 617 页(sitemap 共 673 页)。
- 近 7 天抓取:Googlebot 374 · Bingbot 450 · 百度 31 · AI 爬虫 485;来访:搜索 9 · AI 2。

## 待处理问题

- **🟠 需处理** `crawl_errors` 爬虫近两天遇到 2 个报错路径
  - 建议:404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志
  - 404 /p/th-gaz-20260326-2569.html(Googlebot,最近 2026-10-30)
  - 404 /sitemap.txt(Bingbot,最近 2026-10-29)
- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Add paid credit at https://console.perplexity.ai to upgrade your organization.
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🔵 建议** `gsc_not_indexed` 已检查 673 页,56 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/p/t/boi.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/data-protection.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/excise.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/financial-regulation.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/food-drug.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/import-control.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/land-property.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/social-security.html(已发现 - 尚未编入索引)
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `never_crawled` 20+ 个落地页近 7 天未被搜索爬虫抓取
  - 建议:增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交
  - /p/th-boi-20241010-136030.html
  - /p/th-boi-20241015-136054.html
  - /p/th-boi-20241024-136366.html
  - /p/th-boi-20241025-136110.html
  - /p/th-boi-20241101-136141.html
  - /p/th-boi-20241125-136239.html
  - /p/th-boi-20241209-136276.html
  - /p/th-boi-20241209-136277.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 1 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-rd-20261027-dgr315a.html

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 673  |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 1  |
| Google 已确认收录 | 617  |
| Google 已检查 | 673  |
| Google 曝光(28 天) | 368 (+13) |
| Google 点击(28 天) | 4  |
| Google 平均排名 | 10.3 (-0.2) |
| Bing 已收录 | 303 (+34) |
| Bing 曝光 | 45  |
| Googlebot 抓取(7 天) | 374 (-40) |
| Bingbot 抓取(7 天) | 450 (-33) |
| 百度蜘蛛抓取(7 天) | 31 (-7) |
| AI 爬虫抓取(7 天) | 485 (-123) |
| 落地页被搜索爬虫抓取占比 % | 60.4 (-3.1) |
| 搜索来源访问(7 天) | 9 (+1) |
| AI 来源访问(7 天) | 2  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 0 (-8) |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| 2569-2551 | 1 | 0 | 29 |
| chiang mai initiative multilateralisation (cmim) | 1 | 0 | 68 |
| pt99 | 1 | 0 | 100 |
| 泰國設廠 注意事項 | 1 | 0 | 68 |
| 泰國變更土地用途 注意事項 | 2 | 0 | 49.5 |
| 泰國變更土地用途 限制 | 13 | 0 | 54.2 |

## Google 收录状态分布(已检查页面)

- 已提交，且已编入索引:617
- 已发现 - 尚未编入索引:45
- Google 无法识别此网址:11

## Bing 搜索词

- 清迈倡议:曝光 4 · 点击 0
- 清迈倡议多边化（cmim）:曝光 3 · 点击 0
- 泰国发电厂烟气排放标准:曝光 2 · 点击 0
- 在清迈倡议多边化（cmim）:曝光 2 · 点击 0
- 原文：https://ratchakitcha.soc.go.th/documents/132451.pdf:曝光 2 · 点击 0
- sirps เกณฑ์:曝光 2 · 点击 0
- 《清迈倡议多边化》:曝光 2 · 点击 1
- 清迈协议:曝光 2 · 点击 0
- 《部令：规定工厂的类别、种类及规模，佛历 2563（2020）》:曝光 2 · 点击 0
- 泰国政府储蓄银行 維護通知书:曝光 2 · 点击 0

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 页面数 | 最近 |
|---|---|---|---|---|
| Applebot | 搜索 | 514 | 79 | 2026-10-30 |
| Bingbot | 搜索 | 450 | 252 | 2026-10-30 |
| Googlebot | 搜索 | 374 | 217 | 2026-10-30 |
| ClaudeBot | AI | 320 | 229 | 2026-10-30 |
| OAI-SearchBot | AI | 35 | 11 | 2026-10-30 |
| GPTBot | AI | 32 | 25 | 2026-10-29 |
| Baiduspider | 搜索 | 31 | 25 | 2026-10-26 |
| Meta-AI | AI | 30 | 24 | 2026-10-28 |
| PerplexityBot | AI | 14 | 11 | 2026-10-28 |
| ChatGPT-User | AI | 11 | 11 | 2026-10-28 |
| Amazonbot | AI | 8 | 8 | 2026-10-27 |
| Claude-SearchBot | AI | 7 | 6 | 2026-10-26 |
| DuckAssistBot | AI | 7 | 7 | 2026-10-26 |
| 360Spider | 搜索 | 6 | 1 | 2026-10-29 |
| CCBot | AI | 5 | 5 | 2026-10-26 |
| Perplexity-User | AI | 5 | 5 | 2026-10-26 |
| cohere-ai | AI | 5 | 5 | 2026-10-26 |
| Bytespider | AI | 4 | 3 | 2026-10-26 |
| Claude-User | AI | 2 | 2 | 2026-10-26 |

## 来访渠道(近 7 天)

- 搜索 · Bing:6
- 搜索 · Google:3
- AI · ChatGPT:2

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Add paid credit at https://console.perplexity.ai to upgrade your organization.

## 今日提交

- IndexNow:0 个 URL
- GSC sitemap:已存在
