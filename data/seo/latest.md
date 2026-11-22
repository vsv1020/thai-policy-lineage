# SEO / GEO 日报 · 2026-11-23

站点 https://www.thaipolicy.com · 生成于 2026-11-23T03:14:25+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 1 个,建议 4 个。
- Google 收录(简体):已检查 939 页,确认收录 634 页(sitemap 里简体 2756 页)。
- Google 收录(繁体,单列):已检查 89 页,确认收录 27 页(sitemap 里繁体 2756 页)。
- 近 7 天抓取:Googlebot 4815 · Bingbot 4018 · 百度 9 · AI 爬虫 10496(其中成功取到页面 10397 次);来访:搜索 5 · AI 0。

## 待处理问题

- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🔵 建议** `gsc_hant_not_indexed` 已检查 89 个繁体页,62 页未被 Google 收录
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
- **🔵 建议** `gsc_not_indexed` 已检查 939 个简体页,305 页未被 Google 收录
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
  - /p/th-boi-20241010-136030.html
  - /p/th-boi-20241015-136054.html
  - /p/th-boi-20241101-136141.html
  - /p/th-boi-20241209-136276.html
  - /p/th-boi-20250131-136524.html
  - /p/th-boi-20250218-136588.html
  - /p/th-boi-20250409-136809.html
  - /p/th-boi-20250605-137010.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 1 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-cabx-20241203-2569-98cf5128.html

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 5512  |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 1 (+1) |
| Google 已确认收录(简体) | 634 (+13) |
| Google 已检查(简体) | 939 (+48) |
| Google 已确认收录(繁体) | 27 (+11) |
| Google 已检查(繁体) | 89 (+15) |
| Google 曝光(28 天) | 344 (+8) |
| Google 点击(28 天) | 13 (+2) |
| Google 平均排名 | 8.7 (+0.3) |
| Bing 已收录 | 739 (+147) |
| Bing 曝光 | 193  |
| Googlebot 抓取(7 天) | 4815 (+3012) |
| Bingbot 抓取(7 天) | 4018 (+659) |
| 百度蜘蛛抓取(7 天) | 9  |
| AI 爬虫抓取(7 天) | 10496 (+6224) |
| 搜索爬虫成功取到页面(7 天) | 9606 (+4095) |
| AI 爬虫成功取到页面(7 天) | 10397 (+6208) |
| 简体落地页被搜索爬虫抓取占比 % | 85.9 (+5.7) |
| 繁体落地页数(sitemap) | 2611 (+423) |
| 繁体落地页被搜索爬虫抓取数 | 1797 (+583) |
| 繁体成品可疑字形(处) | 0 (-36) |
| 搜索来源访问(7 天) | 5 (+1) |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 856 (-1730) |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| dolwms.dol.go.th. 2 | 1 | 0 | 47 |
| 泰國工業區 分佈 | 1 | 0 | 1 |
| 泰國變更土地用途 注意事項 | 1 | 0 | 65 |
| 泰國變更土地用途 申請程序 | 2 | 0 | 34 |
| 泰國變更土地用途 限制 | 1 | 0 | 49 |
| 泰國電子產業 稅務優惠 | 2 | 0 | 64.5 |

## Google 收录状态分布(已检查的简体页)

- 已提交，且已编入索引:634
- Google 无法识别此网址:194
- 已发现 - 尚未编入索引:111

## Google 收录状态分布(已检查的繁体页,单列)

- Google 無法辨識的網址:38
- 已提交並建立索引:27
- 已找到 - 目前尚未建立索引:24

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
| GPTBot | AI | 5524 | 5484 | 5517 | 2026-11-22 |
| Meta-AI | AI | 4909 | 4877 | 4898 | 2026-11-22 |
| Googlebot | 搜索 | 4815 | 4124 | 2966 | 2026-11-23 |
| Bingbot | 搜索 | 4018 | 3923 | 3140 | 2026-11-23 |
| PetalBot | 搜索 | 1431 | 1418 | 1318 | 2026-11-23 |
| YandexBot | 搜索 | 142 | 125 | 125 | 2026-11-22 |
| Applebot | 搜索 | 128 | 13 | 23 | 2026-11-21 |
| OAI-SearchBot | AI | 53 | 29 | 30 | 2026-11-23 |
| Baiduspider | 搜索 | 9 | 1 | 9 | 2026-11-17 |
| DuckDuckBot | 搜索 | 6 | 2 | 3 | 2026-11-21 |
| ChatGPT-User | AI | 5 | 5 | 5 | 2026-11-22 |
| PerplexityBot | AI | 5 | 2 | 4 | 2026-11-22 |

## 来访渠道(近 7 天)

- 搜索 · Google:5

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc

## 今日提交

- IndexNow:856 个 URL
- GSC sitemap:已存在
