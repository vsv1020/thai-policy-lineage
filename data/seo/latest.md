# SEO / GEO 日报 · 2026-11-22

站点 https://www.thaipolicy.com · 生成于 2026-11-22T03:14:16+07:00(曼谷时间)。本文件由 `python -m app.seo_monitor` 生成,每日例行会话据此修改站点。

## 结论

- 严重问题 0 个,需处理 3 个,建议 3 个。
- Google 收录(简体):已检查 891 页,确认收录 621 页(sitemap 里简体 2328 页)。
- Google 收录(繁体,单列):已检查 74 页,确认收录 16 页(sitemap 里繁体 2328 页)。
- 近 7 天抓取:Googlebot 1803 · Bingbot 3359 · 百度 9 · AI 爬虫 4272(其中成功取到页面 4189 次);来访:搜索 4 · AI 0。

## 待处理问题

- **🟠 需处理** `deploy_lag` 仓库里有 856 个页面线上还没有(服务器未同步)
  - 建议:服务器每小时跑 deploy/sync.sh;持续出现说明 cron 失效或导出报错,看 /var/log/thai-policy-sync.log
  - https://www.thaipolicy.com/p/th-cabx-20241129-1c9f2f6e21.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-20.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-2566-0adfe5c0.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-2567-68-3cc11ab7.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-2567-68-ebf2b7ff.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-2567-68.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-2568.html
  - https://www.thaipolicy.com/p/th-cabx-20241129-50-2561-30-2567.html
  - ……共 20 项,完整列表见 latest.json
- **🟠 需处理** `geo_api` Perplexity 接口返回 403:The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc
  - 建议:按上面接口返回的原因处理。常见:账户没有可用额度(没绑卡/没充值)、Key 被停用,或接口已变更(需要改 seo_monitor.py 里的 PPLX_URL / 请求格式)
- **🟠 需处理** `hant_suspicious` 繁体版有 36 处可疑字形(s2tw 转换可能出错)
  - 建议:逐条核对;错的在 config/hant.json 的 rules 里补带上下文的规则并在 tests/test_hant.py 补例句,是正确用法就收紧 suspicious 里的模式;改完重新导出,python -m app.hant --check 零命中
  - p/index.html:「家」被拆进「家具 / 家私」(专家具备、国家具有、一家私人);「傢伙」不算 —— 受邀請成為金磚國傢夥伴國（BRIC
  - p/index.html:签/表/斗/制的常见拆词错误 —— 安全要求的議定書籤署事宜</a></
  - p/t/food-drug.html:签/表/斗/制的常见拆词错误 —— 安全要求的議定書籤署事宜"}, {"
  - p/t/food-drug.html:签/表/斗/制的常见拆词错误 —— 安全要求的議定書籤署事宜</a></
  - p/th-boi-20241220-136327.html:「家」被拆进「家具 / 家私」(专家具备、国家具有、一家私人);「傢伙」不算 —— 受邀請成為金磚國傢夥伴國（BRIC
  - p/th-cabx-20241217-4b229ce42b.html:签/表/斗/制的常见拆词错误 —— 並更新法令附圖中籤署人姓名，並採納自
  - p/th-cabx-20241224-710abf5243.html:「家」被拆进「家具 / 家私」(专家具备、国家具有、一家私人);「傢伙」不算 —— 受邀請成為金磚國傢夥伴國（BRIC
  - p/th-cabx-20241224-711f707c76.html:「家」被拆进「家具 / 家私」(专家具备、国家具有、一家私人);「傢伙」不算 —— 受邀請成為金磚國傢夥伴國（BRIC
  - ……共 20 项,完整列表见 latest.json
- **🔵 建议** `gsc_hant_not_indexed` 已检查 74 个繁体页,58 页未被 Google 收录
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
- **🔵 建议** `gsc_not_indexed` 已检查 891 个简体页,270 页未被 Google 收录
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
  - /p/th-boi-20241209-136276.html
  - /p/th-boi-20241209-136277.html
  - /p/th-boi-20250131-136524.html
  - /p/th-boi-20250204-136531.html
  - /p/th-boi-20250218-136588.html
  - /p/th-boi-20250228-136638.html
  - /p/th-boi-20250605-137010.html
  - ……共 20 项,完整列表见 latest.json

## 关键指标(括号内为较前一日变化)

| 指标 | 今日 |
|---|---|
| sitemap 页面数 | 5512 (+3390) |
| 今日抽查页数 | 40  |
| 抽查有问题页数 | 0  |
| 内容单薄页数(抽查) | 0 (-1) |
| Google 已确认收录(简体) | 621 (+11) |
| Google 已检查(简体) | 891 (+56) |
| Google 已确认收录(繁体) | 16 (+8) |
| Google 已检查(繁体) | 74 (+15) |
| Google 曝光(28 天) | 336 (-1) |
| Google 点击(28 天) | 11  |
| Google 平均排名 | 8.4 (+0.3) |
| Bing 已收录 | 592 (+12) |
| Bing 曝光 | 193 (+40) |
| Googlebot 抓取(7 天) | 1803 (+796) |
| Bingbot 抓取(7 天) | 3359 (+1800) |
| 百度蜘蛛抓取(7 天) | 9 (-21) |
| AI 爬虫抓取(7 天) | 4272 (+607) |
| 搜索爬虫成功取到页面(7 天) | 5511 (+2861) |
| AI 爬虫成功取到页面(7 天) | 4189 (+604) |
| 简体落地页被搜索爬虫抓取占比 % | 80.2 (+2.4) |
| 繁体落地页数(sitemap) | 2188 (+1219) |
| 繁体落地页被搜索爬虫抓取数 | 1214 (+415) |
| 繁体成品可疑字形(处) | 36 (+36) |
| 搜索来源访问(7 天) | 4  |
| AI 来源访问(7 天) | 0  |
| AI 实测引用本站(题) | 0  |
| 今日 IndexNow 提交 | 2586 (+2070) |

## Google 搜索词(28 天)

| 搜索词 | 曝光 | 点击 | 排名 |
|---|---|---|---|
| dolwms.dol.go.th. 2 | 1 | 0 | 47 |
| 泰國工業區 分佈 | 1 | 0 | 1 |
| 泰國變更土地用途 注意事項 | 1 | 0 | 65 |
| 泰國變更土地用途 限制 | 2 | 0 | 65.5 |
| 泰國電子產業 稅務優惠 | 1 | 0 | 66 |

## Google 收录状态分布(已检查的简体页)

- 已提交，且已编入索引:621
- Google 无法识别此网址:159
- 已发现 - 尚未编入索引:111

## Google 收录状态分布(已检查的繁体页,单列)

- Google 無法辨識的網址:36
- 已找到 - 目前尚未建立索引:22
- 已提交並建立索引:16

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
| Bingbot | 搜索 | 3359 | 3313 | 2904 | 2026-11-22 |
| GPTBot | AI | 2683 | 2643 | 2676 | 2026-11-21 |
| Googlebot | 搜索 | 1803 | 1401 | 901 | 2026-11-22 |
| Meta-AI | AI | 1560 | 1539 | 1559 | 2026-11-21 |
| PetalBot | 搜索 | 699 | 691 | 656 | 2026-11-22 |
| Applebot | 搜索 | 150 | 16 | 26 | 2026-11-21 |
| YandexBot | 搜索 | 102 | 87 | 87 | 2026-11-21 |
| OAI-SearchBot | AI | 21 | 0 | 1 | 2026-11-21 |
| Baiduspider | 搜索 | 9 | 1 | 9 | 2026-11-17 |
| ChatGPT-User | AI | 6 | 6 | 4 | 2026-11-20 |
| DuckDuckBot | 搜索 | 6 | 2 | 3 | 2026-11-21 |
| PerplexityBot | AI | 2 | 1 | 2 | 2026-11-18 |

## 来访渠道(近 7 天)

- 搜索 · Google:4

## GEO 实测(Perplexity)

- ⚠️ 泰国免签停留期最近有什么调整?内阁决议和公报是否一致? —— HTTP 403 The Agent API requires paid credits. Sign-up credits and Perplexity Pro or Max subscriptions do not count. Add credits at https://console.perplexity.ai to unloc

## 今日提交

- IndexNow:2586 个 URL
- GSC sitemap:已存在
