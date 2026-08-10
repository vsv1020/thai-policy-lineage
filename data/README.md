# 数据分层

三层,方向严格单向:**词表 → 事实 → 派生**。不要跨层写。

```
data/vocab.json              ① 受控词表:领域/机关/法律形式/状态/方向/关系/作用对象
data/policies/*.jsonl        ② 事实层(唯一手写/采集写入的地方)
data/site/*.json             ③ 派生层(tools/build_site.py 生成,禁止手改)
data/raw/ data/processed/     pipeline 抓取的原始归档与 CSV(不入库控)
```

前端只读 ③。CI 会重跑 build 并检查 ③ 与 ②一致 —— 手改 ③ 或改了 ② 忘记重跑,都会让 CI 红。

## ① data/vocab.json

一切 `*_id` 字段的白名单。`tools/validate.py` 从这里读取合法值,所以**新增领域/机关不需要改代码**,
改词表即可(新增领域记得在 `css/main.css` 补一个 `.chip.<chip>::before` 配色)。

`legal_forms[].stability`(1–5)是泰国法律形式的稳定性信号:`พ.ร.บ.`(法律)最稳、
`ประกาศ`(公告)与 `มติ ครม.`(内阁决议)最易变。这个字段直接支撑「政策稳定性风险」的判断。

## ② data/policies/

JSONL(一行一条 JSON),不是 JSON 数组 —— 增量采集只追加/改动单行,diff 干净,
不会因为整文件重排而看不出实际改了什么。

| 文件 | 内容 |
|---|---|
| `documents.jsonl` | 一份政策文件 = 一行 |
| `issues.jsonl` | 一个议题 = 一行,把多份文件串成演进脉络 |
| `deadlines.jsonl` | 周期性法定截止日(报税、年度备案),与文件生效日是不同的东西 |
| `sources.json` | 上次采集时间 + 各数据源健康状态 |

### documents.jsonl 字段

| 字段 | 说明 |
|---|---|
| `uid` | 永久唯一 ID,`TH-<机关>-<YYYYMMDD>-<关键词>`。参照 EUR-Lex 的 CELEX 思路,不随标题变化 |
| `issue_id` | 归属议题,可为 `null` |
| `titles` | `{zh, th, en}` —— 泰文原题是溯源的一部分,拿到就填 |
| `summary_zh` | 中文摘要。不加评论、不加建议 |
| `agency_ids` | **数组**,支持联署(维度五「机构协同」靠它) |
| `domain_ids` | **数组**,支持跨领域;第一个用于 chip 配色 |
| `legal_form_id` | 法律形式,决定稳定性信号 |
| `status_id` | `draft` / `pending_gazette` / `gazetted` / `in_force` / `superseded` / `repealed` / `expired` |
| `direction` | `{value, confidence, method}`。`confidence` 决定它在风向指数里的权重 |
| `doc_no` / `gazette` | 文号;公报的 `{series, volume, part, page}` 拆开存 |
| `dates` | `resolved_at` 决议 / `published_at` 刊登 / `effective_from`…`effective_to` 生效 / `comment_deadline` 意见截止。**只填知道的,其余 `null`** |
| `subjects` | 自由主题标签(尚未受控,量大后再收敛) |
| `affected_parties` | `[{party_id, stance}]` —— 谁被支持、谁被约束(维度四) |
| `relations` | `[{type, uid}]`,**必须双向**。A supersedes B ⇒ B superseded_by A |
| `sources` | `[{role, url, note}]`,`role` ∈ official/secondary/archive。**没链接就别写 url** |
| `provenance` | `{pipeline, run_at, verified, verified_at}`。`pipeline=research` 的条目 `verified` 必须为 `false` |
| `confidence` | 逐字段可信度(`dates` / `doc_no`),这是「可溯源」承诺的落地 |

### 为什么把日期拆成五个字段

这是整个结构化里回报最高的一处。泰国政策的核心事实就是**「决议已过、公报未刊、尚未生效」
三者可以同时成立**,而且生效可以追溯到刊登之前。一个 `date` 字段表达不了这个状态,
「政策生命周期时间线」和「待刊公报」预警都建立在这五个字段上。

## ③ data/site/

| 文件 | 由什么算出 |
|---|---|
| `policies.json` | 摊平的展示视图 + 派生的 `featured` / `wind` / `calendar` / `stats` / 各种 `*_label` |
| `trends.json` | 按月 × 领域的发文量、风向指数;按月 × 机关的活跃度 |
| `lineage.json` | 议题脉络链 |

**风向指数是算出来的,不是填出来的**:`score = Σ(direction.sign × confidence权重) / (Σ权重 + 2)`。
分母加 2 是收缩项,样本少时自动往中性收,避免「1 份文件 = 指数 ±1.0」。

`trends.json` 的 `usable` 在覆盖月份少于 6 个月时为 `false`,前端会退回演示数组 ——
几个点画不出趋势,只会误导。

## build 是纯函数

`build_site.py` 的「现在」取 `sources.json` 的 `last_run_at`,**不是运行时刻**。
所以同样的输入在任何时候重跑都得出逐字节相同的输出,CI 才能用
`git diff --quiet -- data/site/` 判断有没有人手改派生文件或漏跑 build。

## 常用命令

```bash
python3 tools/validate.py     # 校验事实层(词表/关系/日期顺序/编辑红线)
python3 tools/build_site.py   # 重新生成派生层(内部会先校验)
```

## 什么时候该换成数据库

现在这套(git + JSONL + build)在**几万条以内**都够用,而且有数据库给不了的东西:
每次改动都有 commit 记录和 diff、可以 code review、GitHub Pages 直接托管零成本、
整库可离线复现。对一个要求「可溯源」的合规产品,审计轨迹本身就是功能。

该迁 PostgreSQL 的信号是:① 条目破 5 万,build 和 git 操作变慢;
② 需要中泰双语全文检索(Meilisearch/OpenSearch 要一个真源);③ 多人并发写入。
届时上面的字段表基本就是建表语句,`uid` 是主键,`relations` 是一张边表 —— 迁移是直译,不是重写。
