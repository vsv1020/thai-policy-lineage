# SEO / GEO 与每日监控

目标:让 Google、Bing、百度收录本站,并让 ChatGPT、Perplexity、Claude、豆包等 AI 助手在回答泰国政策问题时引用本站、附上原文链接。

## 一、站内做了什么(`backend/app/seo.py`,每次 `app.export` 自动生成)

| 产物 | 作用 |
|---|---|
| `p/<uid>.html` 落地页 | 无需 JS 可读;开头一句话结论(何时、发布了什么、现在什么状态;机关能印证时才写是谁发的)、「要点速览」、引用格式、同领域推荐;结构化数据 `Legislation`(含 `translationOfWork` 指向泰文原文)+ `BreadcrumbList`;`<title>` 最前面写「泰国」(内阁决议写「泰国内阁决议:」),长标题自动截短,标题与别的条目完全相同时(同名系列)带上日期;描述停在句末,不拦腰截断 |
| `p/topic/<领域>.html` 领域页 | 「泰国 + 签证/税务/劳工… + 政策」长尾词的落地页:开场白说明本领域收什么,先列最新 10 条的摘要、要点与原文链接,再按年份列全部条目;页尾链到相关专题与其他领域;`CollectionPage` + `ItemList` |
| `p/guide/royal-gazette.html` 指南页 | 「泰国皇家公报 / 政府公报」是什么、官网、四个类别、编号读法、佛历换算、刊登日与生效日的区别、有没有中文版。Bing 上给本站带来曝光的词大多是这类问公报本身的词。`Article` + `FAQPage`;文字在 `backend/app/seo_guide.py`,数字与编号示例从数据现算 |
| `p/week/<年-W周>.html` 周汇总 | 一周内刊登或发布的条目,逐条带摘要与原文链接。少于 3 条的周只是落地页的重复:`noindex, follow`,不进 sitemap |
| `p/404.html` | `/p/` 下不存在的地址显示它(状态码仍是 404);其他页面类地址的 404 也用这一页,接口与资源文件的 404 仍是 JSON |
| `assets/og.png` 分享图 | 微信、LINE、Telegram、Facebook、X 分享链接时显示的预览图(1200×630),全站页面的 `og:image` 都指向它(繁体页用 `assets/og-hant.png`);源文件 `tools/og.html` |
| `p/t/<专题>.html`、`p/who/<对象>.html` 汇总页 | 配置专题(`config/topics.json`)与影响对象的汇编:最新 20 条带摘要、要点与原文链接,更早的按年份列标题(不超过 25 条的页整页带摘要);描述以「泰国 + 主题」开头;`CollectionPage` + `BreadcrumbList`。每个成员落地页的「收录于汇总页」一行链回它们,汇总页因此不只靠首页和目录两处入口 |
| `p/index.html` | 全部政策目录,按领域分组 |
| `robots.txt` | 放行所有搜索引擎,并逐个点名放行 GPTBot、OAI-SearchBot、ClaudeBot、PerplexityBot 等 AI 爬虫;屏蔽 `/api/`、`/admin` |
| `sitemap.xml` | 首页、目录、专题页、全部落地页,以及它们的繁体版,`lastmod` 取数据日期 |
| `llms.txt` / `llms-full.txt` | 给大模型的站点说明、引用方式、索引(领域、专题、影响对象、指南、繁体版地址规律);索引里每个汇总页都写明收什么、多少条、最新到哪天,模型才能按问题挑对页面;full 版含每条政策的摘要、生效日、影响对象与官方原文链接 |
| `feed.xml` | Atom 订阅,最新 50 条 |
| `index.html` 受管区块 | `<!-- seo:head -->`:canonical、hreflang、分享图、站长平台验证 meta、`WebSite` / `Organization` / `Dataset` 结构化数据;`<!-- seo:links -->`:页脚的领域、专题、影响对象、指南与最新收录链接(给爬虫的入口);`<!-- seo:feed -->`:「最新收录」那几条卡片的静态版(见下) |
| `zh-hant/` 繁体版 | 上面全部静态页的繁体中文版,见「繁体中文版」一节 |
| `favicon.svg` | 搜索结果里显示的站点图标 |

首页卡片标题也改成了真实链接(`<a href="p/…html">`),爬虫能顺着首页找到每一页;普通点击仍在站内打开详情。

首页「最新收录」(`#feed`)原先只有一句「政策加载中……」,Bing、百度和全部 AI 爬虫不跑 JS,在首页主体里读不到任何政策。现在导出时把首页实际显示的那几条(`data/site/policies.json` 里 `featured` 的条目,与前端同一口径)按 `js/data.js` 的 `policyCard` 同一结构、同一类名渲染进 `<!-- seo:feed -->`;前端加载后 `set('feed', …)` 整体替换,卡片相同,版面不跳。静态卡片不带 `onclick`:脚本加载完之前点标题直接去落地页。页头时间戳、「最近收录的 N 条」和数据说明(`#stamp`、`#today-sub`、`#lag-note`)也按 `renderOverview` 同一口径预先写好(`<!-- seo:stamp -->` 等),前端换上的是同样的文字。`backend/tests/test_home_prerender.py` 用 node 真跑 `js/data.js`,与 Python 版逐条比对。

这些都是派生产物,CI 会检查它们与事实层一致,**不要手改**,改 `seo.py`。

几条写页面时守住的规则:

- **有公报卷期才说「刊登公报」。** 税务厅、BOI 等官网来源的条目,日期是官网发布日,落地页写「于某日发布」「发布日」,不写「在皇家公报刊登」。开头那句话是 AI 最常引用的,不能写本站没核对过的事。
- **官方原文链接不加 `nofollow`。** 它是页面的出处;`nofollow` 是给不愿背书的链接(广告、用户投稿)用的。
- **状态里的日期写全。** 「01-01 起施行」在首页卡片上挨着日期看得懂,落地页上写成「2027-01-01 起施行」。
- **内容太少的汇总页不进索引。** 一两条的周汇总只是落地页的重复,留在索引里会拉低整站的内容质量评价。
- **机关能印证才说是「发文机关」**(`issuer_info`)。数据里的机关是模型从词表里选的,词表没有的机关(宪法法院、商品与服务安全委员会、疾病控制厅……)会被归到上级部委,或落到缺省值「内阁」。Google 上点击最多的落地页曾写着「内阁于某日在泰国皇家公报刊登《商品与服务安全委员会命令……》」。现在(`app.issuer.attribute`,落地页、首页卡片、站内详情视图、llms-full.txt 共用,导出时算好放进 `policies.json` 的 `org_label` / `org_issuer` / `org_related`):公报条目要泰文原题写明的发文机关(与数据层 `app.enrich.fix_agency` 同一套判断:机关名紧跟在「ประกาศ / คำสั่ง / ระเบียบ……」之后,名字里含「ว่าด้วย」的委员会按整名认;府级办公室等前缀式别名、官员职务称谓不算)是该条目的机关之一 —— 只有这几个写成发文机关,模型另选的机关另列「相关机关」;官网来源转载的皇家法令、部令不按官网机关写成发文者,标题以文件类型开头却认不出、或写明了别的机关时也不按官网机关算;官网转载别家的文件(BOI 官网上的总理府命令、税务厅官网上的财政部公告),机关栏照写发文机关,开头句与时间轴写「在某某官网发布」(那是上架日,不是发文日);官网来源的条目要第一个机关就是那个官网的机关(uid 的第二段);内阁决议要第一个机关是内阁。印证不了的,开头那句话不拿机关当主语(「《……》于某日在泰国皇家公报刊登」「……在投资促进委员会官网发布」),机关一栏的标签改成「相关机关」,结构化数据不写 `legislationPassedBy`;只有一个缺省的「内阁」时整栏不显示。581 个落地页里 465 个印证得了,89 个标「相关机关」,27 个不显示。之后在数据层根治:机关词表从 39 个补到 112 个(宪法法院、商品与服务安全委员会、疾病控制厅、选举委员会……,府级土地办公室等用别名归到上级),已入库条目用 `python3 -m app.enrich --fix-agencies` 按泰文原题重新归类;现在 714 个落地页里 600 个标「发文机关」(其中 37 个另有一行「相关机关」列出模型另选的机关),110 个只有「相关机关」(部令、皇家法令等标题里没写发文机关的;各府办公室、地方行政组织、交警长官、破产财产管理人这类前缀式 / 职务别名;官网来源、内阁决议里第一个机关对不上的),4 个不显示。
- **内阁决议只说「作出决议」。** 决议可能是批准,也可能只是听取报告或交办;50 条内阁决议的摘要都还只凭标题,不能一律写成「经内阁决议通过」。
- **标题里已有书名号时,外层用双书名号、内层改单书名号**:《〈清迈倡议多边化协议〉修订版草案》,不写《《……》……》。
- **`<title>` 最前面写「泰国」**(`title_lead`)。公报标题是「工业部公告:……」这样的写法,581 个落地页里只有 71 个的 `<title>` 前 30 个字里有「泰国」(搜索结果大致只显示这么多),其余的要么标题里没有,要么只在被截掉的结尾「| 泰国政策」里。只改 `<title>` 与 `og:title`,页面上的 H1 仍是标题原样。
- **结构化数据跟着页面上看得见的事实走。** `legislationLegalForce` 原先只看状态词表,「已刊公报」一律是 `NotInForce`,而正文写着「某日起生效」。现在:现行有效或已到生效日 → `InForce`;已刊公报但没有生效日 → 不声明;草案、待刊公报、未到生效日、已被替代或废止 → `NotInForce`(`legal_force`)。
- **条目多的汇总页不整页铺摘要。** 「影响外资企业」440 条每条都带摘要与要点时一页 583 KB、5100 个节点,手机 4G 首屏 2.1 秒,AI 助手取页面也只读得进开头一小段。改成最新 20 条带摘要、其余按年份列标题后 173 KB、2250 个节点、首屏 1.2 秒;每一条仍在页面上有一个链接。
- **开头明显缺字的要点不展示**(`sound_points`)。早先的要点清洗把开头的数字一律当成列表序号删掉,「2026年7月1日及以后建造的船舶须……」成了「年7月1日及以后……」。`app.enrich.strip_list_marker` 已改正(只删「1. 」「2、」「- 」这类记号),事实层里已有的 35 条要等重新整理;在那之前页面与 llms-full.txt 不展示它们,摘要不受影响。

服务器(`backend/app/main.py`)给静态内容加了短时间的浏览器缓存:样式与脚本 1 小时、落地页(含 `/zh-hant/`)10 分钟、首页与根目录文件 5 分钟,过期后凭 ETag 复核。

### 繁体中文版(`/zh-hant/`)

Google 给本站带来曝光的搜索词全是繁体(泰國變更土地用途、泰國工業區 分佈……),所以全部静态页另出一份繁体版。

- **地址**:简体地址的路径前加 `/zh-hant`,目录结构完全相同(`/zh-hant/p/<uid>.html`、`/zh-hant/p/topic/`、`/zh-hant/feed.xml`……)。简体地址一个不变。`/zh-hant` 301 到 `/zh-hant/`;`/zh-hant/` 下不存在的地址给繁体 404 页。
- **怎么生成**:`seo.build()` 用同一套渲染函数跑两遍,第二遍在 `_variant(True)` 下:站内绝对地址、语言标记、资源路径按繁体版写,整页再过 `backend/app/hant.py` 转换。站内相对链接两边结构相同,自然留在 `/zh-hant/` 内;css、js、favicon、assets 不复制,从站点根目录取,`data-base` 也指向站点根(统计、广告位、打赏照常工作)。`about.html`、`privacy.html` 的繁体版从简体文件转换。
- **繁体首页**是静态门户页:领域、专题、影响对象、指南、周汇总、订阅入口,加最新 20 条摘要卡片。单页应用、`js/`、`data/site/*.json` 只有简体,门户页注明检索与图表在简体版并给链接。它的描述与开场白单独写(`HANT_HOME_DESC`),不照抄简体的站点描述 —— 那句话里的「七维政策分析与趋势看板」繁体首页没有。
- **语言标记**:`<html lang="zh-Hant">`、`og:locale` `zh_TW`、结构化数据 `inLanguage: zh-Hant`、分享图 `assets/og-hant.png`。每页简繁两边都有 `zh-Hans` / `zh-Hant` / `x-default`(指简体)三条 hreflang,canonical 各指自己;页头有切换链接。sitemap 收全部可收录的繁体地址,周汇总「少于 3 条 noindex」同样适用。
- **转换**:OpenCC `s2tw`(只换字形,版本钉死在 `backend/requirements.txt`)。不用 `s2twp`:它连词汇一起换,会把「发布公告」换成「釋出公告」、「申请文件」换成「申請檔案」。转换只动汉字,并逐字核对 URL、泰文、类名等非汉字内容一字未改,否则导出报错。
- **覆盖表 `config/hant.json`**:`s2tw` 一简对多繁的错,在 OpenCC 之后逐条替换,每条在 `backend/tests/test_hant.py` 里有一个真实例句。表是对全站简体文本做审计得来的:找出含「干、后、里、发、复、台、制、并、周……」等一简对多繁字的全部片段,按「字 → 转换结果」分组,逐组看三字语境,对可疑的再看整句。审计字表:干 后 里 面 只 松 发 复 历 钟 系 台 余 云 谷 斗 划 采 冲 症 托 签 表 板 获 汇 伙 几 卷 克 困 累 厘 蒙 征 志 制 致 种 周 筑 准 借 当 尽 据 范 并 价 适 了 家/具 并发 等。修过的有:府名音译里的「里」「干」(春武里、董里、南奔府里县、沙没巴干、汶干);「部长发布→部長髮布」「60天后生效→天后」「证书签发→書籤發」「货斗→貨鬥」「规定制定→製定」「协调制度→協調製度」「提交并缴税、制定并发布→併」「专家具备、国家具有→專傢俱備、國傢俱有」「列明了→列明瞭」「冲抵、冲减→衝」「折合→摺合」「不准进口、御准→準」「本规定系根据→系」「干木耳、干物质→幹」等;「台、發布、公布、頒布、宣布、週、夥伴、複核、託運」统一成一种写法。规则都带上下文,只改错处:「抑制劑」「部分周邊」「長髮須束起」「天后宮」以及王后、皇后、太后、陛下、殿下等称谓都有反例测试。
- **用词**:只换两个词,「数据库→資料庫」「链接→連結」。它们无歧义、台湾与香港都通行,而且目前只出现在本站自己的说明文字里(繁体首页标题、各页描述里的「每条附泰文原文链接」),政策正文里一处都没有;「链接」的规则避开「供应链接入」「区块链接口」这类「某某链 + 接…」。其余大陆用词(信息、网络、数字、软件、项目……)不换:它们大量出现在政策正文里,台湾与香港的说法又不一致(網路 / 網絡、數位 / 數碼),换了反而可能改坏法律文本。领域名「数字与数据」同理未动。
- **可疑字形检查**:`config/hant.json` 的 `suspicious` 是一份检查用的正则清单(不改文字),覆盖本领域里 s2tw 常错、而现有规则可能没盖住的写法(如「傢俱[備有體]」「明瞭」「衝抵」「摺合」「併發」)。`python -m app.hant --check` 扫描导出的 `zh-hant/`,有命中就列出页面与片段并非零退出;每日监控也读仓库里的 `zh-hant/` 在日报里列出命中(`hant_suspicious`)。成品必须零命中:命中说明数据里出现了新的语境,在 `rules` 里补带上下文的规则并配例句;确认是正确用法就收紧可疑模式。
- **失败模式**:导出先把简繁全部页面渲染、转换到内存,最后才清空目录写盘,中途出错时两套旧文件原样保留。环境变量 `HANT_STRICT` 默认 1(CI、本地):繁体出错导出直接失败。生产(`docker-compose.yml`)设 0:繁体出错只记错误日志、保留旧的 `zh-hant/`,简体照常导出、站点照常启动;此时简体页与 sitemap 只引用旧 `zh-hant/` 里确实存在的繁体页。

## 二、效果度量(服务器侧,`backend/app/seo_track.py`)

- **落地页覆盖率**:近 N 天被搜索爬虫抓过的落地页占 sitemap 落地页的比例。主指标只算简体落地页(分子分母同口径,与繁体版上线前可比),繁体落地页另列 `hant_sitemap_landing` / `hant_crawled_by_search`。
- **爬虫抓取**:中间件按 User-Agent 识别 Googlebot、Bingbot、百度、神马、花瓣、GPTBot、ClaudeBot、PerplexityBot、豆包(Bytespider)、智谱等,记录爬虫名、路径、状态码(不存 IP)。爬虫不跑 JS,前端统计看不到它们。
  「抓取次数」(`hits`)把样式、脚本、数据文件和报错请求都算在内:会渲染页面的爬虫(Applebot)每抓一页带出十来个子请求;冒用爬虫 UA 的漏洞扫描一天就能刷出几百次 404(2026-11-13 那天「AI 爬虫」245 次几乎全是)。所以每个爬虫另记「取到页面」(`page_hits`:状态码 < 400 的 `.html` 页面与目录地址),日报的「搜索 / AI 爬虫成功取到页面(7 天)」用它。判断爬虫实际读了多少内容看这一项;原有的次数指标口径不变。
- **来源渠道**:把真人访问的来源分成 搜索引擎 / AI 助手 / 社交 / 其他网站 / 直接访问。从 chatgpt.com、perplexity.ai、豆包、Kimi、DeepSeek、元宝、通义、文心一言等进来 = AI 回答引用了本站,这是 GEO 最直接的证据。
- **后台**:`/admin` →「SEO / GEO」标签。

## 三、每日监控(每天曼谷时间 03:00)

`.github/workflows/seo.yml` 运行 `python -m app.seo_monitor`:

1. **体检线上站点**:首页、robots、sitemap、llms.txt、feed、IndexNow 核验文件、http→https 与裸域→www 跳转;每天抽查 40 个页面(最新 10 页,简繁各 5 页 + 其余轮换),检查 `<html lang>` 与三条 hreflang 是否齐全;繁体首页 `/zh-hant/` 能打开、`/zh-hant` 301 过去,检查 canonical、noindex、标题、描述、H1、结构化数据、分享图、官方原文链接、内容是否单薄;线上 sitemap 与仓库对比,发现服务器没同步。
2. **查收录**:Search Console 的 URL 检查接口逐页查 Google 收录状态(每天 60 页轮换,结果累积;名额简体 3/4、繁体 1/4。收录率等主指标与告警只算简体,繁体单列 `gsc_hant_*`;繁体页被 Google 归并到对应简体页单独归为提示,不套用「内容过于相似」的建议)、28 天搜索表现、sitemap 状态;Bing 已收录页数与搜索词;服务器的爬虫抓取与来源渠道。
3. **提交新页面**:IndexNow(Bing、Yandex、Naver、Seznam 共用)、百度普通收录、GSC sitemap —— 只提交新增或变更的页面,进度记在 `data/seo/state.json`。
   改了页面模板(措辞、标题、描述)而数据日期没变时,lastmod 不变,IndexNow 不会重交:把 `config/seo.json` 里 `indexnow_resubmit.epoch` 改成一个新值,下一次监控就整站向 IndexNow 重新提交一次(成功后记在 `state.json` 的 `indexnow_epoch`)。线上还没部署到仓库这一版时(仓库 sitemap 里有线上没有的地址)整站重交顺延到下一次,免得 Bing 抓到旧模板。百度配额很小(约 10 条/天),不跟着重推,也不推繁体页。
4. **GEO 实测**:用 `config/seo.json` 里的问题问 Perplexity,看回答是否引用本站、引用了哪些竞争站点。
5. **写日报**:`data/seo/latest.md`(人看)、`latest.json`(后台与例行会话读)、`history.jsonl`(趋势),提交回仓库。

站点打不开、整站被 robots 屏蔽、sitemap 丢失时,这次运行会变红,GitHub 给仓库所有者发邮件。

随后的**每日例行会话**(Claude,09:45;GitHub 定时任务可能延迟数小时,留足余量)读日报,把能在代码里修的问题修掉、开 PR、CI 通过后合并;需要人操作的(站长平台验证、服务器配置)留在日报与后台里。

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

### 准时触发(推荐)

GitHub Actions 自带的定时只是「尽量准时」,实测会延迟 5 小时甚至整晚不触发。服务器的 cron 是准时的,由它每天准点触发工作流:03 点触发 SEO 监控,07 点触发采集。GitHub 的定时保留作备份,当天已经由服务器触发过的,备份那次会自动跳过。

1. GitHub → 右上角头像 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token:
   - Repository access:Only select repositories → `thai-policy-lineage`
   - Permissions → Repository permissions → **Actions: Read and write**,其余不用勾
   - 有效期选最长,到期前记得换
2. 在服务器上执行:
   ```bash
   cd /opt/thai-policy-lineage
   echo 'GH_DISPATCH_TOKEN=github_pat_xxx' >> .env      # 换成刚生成的令牌
   bash deploy/install.sh                                # 重跑一次,装上 cron(已有配置与密钥都会保留)
   deploy/dispatch.sh seo.yml       # 手动试一次,输出「已触发 seo.yml」即成功(定时运行的记录在 /var/log/thai-policy-dispatch.log)
   ```

## 五、手动运行

```bash
# GitHub:Actions →「SEO / GEO 每日监控」→ Run workflow
# 本地:对着本地服务试跑,不提交
cd backend && python -m app.seo_monitor --site http://127.0.0.1:8000 --no-submit --out /tmp/seo
```

## 六、已知限制

- 爬虫按 User-Agent 识别,可被伪造,只看趋势;被伪造时「抓取次数」会虚高,以「取到页面」为准。
- 漏洞扫描器常冒用爬虫 UA 乱试地址。日报的「爬虫报错」不报这类 404:路径既不在仓库已有的顶层目录或文件之下,也不是网页类后缀(如 `/index.php`、`/cgi-bin/php`、`/userfiles`)。旧页面、错误内链和所有 5xx 照常上报。
- 没有 Search Console 时,「是否被收录」只能从爬虫抓取和搜索来访间接判断。GSC 数据有 2–3 天延迟。
- 爬虫与来源数据要等服务器更新后才开始积累。

## 七、内容质量:按公报正文写摘要(`backend/app/fulltext.py`)

只凭标题写的摘要(「据标题……具体条款待原文核对」)内容单薄,搜索引擎不给排名,AI 也不会引用。现在翻译前先读正文:

1. 下载官方 PDF 原文:只下载 `*.go.th` 域名下的 PDF,经 `THAI_EGRESS_PROXY` 出口,每秒最多 1 个请求,单个文件不超过 15 MB。
2. 按顺序尝试,直到读到可用正文(泰文,或英文原文):
   - pypdf 抽取文字层(装了 fonttools 才能正确解码 CFF/Type1 嵌入字体);
   - poppler 的 pdftotext;
   - 老式字体的乱码自动还原(私用区声调符号、TIS-620 被当成 Latin-1 的乱码);
   - 扫描件用 tesseract 泰文 OCR 识别前 3 页。
   都不行时,采集运行摘要里的「没读到正文」会按原因分类计数,并附示例链接和各环节读出的字数。
3. 正文和标题一起交给模型,产出三样东西:
   - 2–4 句有实质内容的摘要;
   - 3–5 条**正文要点**(适用对象、义务或权利、金额、期限、办理机关);
   - **生效日**。「自刊登次日起施行」这类规定由程序按刊登日推算,不让模型自己算日期。
4. 正文拿不到时退回只看标题,与原来一样。

之前只凭标题写的摘要,会用每日翻译额度里剩下的部分逐步按正文重做,新条目优先。重做时正文拿不到,最多重试 3 轮。要点显示在落地页和站内详情的「正文要点」一节。

有正文要点的页面,监控不再判为「内容单薄」。要关闭读正文,把 `ENRICH_FULLTEXT` 设为 `0`。

费用(DeepSeek,按公开价估算,以官网为准):每条带正文约 0.001 美元,只看标题约 0.0003 美元。积压的约 1200 条一次性处理完约 1.5 美元;之后每天新增约 15 条,每月约 0.5 美元。每日上限 `ENRICH_MAX_PER_RUN` 只是封顶,实际按新增条数计费。
