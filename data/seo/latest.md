# SEO / GEO 日报 · 2026-11-26

站点 https://www.thaipolicy.com · 生成于 2026-11-26T03:14:24+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 1 个,建议 4 个。
- Google 收录(简体):已检查 1074 页,确认收录 711 页(sitemap 里简体 2771 页)。
- Google 收录(繁体,单列):已检查 134 页,确认收录 62 页(sitemap 里繁体 2771 页)。
- 近 7 天抓取:Googlebot 6717 · Bingbot 5537 · 百度 63 · AI 爬虫 14790(其中成功取到页面 14675 次);来访:搜索 9 · AI 0。

## 待处理问题

- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🔵 建议** `gsc_hant_not_indexed` 已检查 134 个繁体页,72 页未被 Google 收录
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
- **🔵 建议** `gsc_not_indexed` 已检查 1074 个简体页,363 页未被 Google 收录
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
  - /p/th-boi-20241209-136276.html
  - /p/th-boi-20250714-137152.html
  - /p/th-boi-20260105-138395.html
  - /p/th-cabx-20241129-50-2561-30-2567.html
  - /p/th-cabx-20241129-d20efa630b.html
  - /p/th-cabx-20241129-f67e3452ee.html
  - /p/th-cabx-20241129-pm2-5.html
  - /p/th-cabx-20241203-1-4000-one-map-4.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 1 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-cabx-20241224-2569-2572.html

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 5542  |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 1 (+1) |
| Google 已确认收录(简体) | 711 (+26) |
| Google 已检查(简体) | 1074 (+45) |
| Google 已确认收录(繁体) | 62 (+10) |
| Google 已检查(繁体) | 134 (+15) |
| Google 曝光(28 天) | 444 (+81) |
| Google 点击(28 天) | 14 (-2) |
| Google 平均排名 | 8.0 (-0.7) |
| Bing 已收录 | 3287 (+275) |
| Bing 曝光 | 193  |
| Googlebot 抓取(7 天) | 6717 (-85) |
| Bingbot 抓取(7 天) | 5537 (-77) |
| 百度蜘蛛抓取(7 天) | 63 (+63) |
| AI 爬虫抓取(7 天) | 14790 (-618) |
| 搜索爬虫成功取到页面(7 天) | 15743 (+575) |
| AI 爬虫成功取到页面(7 天) | 14675 (-604) |
| 简体落地页被搜索爬虫抓取占比 % | 92.8 (+0.8) |
| 繁体落地页数(sitemap) | 2626  |
| 繁体落地页被搜索爬虫抓取数 | 2448 (+63) |
| 繁体成品可疑字形(处) | 0  |
| 搜索来源访问(7 天) | 9  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 0 (-4) |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| apex green industrial estate | 1 | 0 | 3 |
| dolwms.dol.go.th. 2 | 1 | 0 | 47 |
| royal thai government gazette | 1 | 0 | 10 |
| タイ boi 条件違反 | 1 | 0 | 18 |
| 泰国皇家公报 | 1 | 0 | 6 |
| 泰國工業區 分佈 | 1 | 0 | 1 |
| 泰國變更土地用途 注意事項 | 1 | 0 | 65 |
| 泰國變更土地用途 申請 | 1 | 0 | 3 |
| 泰國變更土地用途 申請程序 | 6 | 0 | 34.3 |
| 泰國變更土地用途 限制 | 1 | 0 | 49 |
| 泰國電子產業 稅務優惠 | 4 | 0 | 63.8 |

## Google 收录状态分布(已检查的简体页)

- 已提交，且已编入索引:711
- Google 无法识别此网址:226
- 已发现 - 尚未编入索引:137

## Google 收录状态分布(已检查的繁体页,单列)

- 已提交並建立索引:62
- Google 無法辨識的網址:40
- 已找到 - 目前尚未建立索引:32

## Bing 搜索词

- 泰国皇家政府公报:曝光 6 · 点击 1
- 清迈倡议:曝光 5 · 点击 0
- 泰国皇家公报:曝光 5 · 点击 1
- 清迈协议:曝光 4 · 点击 0
- 泰国政府公报网:曝光 4 · 点击 1
- 泰国政府公报百度百科:曝光 4 · 点击 0
- 泰国央行:曝光 4 · 点击 0
- boi第sor.3/2569号公告:曝光 4 · 点击 0
- 清迈倡议多边化（cmim）:曝光 3 · 点击 0
- sirps เกณฑ์:曝光 3 · 点击 0

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 取到页面 | 不同地址数 | 最近 |
|---|---|---|---|---|---|
| Googlebot | 搜索 | 6717 | 5749 | 3851 | 2026-11-26 |
| Bingbot | 搜索 | 5537 | 5424 | 2994 | 2026-11-26 |
| ClaudeBot | AI | 5437 | 5408 | 5431 | 2026-11-25 |
| PetalBot | 搜索 | 4076 | 4055 | 3483 | 2026-11-26 |
| GPTBot | AI | 3900 | 3880 | 3893 | 2026-11-25 |
| Meta-AI | AI | 3841 | 3818 | 3827 | 2026-11-24 |
| OAI-SearchBot | AI | 1590 | 1550 | 1560 | 2026-11-26 |
| Applebot | 搜索 | 1381 | 396 | 416 | 2026-11-26 |
| YandexBot | 搜索 | 115 | 106 | 104 | 2026-11-24 |
| Baiduspider | 搜索 | 63 | 12 | 33 | 2026-11-26 |
| ChatGPT-User | AI | 17 | 17 | 17 | 2026-11-26 |
| PerplexityBot | AI | 5 | 2 | 4 | 2026-11-23 |
| DuckDuckBot | 搜索 | 3 | 1 | 3 | 2026-11-21 |

## 来访渠道(近 7 天)

- 搜索 · Google:5
- 搜索 · Bing:4

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc

## 今日提交

- IndexNow:0 个 URL
- GSC sitemap:已存在
