# 政策脉络 · 泰国 — Thai Policy Lineage

> 面向在泰华人的泰国政策中文数据库与预警系统(原型阶段)
> Thai government policy tracker for the Chinese-speaking community — prototype.

**在线原型:** https://vsv1020.github.io/thai-policy-lineage/

泰国政策信息只有泰文、极度分散(公报/移民局/税务厅/BOI 各自发布),中文世界的供给全部停留在"新闻编译"层。本项目要做的是"泰国政策的中文数据库与预警系统":**官方源自动监测 → 可溯源中文结构化 → 归类检索 → 趋势与维度分析 → 订阅预警**。

## 仓库结构

```
index.html            产品原型(纯静态,GitHub Pages 直接访问)
css/ js/              原型样式与逻辑(js/data.js 读派生数据;js/app.js 图表)
data/vocab.json       受控词表:领域/机关/法律形式/状态/关系/作用对象
data/policies/        事实层(JSONL,唯一手写与采集写入的地方)
data/site/            派生层(tools/build_site.py 生成,禁止手改)
tools/                validate.py 校验 · build_site.py 生成
pipeline/             数据管线 PoC:皇家公报 + 内阁决议官方开放数据抓取
.claude/skills/autoresearch   定时增量采集流程
docs/research-report.md   完整调研报告(数据源盘点/竞品/技术架构/合规/商业模式)
```

**没有数据库,是 git 里的结构化文件。**数据分三层单向流动:受控词表 → 事实层(JSONL)
→ 派生层(build 生成),前端只读派生层。字段含义与设计理由见 [data/README.md](data/README.md)。

```bash
python3 tools/validate.py     # 校验:词表成员、关系双向、日期顺序、编辑红线
python3 tools/build_site.py   # 生成 data/site/*.json
```

关键性质:

- **风向指数、生效日历、首页选条、趋势聚合都是算出来的**,不是手填的 —— 结构上排除了
  「为了让页面有变化而编造数字」。
- **build 是纯函数**(「现在」取上次采集时间而非运行时刻),所以 CI 能用
  `git diff --quiet -- data/site/` 抓出手改派生文件或漏跑 build。
- 日期拆成决议/刊登/生效/意见截止四类,才表达得了泰国政策那个「决议已过、公报未刊、
  尚未生效」同时成立的常见状态。
- 派生 JSON 加载失败时页面回退到 HTML 里的静态内容,不白屏。
- 趋势看板在真实数据覆盖不足 6 个月时自动退回演示数组;上升话题榜暂无数据源,始终为演示。

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

`/autoresearch`(定义见 [.claude/skills/autoresearch/SKILL.md](.claude/skills/autoresearch/SKILL.md))每轮做一次增量采集:
官方 JSON 源 → 公开检索兜底 → 去重后写入 `data/site/policies.json` → 提交推送。可挂 3 小时一次的定时任务。

流程内置三条编辑红线(王室零加工 / 不建人名索引 / 不虚构文号与链接),`verified` 恒为 `false`,
人工复核后才手动改为 `true`。

**注意**:泰国政府站点对海外 IP 有 WAF 拦截,受限出口环境下 `data.go.th` 返回 403;
此时流程降级为只用公开检索,并在页面右上角显示「N 个源均未接通」。

## 设计原则(合规红线,见调研报告第七章)

1. 只处理官方文本 —— 泰国《版权法》B.E. 2537 第 7 条:法律、公告、判决及官方报告不受版权保护;
2. 王室相关内容零加工、零评论;
3. 名单类公告不建人名索引(PDPA);
4. 每条内容附泰文原文链接与公报编号,非官方翻译、以原文为准。

## 路线图

原型(本仓库)→ 公报/决议管线打通 → LLM 翻译分类流水线 → 上线最简站点(政策流+检索)→ 订阅推送 → 趋势/维度分析 → 企业监测订阅。

## License

MIT — 演示数据均为虚构示例;正式数据以泰国皇家公报及各部委官方发布为准。
