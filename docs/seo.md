# SEO / GEO 与每日监控

目标:让 Google、Bing、百度收录本站,并让 ChatGPT、Perplexity、Claude、豆包等 AI 助手在回答泰国政策问题时引用本站、附上原文链接。

## 一、站内做了什么(`backend/app/seo.py`,每次 `app.export` 自动生成)

| 产物 | 作用 |
|---|---|
| `p/<uid>.html` 落地页 | 无需 JS 可读;开头一句话结论(谁、何时、发布了什么、现在什么状态)、「要点速览」、引用格式、同领域推荐;结构化数据 `Legislation`(含 `translationOfWork` 指向泰文原文)+ `BreadcrumbList`;长标题自动截短 |
| `p/topic/<领域>.html` 专题页 | 「泰国 + 签证/税务/劳工… + 政策」长尾词的落地页,`CollectionPage` + `ItemList` |
| `p/index.html` | 全部政策目录,按领域分组 |
| `robots.txt` | 放行所有搜索引擎,并逐个点名放行 GPTBot、OAI-SearchBot、ClaudeBot、PerplexityBot 等 AI 爬虫;屏蔽 `/api/`、`/admin` |
| `sitemap.xml` | 首页、目录、专题页、全部落地页,`lastmod` 取数据日期 |
| `llms.txt` / `llms-full.txt` | 给大模型的站点说明、引用方式、索引;full 版含每条政策的摘要与官方原文链接 |
| `feed.xml` | Atom 订阅,最新 50 条 |
| `index.html` 受管区块 | `<!-- seo:head -->`:canonical、站长平台验证 meta、`WebSite` / `Organization` / `Dataset` 结构化数据;`<!-- seo:links -->`:页脚按领域浏览与最新收录链接(给爬虫的入口) |
| `favicon.svg` | 搜索结果里显示的站点图标 |

首页卡片标题也改成了真实链接(`<a href="p/…html">`),爬虫能顺着首页找到每一页;普通点击仍在站内打开详情。

这些都是派生产物,CI 会检查它们与事实层一致,**不要手改**,改 `seo.py`。

## 二、效果度量(服务器侧,`backend/app/seo_track.py`)

- **爬虫抓取**:中间件按 User-Agent 识别 Googlebot、Bingbot、百度、GPTBot、ClaudeBot、PerplexityBot 等,记录爬虫名、路径、状态码(不存 IP)。爬虫不跑 JS,前端统计看不到它们。
- **来源渠道**:把真人访问的来源分成 搜索引擎 / AI 助手 / 社交 / 其他网站 / 直接访问。从 chatgpt.com、perplexity.ai 等进来 = AI 回答引用了本站,这是 GEO 最直接的证据。
- **后台**:`/admin` →「SEO / GEO」标签。

## 三、每日监控(每天曼谷时间 03:00)

`.github/workflows/seo.yml` 运行 `python -m app.seo_monitor`:

1. **体检线上站点**:首页、robots、sitemap、llms.txt、feed、IndexNow 核验文件、http→https 与裸域→www 跳转;每天抽查 40 个页面(最新 10 页 + 其余轮换),检查 canonical、noindex、标题、描述、H1、结构化数据、官方原文链接、内容是否单薄;线上 sitemap 与仓库对比,发现服务器没同步。
2. **查收录**:Search Console 的 URL 检查接口逐页查 Google 收录状态(每天 60 页轮换,结果累积)、28 天搜索表现、sitemap 状态;Bing 已收录页数与搜索词;服务器的爬虫抓取与来源渠道。
3. **提交新页面**:IndexNow(Bing、Yandex、Naver、Seznam 共用)、百度普通收录、GSC sitemap —— 只提交新增或变更的页面,进度记在 `data/seo/state.json`。
4. **GEO 实测**:用 `config/seo.json` 里的问题问 Perplexity,看回答是否引用本站、引用了哪些竞争站点。
5. **写日报**:`data/seo/latest.md`(人看)、`latest.json`(后台与例行会话读)、`history.jsonl`(趋势),提交回仓库。

站点打不开、整站被 robots 屏蔽、sitemap 丢失时,这次运行会变红,GitHub 给仓库所有者发邮件。

随后的**每日例行会话**(Claude,03:45 左右)读日报,把能在代码里修的问题修掉、开 PR、CI 通过后合并;需要人操作的(站长平台验证、服务器配置)留在日报与后台里。

## 四、需要你配置的(都可选,越全越准)

在 GitHub 仓库 **Settings → Secrets and variables → Actions** 里添加。没配的项日报会写在「未启用的数据源」里。

| 名称 | 类型 | 作用 | 怎么拿 |
|---|---|---|---|
| `ADMIN_TOKEN` | Secret | 读服务器的爬虫与来源数据 | 与服务器 `backend/.env` 里的 `ADMIN_TOKEN` 相同 |
| `GSC_SERVICE_ACCOUNT_JSON` | Secret | **直接查 Google 收录** | 见下文「接入 Search Console」 |
| `GSC_PROPERTY` | Variable | GSC 资源名 | 网域资源不用填(默认 `sc-domain:thaipolicy.com`);网址前缀资源填 `https://www.thaipolicy.com/` |
| `BING_WEBMASTER_API_KEY` | Secret | Bing 已收录数与搜索词 | Bing Webmaster Tools → 设置 → API 访问 |
| `BAIDU_PUSH_TOKEN` | Secret | (可选,目前不用)主动推送新页面给百度;不配时日报不提百度 | 百度搜索资源平台 → 验证站点 → 普通收录 → API 提交里的 token |
| `PERPLEXITY_API_KEY` | Secret | GEO 实测 | perplexity.ai → API,每天约 0.03 美元 |

### 接入 Search Console

1. 在 [Search Console](https://search.google.com/search-console) 添加资源。推荐「网域」资源 `thaipolicy.com`,按提示在 DNS 加一条 TXT 记录验证。
   也可以用「网址前缀」资源 + HTML 标记验证:把 `content` 的值填进 `config/seo.json` 的 `verification.google`,合并后首页会自动带上验证 meta。
2. 在 [Google Cloud 控制台](https://console.cloud.google.com/) 新建项目 → 启用 **Google Search Console API** → 「IAM 和管理 → 服务账号」新建一个服务账号 → 「密钥 → 添加密钥 → JSON」下载。
3. 回到 Search Console → 设置 → 用户和权限 → 添加用户,填服务账号邮箱(`…@….iam.gserviceaccount.com`),权限选「完整」。
4. 把下载的 JSON 整段粘贴到 GitHub Secret `GSC_SERVICE_ACCOUNT_JSON`。

### 接入 Bing / 百度

- **Bing Webmaster**:可以直接「从 Google Search Console 导入」站点,省去验证。Bing 同时是 ChatGPT 搜索与 Copilot 的检索来源,对 GEO 很重要。IndexNow 不需要任何账号,已自动提交。
- **百度搜索资源平台**:添加站点,用 HTML 标签验证时把值填进 `config/seo.json` 的 `verification.baidu`。新站每天推送配额很小(约 10 条),监控会优先推最新页面。

## 五、手动运行

```bash
# GitHub:Actions →「SEO / GEO 每日监控」→ Run workflow
# 本地:对着本地服务试跑,不提交
cd backend && python -m app.seo_monitor --site http://127.0.0.1:8000 --no-submit --out /tmp/seo
```

## 六、已知限制

- 爬虫按 User-Agent 识别,可被伪造,只看趋势。
- 没有 Search Console 时,「是否被收录」只能从爬虫抓取和搜索来访间接判断。GSC 数据有 2–3 天延迟。
- 爬虫与来源数据要等服务器更新后才开始积累。

## 七、内容质量:按公报正文写摘要(`backend/app/fulltext.py`)

只凭标题写的摘要(「据标题……具体条款待原文核对」)内容单薄,搜索引擎不给排名,AI 也不会引用。现在翻译前先读正文:

1. 下载官方 PDF 原文:只下载 `*.go.th` 域名下的 PDF,经 `THAI_EGRESS_PROXY` 出口,每秒最多 1 个请求,单个文件不超过 15 MB。
2. 用 pypdf 抽取文字层,并把老式泰文字体放在私用区的声调符号还原成标准字符。文字层读不出来的扫描件,用 tesseract 泰文 OCR 识别前 3 页;采集工作流会自动装好 OCR 工具。
3. 正文和标题一起交给模型,产出三样东西:
   - 2–4 句有实质内容的摘要;
   - 3–5 条**正文要点**(适用对象、义务或权利、金额、期限、办理机关);
   - **生效日**。「自刊登次日起施行」这类规定由程序按刊登日推算,不让模型自己算日期。
4. 正文拿不到时退回只看标题,与原来一样。

之前只凭标题写的摘要,会用每日翻译额度里剩下的部分逐步按正文重做,新条目优先。重做时正文拿不到,最多重试 3 轮。要点显示在落地页和站内详情的「正文要点」一节。

有正文要点的页面,监控不再判为「内容单薄」。要关闭读正文,把 `ENRICH_FULLTEXT` 设为 `0`。

费用(DeepSeek,按公开价估算,以官网为准):每条带正文约 0.001 美元,只看标题约 0.0003 美元。积压的约 1200 条一次性处理完约 1.5 美元;之后每天新增约 15 条,每月约 0.5 美元。每日上限 `ENRICH_MAX_PER_RUN` 只是封顶,实际按新增条数计费。
