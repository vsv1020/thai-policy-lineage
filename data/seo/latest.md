# SEO / GEO 日报 · 2026-11-14

站点 https://www.thaipolicy.com · 生成于 2026-11-14T03:14:04+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 2 个,建议 3 个。
- Google 收录:已检查 679 页,确认收录 618 页(sitemap 共 679 页)。
- 近 7 天抓取:Googlebot 365 · Bingbot 341 · 百度 54 · AI 爬虫 322;来访:搜索 5 · AI 0。

## 待处理问题

- **🟠 需处理** `crawl_errors` 爬虫近两天遇到 7 个报错路径
  - 建议:404 通常是删掉的旧页面(可在 nginx 加 301)或错误链接;5xx 查服务器日志
  - 404 /userfiles(Bingbot,ChatGPT-User,DuckAssistBot,PerplexityBot,cohere-ai,最近 2026-11-13)
  - 404 /cgi-bin/php(Baiduspider,Bytespider,cohere-ai,最近 2026-11-13)
  - 404 /index.php(Bytespider,Claude-SearchBot,Claude-User,最近 2026-11-13)
  - 404 /config.json(OAI-SearchBot,最近 2026-11-13)
  - 404 /_debugbar/open(Amazonbot,Claude-User,最近 2026-11-13)
  - 404 /cgi-bin/php-cgi(Bytespider,OAI-SearchBot,最近 2026-11-13)
  - 404 /core/settings.py(Amazonbot,Googlebot,最近 2026-11-13)
- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🔵 建议** `gsc_not_indexed` 已检查 679 页,61 页未被 Google 收录
  - 建议:「已发现-尚未编入索引」多为权重/内链不足:加内链、丰富内容;「已抓取-尚未编入索引」多为内容单薄或重复
  - https://www.thaipolicy.com/p/t/boi.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/data-protection.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/excise.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/financial-regulation.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/food-drug.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/import-control.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/land-property.html(已发现 - 尚未编入索引)
  - https://www.thaipolicy.com/p/t/social-security.html(Google 无法识别此网址)
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `never_crawled` 20+ 个落地页近 7 天未被搜索爬虫抓取
  - 建议:增加站内链接(首页、专题页、同领域推荐);新页面已通过 IndexNow 与 GSC sitemap 提交
  - /p/th-boi-20241010-136030.html
  - /p/th-boi-20241101-136141.html
  - /p/th-boi-20241101-136142.html
  - /p/th-boi-20241104-136149.html
  - /p/th-boi-20241125-136238.html
  - /p/th-boi-20241125-136239.html
  - /p/th-boi-20241209-136279.html
  - /p/th-boi-20241220-136327.html
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `thin_content` 抽查的 40 页中有 1 页摘要只依据标题(内容单薄)
  - 建议:单薄页面难以获得排名与 AI 引用:给 enrich 增加读取公报 PDF 正文的步骤,生成有实质内容的摘要与要点
  - https://www.thaipolicy.com/p/th-gaz-20260205-46-2568-grid-code.html

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 679  |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 1 (+1) |
| Google 已确认收录 | 618  |
| Google 已检查 | 679  |
| Google 曝光(28 天) | 367 (-20) |
| Google 点击(28 天) | 11 (-1) |
| Google 平均排名 | 9.4 (+0.1) |
| Bing 已收录 | 510 (+5) |
| Bing 曝光 | 111  |
| Googlebot 抓取(7 天) | 365 (+6) |
| Bingbot 抓取(7 天) | 341 (+13) |
| 百度蜘蛛抓取(7 天) | 54 (+15) |
| AI 爬虫抓取(7 天) | 322 (+236) |
| 落地页被搜索爬虫抓取占比 % | 35.3 (-1.2) |
| 搜索来源访问(7 天) | 5  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 0  |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| 2569-2551 | 1 | 0 | 29 |
| chiang mai initiative multilateralisation (cmim) | 1 | 0 | 68 |
| dolwms.dol.go.th. 2 | 1 | 0 | 47 |
| pt99 | 1 | 0 | 100 |
| 泰國工業區 分佈 | 1 | 0 | 1 |
| 泰國變更土地用途 注意事項 | 2 | 0 | 49.5 |
| 泰國變更土地用途 限制 | 8 | 0 | 55.4 |

## Google 收录状态分布(已检查页面)

- 已提交，且已编入索引:618
- 已发现 - 尚未编入索引:49
- Google 无法识别此网址:12

## Bing 搜索词

- 清迈倡议:曝光 5 · 点击 0
- 清迈协议:曝光 4 · 点击 0
- 泰国政府公报网:曝光 4 · 点击 1
- 泰国皇家政府公报:曝光 4 · 点击 1
- 清迈倡议多边化（cmim）:曝光 3 · 点击 0
- sirps เกณฑ์:曝光 3 · 点击 0
- 泰国皇家公报:曝光 3 · 点击 0
- 泰国发电厂烟气排放标准:曝光 2 · 点击 0
- 原文：https://ratchakitcha.soc.go.th/documents/132451.pdf:曝光 2 · 点击 0
- 在清迈倡议多边化（cmim）:曝光 2 · 点击 0

## 爬虫抓取(近 7 天)

| 爬虫 | 类型 | 次数 | 页面数 | 最近 |
|---|---|---|---|---|
| Googlebot | 搜索 | 365 | 186 | 2026-11-14 |
| Bingbot | 搜索 | 341 | 170 | 2026-11-14 |
| Applebot | 搜索 | 148 | 41 | 2026-11-14 |
| Baiduspider | 搜索 | 54 | 44 | 2026-11-13 |
| Meta-AI | AI | 54 | 42 | 2026-11-13 |
| OAI-SearchBot | AI | 53 | 25 | 2026-11-14 |
| GPTBot | AI | 38 | 32 | 2026-11-13 |
| cohere-ai | AI | 26 | 26 | 2026-11-13 |
| ChatGPT-User | AI | 21 | 21 | 2026-11-13 |
| CCBot | AI | 20 | 20 | 2026-11-13 |
| Bytespider | AI | 19 | 19 | 2026-11-13 |
| Perplexity-User | AI | 18 | 18 | 2026-11-13 |
| Claude-User | AI | 17 | 17 | 2026-11-13 |
| DuckAssistBot | AI | 14 | 14 | 2026-11-13 |
| PerplexityBot | AI | 14 | 14 | 2026-11-13 |
| Claude-SearchBot | AI | 13 | 13 | 2026-11-13 |
| Amazonbot | AI | 9 | 9 | 2026-11-13 |
| ClaudeBot | AI | 6 | 6 | 2026-11-13 |

## 来访渠道(近 7 天)

- 搜索 · Bing:4
- 搜索 · Google:1

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc

## 今日提交

- IndexNow:0 个 URL
- GSC sitemap:已存在
