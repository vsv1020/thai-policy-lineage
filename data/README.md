# 数据分层

三层,方向严格单向:**词表 → 事实 → 派生**。不要跨层写。

```
data/vocab.json              ① 受控词表(同时是数据库词表表的建表来源)
data/policies/*.jsonl        ② 事实层(唯一手写/采集写入的地方)
        ↓ backend/app/ingest.py
   数据库(SQLite 开发 / Postgres 生产)—— 运行时存储,API 从这里查
        ↓ backend/app/export.py
data/site/*.json             ③ 派生层(禁止手改)
data/raw/ data/processed/     早期 pipeline 的原始归档与 CSV(不入库控)
```

前端优先打 API(读数据库),打不通才读 ③。CI 会重跑 ingest+export 并检查 ③ 与 ② 一致 ——
手改 ③ 或改了 ② 忘记重跑,都会让 CI 红。

**为什么 JSONL 和数据库都留着**:数据库是运行时存储(索引、并发、聚合),JSONL 是 git 里
可 diff、可 code review、可离线复现的事实记录。对一个卖「可溯源」的合规产品,审计轨迹
本身就是功能。采集流程两边都写,不会漂移。

## ① data/vocab.json

一切 `*_id` 字段的白名单,**同时是数据库词表各表的数据来源** —— `app.ingest` 把它 upsert 进
`domains` / `agencies` / `legal_forms` / `instruments` / `goals` / … 表,事实表用外键指向它们。
所以未知 id 有两道拦截:`tools/validate.py`(不装包也能跑)和数据库外键。

**新增领域/机关不需要改代码**,改词表即可(新增领域记得在 `css/main.css` 补一个
`.chip.<chip>::before` 配色,并在 `js/app.js` 的 `DOMAIN_COLOR` 里加一项)。

`legal_forms[].stability`(1–5)是泰国法律形式的稳定性信号:`พ.ร.บ.`(法律)最稳、
`ประกาศ`(公告)与 `มติ ครม.`(内阁决议)最易变。这个字段直接支撑「政策稳定性风险」的判断。

## ② data/policies/

JSONL(一行一条 JSON),不是 JSON 数组 —— 增量采集只追加/改动单行,diff 干净,
不会因为整文件重排而看不出实际改了什么。

| 文件 | 内容 |
|---|---|
| `documents.jsonl` | 一份政策文件 = 一行 |
| `issues.jsonl` | 一个议题 = 一行,把多份文件串成演进脉络 |
| `conflicts.jsonl` | 口径冲突(维度六),每条至少两方对照引文 |
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
| `instrument_ids` | 政策工具(维度一/二)。工具归属供给型/环境型/需求型三类 |
| `goal_ids` | 政策目标(维度二的列) |
| `implementation_stage` | 处于「规划→法律→决议→细则→预算→评估」哪一环(维度七) |
| `subjects` | 自由主题标签(尚未受控,量大后再收敛) |
| `affected_parties` | `[{party_id, stance}]` —— 谁被支持、谁被约束(维度四) |
| `relations` | `[{type, uid}]`,**必须双向**。A supersedes B ⇒ B superseded_by A |
| `sources` | `[{role, url, note}]`,`role` ∈ official/secondary/archive。**没链接就别写 url** |
| `provenance` | `{pipeline, run_at, verified, verified_at}`。`pipeline=research` 的条目 `verified` 必须为 `false` |
| `confidence` | 逐字段可信度(`dates` / `doc_no`),这是「可溯源」承诺的落地 |

### 为什么把日期拆成五个字段(而不是一个)

这是整个结构化里回报最高的一处。泰国政策的核心事实就是**「决议已过、公报未刊、尚未生效」
三者可以同时成立**,而且生效可以追溯到刊登之前。一个 `date` 字段表达不了这个状态,
「政策生命周期时间线」和「待刊公报」预警都建立在这五个字段上。

## ③ data/site/

| 文件 | 由什么算出 | 对应接口 |
|---|---|---|
| `policies.json` | 展示视图 + 派生的 `featured` / `wind` / `calendar` / `stats` / 各种 `*_label` | `/api/overview` |
| `trends.json` | 按月 × 领域的发文量、风向指数;按月 × 机关的活跃度 | `/api/trends` |
| `lineage.json` | 议题脉络链 | `/api/lineage` |
| `dimensions.json` | 政策维度七维 | `/api/dimensions` |

**每个统计型维度都带 `n` / `sufficient` / `min_n`**。样本不足时前端显示「数据不足」提示条,
而不是画一张看起来很确定的图。要让维度更准,该做的是给条目补
`instrument_ids` / `goal_ids` / `implementation_stage` / `affected_parties`,**不是降低阈值**。

**风向指数是算出来的,不是填出来的**:`score = Σ(direction.sign × confidence权重) / (Σ权重 + 2)`。
分母加 2 是收缩项,样本少时自动往中性收,避免「1 份文件 = 指数 ±1.0」。

`trends.json` 的 `usable` 在覆盖月份少于 6 个月时为 `false`,前端会退回演示数组 ——
几个点画不出趋势,只会误导。

## 导出是纯函数

分析层的「现在」取 `sources.json` 的 `last_run_at`,**不是运行时刻** ——
生效日历窗口、「已生效」判定、按月分桶都以它为基准。所以同样的输入在任何时候重跑
都得出逐字节相同的输出,CI 才能用 `git diff --quiet -- data/site/` 判断有没有人
手改派生文件或漏跑导出。

## 常用命令

```bash
python3 tools/validate.py                  # 校验事实层(纯标准库,无需装包)
cd backend
python3 -m app.ingest                      # 事实层 → 数据库(幂等)
python3 -m app.export                      # 数据库 → data/site/*.json
python3 -m pytest tests -q                 # 60 个测试
```

## SQLite 还是 Postgres

模型不含方言专属类型,换 `DATABASE_URL` 即可,`python3 -m app.ingest` 重新载入。

- **SQLite**:开发、单机部署、几万条以内。注意 `app/db.py` 里显式打开了
  `PRAGMA foreign_keys=ON`(SQLite 默认关闭,不开等于没有词表约束)和 WAL(采集写 / API 读并发)。
- **Postgres**:多进程、并发写、要上全文检索时。`docker-compose.yml` 里已经配好。

目前没上 Alembic —— 表结构还在动,`create_all` + `--reset` 重建更省事。
有真实增量数据后应当引入 Alembic,别再靠 `create_all` 改表。
