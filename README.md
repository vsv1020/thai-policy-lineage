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
.claude/skills/autoresearch   LLM 采集流程(负责需要判断的那部分)
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

## 原型包含的界面(演示数据)

- **今日**:政策流卡片(领域标签 · 收紧/放宽方向 · 公报编号 · 原文链接 · 人工复核标记)+ 本月风向 + 生效日历
- **检索**:领域 × 机关 × 法律形式 × 状态 × 时间 的分面检索
- **政策详情**:中文摘要 · 关键字段卡 · 生命周期时间线 · 原文对照 · 免责声明
- **演进脉络**:同一议题的"旧规 → 转折 → 补丁 → 决议 → 听证 → 现行版 → 前瞻"完整链条
- **政策维度**:七维分析(工具结构演变 / 工具×目标空白 / 法律形式与强制力 / 作用对象 / 机构联署 / 一致性冲突检测 / 执行完整度)
- **趋势看板**:发文量时序 · 风向指数 · 部委活跃度热力 · 上升话题榜

## 数据管线(PoC)

```bash
cd pipeline && pip install -r requirements.txt
python fetch_gazette.py --limit 3   # 皇家公报月度索引 → data/processed/gazette_index.csv
python fetch_cabinet.py --limit 2   # 内阁决议年度数据 → data/processed/cabinet_index.csv
```

数据走 data.go.th 官方开放接口(DGA Open Government License 明确允许复制、传播、再利用),内置礼貌限速;详见 [pipeline/README.md](pipeline/README.md)。

## 自动更新

分两层,互不重叠:

**① 确定性采集(每天一次,后端自动)** —— `backend/app/collect.py`:
取 data.go.th 官方 CKAN 接口 → 佛历换算 → 红线过滤 → 追加 JSONL → 入库 → 导出静态 JSON。
默认曼谷时间每天 07:23 由进程内定时器触发(可改用系统 cron,见 backend/README.md)。
每次运行在 `collect_runs` 表留一条记录,`GET /api/runs` 可查。

**② 需要判断的部分(LLM 流程)** —— [.claude/skills/autoresearch](.claude/skills/autoresearch/SKILL.md):
公开检索发现的线索,经人可复核的判断后写成结构化记录。为什么分开:自动写入必须可复现、
可审计,「检索摘要 → 带文号带机关带日期的记录」中间那一步判断应该发生在人能复核的地方。

两层共用三条编辑红线(王室零加工 / 不建人名索引 / 不虚构文号与链接),
在 `collect.normalize_*()` 与 `tools/validate.py` 里**机械执行**并有测试覆盖;
自动采集的条目 `verified` 恒为 `false`(校验器强制),人工复核后才改 `true`。

**注意**:泰国政府站点对海外 IP 有 WAF 拦截。受限出口环境下 `data.go.th` 返回 403,
采集会诚实记为 `error` 并继续,页面右上角显示「N 个源均未接通」。生产部署建议用泰国出口。

## 设计原则(合规红线,见调研报告第七章)

1. 只处理官方文本 —— 泰国《版权法》B.E. 2537 第 7 条:法律、公告、判决及官方报告不受版权保护;
2. 王室相关内容零加工、零评论;
3. 名单类公告不建人名索引(PDPA);
4. 每条内容附泰文原文链接与公报编号,非官方翻译、以原文为准。

## 路线图

原型(本仓库)→ 公报/决议管线打通 → LLM 翻译分类流水线 → 上线最简站点(政策流+检索)→ 订阅推送 → 趋势/维度分析 → 企业监测订阅。

## License

MIT — 演示数据均为虚构示例;正式数据以泰国皇家公报及各部委官方发布为准。
