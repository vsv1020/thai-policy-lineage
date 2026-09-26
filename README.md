# 政策脉络 · 泰国 — Thai Policy Lineage

> 面向在泰华人的泰国政策中文数据库与预警系统(原型阶段)
> Thai government policy tracker for the Chinese-speaking community — prototype.

**在线原型:** https://vsv1020.github.io/thai-policy-lineage/

泰国政策信息只有泰文、极度分散(公报/移民局/税务厅/BOI 各自发布),中文世界的供给全部停留在"新闻编译"层。本项目要做的是"泰国政策的中文数据库与预警系统":**官方源自动监测 → 可溯源中文结构化 → 归类检索 → 趋势与维度分析 → 订阅预警**。

## 仓库结构

```
index.html            产品原型(静态站,GitHub Pages 直接访问)
css/ js/              前端:api.js 取数与降级 · data.js 首页/检索/脉络 · dims.js 七维 · app.js 图表
backend/              Python 后端:FastAPI + SQLAlchemy + 每日采集定时器(见 backend/README.md)
data/vocab.json       受控词表:领域/机关/法律形式/工具/目标/环节/关系/作用对象
data/policies/        事实层(JSONL,可 review 的政策记录)
data/site/            派生层(backend/app/export.py 导出,禁止手改)
tools/validate.py     纯标准库校验器(词表、关系、日期顺序、编辑红线)
pipeline/             早期抓取 PoC(已由 backend/app/collect.py 接管)
.github/workflows/collect.yml  每日自动采集 → 翻译 → 导出 → 提交
p/                    每条政策的静态落地页(SEO,由 export 生成)
config/ads.json       广告位配置(默认关闭,类别白名单)
config/analytics.json 站点统计配置(自建 /admin 后台 + 可选 Cloudflare/Plausible)
admin.html            站点统计后台(需 ADMIN_TOKEN)
docs/deploy.md · docs/monetization.md · docs/analytics.md   上线手册 · 营收与广告位 · 站点统计
deploy/install.sh     一键部署到 Linux 服务器(Docker + Postgres + 宿主机 nginx/certbot HTTPS + 定时同步与备份)
docs/research-report.md   完整调研报告
```

## 架构

```
data/vocab.json ─┐
data/policies/*.jsonl ─┴→ app.ingest ──→ 数据库 ──→ app.api  ──→ 前端(首选)
                                          │           SQLite 开发 / Postgres 生产
每日采集 app.collect ──→ 追加 JSONL ───────┤
(data.go.th 官方接口)  └→ 写库             └→ app.export → data/site/*.json(静态降级)
```

**数据库是运行时存储,git 里的 JSONL 是可 review 的事实记录**,采集两边都写。
对一个卖「可溯源」的产品,审计轨迹本身就是功能。字段含义与设计理由见
[data/README.md](data/README.md),部署见 [backend/README.md](backend/README.md)。

前端三级降级:**API → data/site/*.json → HTML 内联占位**,后端没部署时静态站照常工作。

```bash
cd backend && pip install -r requirements.txt
python3 -m app.ingest --reset   # 建表 + 载入词表与事实层
uvicorn app.main:app --port 8000  # 同时提供 API(/docs)与静态站(/)
```

## 关键性质

- **所有分析都是算出来的**:风向指数、生效日历、首页选条、趋势聚合、政策维度七维,
  全部由 `backend/app/analytics.py` 从数据库聚合。结构上排除了「为了让页面有变化而编造数字」。
- **每个维度自报样本量**:不足阈值就显示「数据不足:仅 N 条样本」而不是画一张看起来
  很确定的图。趋势图在覆盖不足 6 个月时退回演示数组。
- **导出是纯函数**(「现在」取上次采集时间而非运行时刻),所以 CI 能用
  `git diff --quiet -- data/site/` 抓出手改派生文件或漏跑导出。
- **日期拆成四类**(决议/刊登/生效/意见截止),才表达得了泰国政策那个「决议已过、
  公报未刊、尚未生效」同时成立的常见状态 —— `GET /api/documents?pending_gazette=true`
  就是靠它把这个窗口期查出来的。
- **词表是真表 + 外键**:未知领域/机关/工具 id 由数据库拒绝,不依赖应用层记得校验。
- 上升话题榜暂无数据源,始终为演示数据。

## 界面

- **今日**:政策流卡片(领域标签 · 收紧/放宽方向 · 公报编号 · 原文链接 · 人工复核标记)+ 本月风向 + 生效日历
- **检索**:领域 × 机关 × 法律形式 × 状态 × 时间 的分面检索
- **政策详情**:中文摘要 · 关键字段卡 · 生命周期时间线 · 原文对照 · 免责声明
- **演进脉络**:同一议题的"旧规 → 转折 → 补丁 → 决议 → 听证 → 现行版 → 前瞻"完整链条
- **政策维度**:七维分析(工具结构演变 / 工具×目标空白 / 法律形式与强制力 / 作用对象 / 机构联署 / 一致性冲突检测 / 执行完整度)
- **趋势看板**:发文量时序 · 风向指数 · 部委活跃度热力 · 上升话题榜
- **采集状态**:数据源健康 · 每日运行记录 · 翻译队列 · 数据新鲜度
- **统计后台** `/admin`(站长):浏览/访客 · 热门政策 · 来源与 UTM · 站内检索词与零结果检索 ·
  外链(官方原文)点击 · 广告 CTR · 打赏漏斗 · 设备/语言/时段。无 Cookie、不存 IP,见 [docs/analytics.md](docs/analytics.md)

## 数据管线(PoC)

```bash
cd pipeline && pip install -r requirements.txt
python fetch_gazette.py --limit 3   # 皇家公报月度索引 → data/processed/gazette_index.csv
python fetch_cabinet.py --limit 2   # 内阁决议年度数据 → data/processed/cabinet_index.csv
```

数据走 data.go.th 官方开放接口(DGA Open Government License 明确允许复制、传播、再利用),内置礼貌限速;详见 [pipeline/README.md](pipeline/README.md)。

## 自动化采集与呈现

```
GitHub Actions(每天曼谷 07:23)
  └─ app.collect   data.go.th 官方接口 → 佛历换算 → 红线过滤 → 追加 JSONL
  └─ app.enrich    DeepSeek(或 Claude)把泰文标题翻译分类成中文结构化记录(受词表约束,标「未经人工复核」)
  └─ app.export    → data/site/*.json + p/*.html 落地页 + sitemap.xml
  └─ git commit    → GitHub Pages 自动呈现
```

- **失败会响**:所有数据源失败时工作流变红,GitHub 给仓库所有者发邮件;失败事实本身也提交进仓库,
  「采集状态」页显示「管道中断」。取代了原先每天开一个 LLM 会话的方案 —— 那个方案六周零提交却一直显示成功。
- **只呈现可呈现的**:待翻译(无中文标题)与判定无关(人事任免、授勋)的条目只留在 JSONL 审计记录里,
  不会以空标题出现在首页。
- **三条编辑红线机械执行**:王室相关标题连模型都不发;模型只能从词表枚举里选 id,返回后再校验一次;
  没有日期不入库,没有官方链接不编。全部有测试覆盖。
- 翻译模型:配了 `DEEPSEEK_API_KEY` 用 DeepSeek,否则用 Claude(`ANTHROPIC_API_KEY`);都没配时翻译步骤自动跳过,采集照常。

上线步骤见 [docs/deploy.md](docs/deploy.md),营收与广告位见 [docs/monetization.md](docs/monetization.md)。

**注意**:泰国政府站点可能拦截海外 IP。GitHub Actions 跑在美国;第一次运行若数据源 403,
在仓库 Secrets 里配 `THAI_EGRESS_PROXY`(泰国出口代理)后重跑。

## 设计原则(合规红线,见调研报告第七章)

1. 只处理官方文本 —— 泰国《版权法》B.E. 2537 第 7 条:法律、公告、判决及官方报告不受版权保护;
2. 王室相关内容零加工、零评论;
3. 名单类公告不建人名索引(PDPA);
4. 每条内容附泰文原文链接与公报编号,非官方翻译、以原文为准。

## 路线图

原型(本仓库)→ 公报/决议管线打通 → LLM 翻译分类流水线 → 上线最简站点(政策流+检索)→ 订阅推送 → 趋势/维度分析 → 企业监测订阅。

## License

MIT — 演示数据均为虚构示例;正式数据以泰国皇家公报及各部委官方发布为准。
