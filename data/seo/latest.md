# SEO / GEO 日报 · 2026-11-21

站点 https://www.thaipolicy.com · 生成于 2026-11-21T03:14:15+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 1 个,建议 4 个。
- Google 收录(简体):已检查 835 页,确认收录 610 页(sitemap 里简体 1061 页)。
- Google 收录(繁体,单列):已检查 59 页,确认收录 8 页(sitemap 里繁体 1061 页)。
- 近 7 天抓取:Googlebot 1007 · Bingbot 1559 · 百度 30 · AI 爬虫 3665(其中成功取到页面 3585 次);来访:搜索 4 · AI 0。

## 待处理问题

- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🔵 建议** `gsc_hant_not_indexed` 已检查 59 个繁体页,51 页未被 Google 收录
  - 建议:繁体页是简体页的字形转换,新上线时收录慢属正常;先看简体页的收录情况,不必为繁体页单独加内链或改内容
  - https://www.thaipolicy.com/zh-hant/(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/about.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/index.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/t/boi.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/t/data-protection.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/t/energy.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/t/environment.html(Google 無法辨識的網址)
  - https://www.thaipolicy.com/zh-hant/p/t/ev-auto.html(Google 無法辨識的網址)
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `gsc_not_indexed` 已检查 835 个简体页,225 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/p/guide/royal-gazette.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/boi.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/data-protection.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/energy.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/environment.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/ev-auto.html(Google 无法识别此网址)
  - https://www.thaipolicy.com/p/t/excise.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/financial-regulation.html(已发现 - 尚未编入索引)
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `never_crawled` 20+ 个落地页近 7 天未被搜索爬虫抓取
  - 建议:增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交
  - /p/th-boi-20241220-136325.html
  - /p/th-boi-20250204-136531.html
  - /p/th-boi-20250218-136588.html
  - /p/th-boi-20250224-136611.html
  - /p/th-boi-20250722-137196.html
  - /p/th-boi-20250722-137199.html
  - /p/th-boi-20250808-137290.html
  - /p/th-boi-20251017-138054.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 1 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-gaz-20230620-2566.html

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 2122 (+512) |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 1 (+1) |
| Google 已确认收录(简体) | 610 (+4) |
| Google 已检查(简体) | 835 (+45) |
| Google 已确认收录(繁体) | 8 (+3) |
| Google 已检查(繁体) | 59 (+15) |
| Google 曝光(28 天) | 337 (-6) |
| Google 点击(28 天) | 11 (-1) |
| Google 平均排名 | 8.1  |
| Bing 已收录 | 580  |
| Bing 曝光 | 153  |
| Googlebot 抓取(7 天) | 1007 (+432) |
| Bingbot 抓取(7 天) | 1559 (+397) |
| 百度蜘蛛抓取(7 天) | 30  |
| AI 爬虫抓取(7 天) | 3665 (+876) |
| 搜索爬虫成功取到页面(7 天) | 2650 (+930) |
| AI 爬虫成功取到页面(7 天) | 3585 (+876) |
| 简体落地页被搜索爬虫抓取占比 % | 77.8 (+20.4) |
| 繁体落地页数(sitemap) | 969 (+255) |
| 繁体落地页被搜索爬虫抓取数 | 799 (+93) |
| 繁体成品可疑字形(处) | 0  |
| 搜索来源访问(7 天) | 4 (+2) |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 516 (+516) |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| dolwms.dol.go.th. 2 | 1 | 0 | 47 |
| pt99 | 1 | 0 | 100 |
| 泰國工業區 分佈 | 1 | 0 | 1 |
| 泰國變更土地用途 注意事項 | 1 | 0 | 65 |
| 泰國變更土地用途 限制 | 3 | 0 | 59 |

## Google 收录状态分布(已检查的简体页)

- 已提交，且已编入索引:610
- Google 无法识别此网址:114
- 已发现 - 尚未编入索引:111

## Google 收录状态分布(已检查的繁体页,单列)

- Google 無法辨識的網址:34
- 已找到 - 目前尚未建立索引:17
- 已提交並建立索引:8

## Bing 搜索词

- 泰国皇家政府公报:曝光 6 · 点击 1
- 清迈倡议:曝光 5 · 点击 0
- 泰国皇家公报:曝光 5 · 点击 1
- 清迈协议:曝光 4 · 点击 0
- 泰国政府公报网:曝光 4 · 点击 1
- 泰国政府公报百度百科:曝光 4 · 点击 0
- 清迈倡议多边化（cmim）:曝光 3 · 点击 0
- sirps เกณฑ์:曝光 3 · 点击 0
- 泰国政府公报:曝光 3 · 点击 0
- 泰国央行:曝光 3 · 点击 0

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 取到页面 | 不同地址数 | 最近 |
|---|---|---|---|---|---|
| GPTBot | AI | 2186 | 2147 | 2179 | 2026-11-20 |
| Bingbot | 搜索 | 1559 | 1519 | 1418 | 2026-11-21 |
| Meta-AI | AI | 1452 | 1431 | 1451 | 2026-11-20 |
| Googlebot | 搜索 | 1007 | 734 | 490 | 2026-11-21 |
| Applebot | 搜索 | 394 | 51 | 61 | 2026-11-21 |
| PetalBot | 搜索 | 279 | 277 | 257 | 2026-11-20 |
| YandexBot | 搜索 | 79 | 66 | 68 | 2026-11-19 |
| Baiduspider | 搜索 | 30 | 2 | 23 | 2026-11-17 |
| OAI-SearchBot | AI | 19 | 0 | 1 | 2026-11-21 |
| ChatGPT-User | AI | 6 | 6 | 4 | 2026-11-20 |
| DuckDuckBot | 搜索 | 3 | 1 | 3 | 2026-11-17 |
| PerplexityBot | AI | 2 | 1 | 2 | 2026-11-18 |

## 来访渠道(近 7 天)

- 搜索 · Google:4

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc

## 今日提交

- IndexNow:516 个 URL
- GSC sitemap:已存在
