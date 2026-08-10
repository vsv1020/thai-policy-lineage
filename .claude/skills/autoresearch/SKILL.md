---
name: autoresearch
description: 抓取泰国官方政策最新动态,写入 data/policies/documents.jsonl,重新生成站点数据并推送,使原型站保持最新。用于定时刷新(如每 3 小时一次)或用户手动要求「更新政策数据/更新网页」时。Fetches the latest Thai government policy updates into the normalized data layer, rebuilds the site data, and pushes.
---

# autoresearch —— 定时增量更新政策数据

一次运行 = 一轮增量采集。

**写入 `data/policies/*.jsonl`(规范化事实层),然后跑 `tools/build_site.py` 生成 `data/site/*.json`。**
不要手改 `data/site/` 下的任何文件(那是派生产物,CI 会检查它与源数据一致),
也不要改 `index.html` / `js/`(前端从 JSON 渲染)。

数据分层与字段含义见 [data/README.md](../../../data/README.md)。

## 三条硬红线(违反即中止本条,不写入)

来自 `docs/research-report.md` 第七章,不可协商:

1. **王室相关内容零加工**:只允许原样转载官方文本 + 规范译名,不写摘要、不做方向标注、不评论。拿不准就跳过。`tools/validate.py` 会机械拦截命中王室词的条目。
2. **名单类公告不建人名索引**:归化名单、破产公告、处罚名单只做数量级描述,不写入任何自然人姓名。
3. **不虚构**。没有可核实的发文机关 + 日期就不写入;没拿到原文链接就不写 `sources[].url`,**不要编 URL、不要编公报文号**。宁可这一轮 0 条新增。

## 步骤

### 1. 读取当前状态

```bash
cd <repo> && git fetch origin claude/code-review-loop-autoresearch-pisrof \
  && git checkout claude/code-review-loop-autoresearch-pisrof \
  && git pull origin claude/code-review-loop-autoresearch-pisrof
```

读 `data/policies/sources.json` 的 `last_run_at`(本轮时间下界),
读 `data/policies/documents.jsonl` 的全部 `uid` / `titles.zh` / `doc_no`(去重用)。
读 `data/vocab.json` —— **所有 `*_id` 字段只能取词表里已有的 id**。

### 2. 官方源(首选,可能被网络策略拦截)

```bash
cd pipeline && python3 fetch_gazette.py --limit 1 && python3 fetch_cabinet.py --limit 1
```

成功 → 读 `data/processed/*.csv`,取 `date > last_run_at` 的记录作为候选。
失败(`FetchError` / `ProxyError` / 403) → **不要重试超过一次,不要试图绕过**,继续走第 3 步。
这是预期情况:泰国政府站点对海外 IP 有 WAF 拦截,且本仓库的远程执行环境出口默认只放行
GitHub/包镜像,`data.go.th` 会返回 403 CONNECT。要打通需由用户在环境的网络策略里放行域名
(见 https://code.claude.com/docs/en/claude-code-on-the-web)。

### 3. 公开检索(当前唯一稳定可用的通路)

`WebSearch` 可用(走 API 侧),`WebFetch` 在受限出口下会返回 `EGRESS_BLOCKED` —— 试一次即可。

按领域各检索 1–2 次,查询模板见 `references/sources.md`。只接受**近 7 天内**的信号。

律所/会计师事务所(Tilleke、Baker McKenzie、Mazars、HLB、KPMG)的更新是**重要性信号**
而非一手来源:它们写了 = 值得收录,但文号、生效日期、层级要以正文里引述的官方信息为准,
且 `provenance.verified` 一律为 `false`(校验器会强制这一点)。

### 4. 写入规范化数据

**每条新增 = 往 `data/policies/documents.jsonl` 追加一行。**一行一条,不要重排整个文件
(这样 diff 只有新增行,人工复核时看得清)。字段照抄 data/README.md 的表格,要点:

- `uid`:`TH-<机关缩写>-<YYYYMMDD>-<关键词>`,大写,全库唯一。
- `agency_ids` / `domain_ids` 是**数组** —— 联署文件写多个机关,跨领域写多个领域。
  第一个领域用于首页 chip 配色。
- `dates` 是**分开的字段**:`resolved_at`(决议日)、`published_at`(刊登日)、
  `effective_from` / `effective_to`、`comment_deadline`。**只填知道的,其余留 `null`**。
  日期只精确到月时取月首,并在 `note` 里说明。
- `status_id` 与日期必须自洽:`pending_gazette` 不能有 `published_at`;
  `in_force` 必须有 `effective_from` 或 `published_at`。校验器会查。
- `direction.confidence` 决定它在风向指数里的权重,判不准就填 `low` 或把 `value` 设 `neutral`。
- `confidence.doc_no`:填了 `doc_no` 就必须给可信度,否则清空文号。
- `relations` 要**双向写**:A `supersedes` B,就要给 B 补 `superseded_by` A,否则脉络图少一条边
  (校验器会提醒)。
- `issue_id`:归入已有议题,或在 `issues.jsonl` 新建一个议题并把本条挂进 `stages`。
  **同一议题有新进展时,改 `issues.jsonl` 的 stages,而不是堆一堆孤立文件。**

**去重**:标题高度相似或 `doc_no` 相同 → 同一条。已存在但有新进展(如「待刊公报」→「已刊登」)
时**改那一行**(改 `status_id`、补 `dates.published_at`),不新增。

新发现的周期性法定截止日(报税、备案)写 `deadlines.jsonl`,不要塞进 documents。

**不用手写的东西**(build 会算,写了也会被覆盖):首页 `featured`、风向指数 `wind`、
生效日历 `calendar`、`stats`、各种 `*_label`、趋势聚合。

### 5. 记录本轮运行状态

更新 `data/policies/sources.json`:
- `last_run_at` 改成当前时间,**带 `+07:00` 时区**。这个值同时是 build 的「现在」,
  前端显示的「数据更新 …」也取它。
- 每个源的 `status`(`ok` / `error` / `unattempted`)、`last_ok`、`detail` 都要更新。

### 6. 校验 + 生成 + 提交

```bash
python3 tools/validate.py      # 词表、关系、日期顺序、红线;不过就修数据,别改校验器
python3 tools/build_site.py    # 生成 data/site/*.json(内部会先跑一次校验)
git add data/policies data/site
git commit -m "data: 政策数据增量更新(新增 N 条 / 更新 M 条)"
git push -u origin claude/code-review-loop-autoresearch-pisrof
```

校验报错就**修数据**;不要为了让校验通过去放宽 `tools/validate.py` 的规则。
推送失败(网络)按 2s/4s/8s/16s 退避重试至多 4 次。

**即使 0 条新增也要提交**:第 5 步的 `last_run_at` 与源状态本身就是有信息量的输出,
让页面时间戳诚实反映最后一次尝试。commit message 写
`data: 本轮无新增,刷新采集时间与源状态`。

### 7. 一句话回报

`新增 N 条 / 更新 M 条 / 源:公报 ✗ 决议 ✗ 检索 ✓ / 已推送 <sha>`。
没有新增就直说没有 —— 不要为了显得有产出而堆叙述。

## 不在本流程范围内

- **上升话题榜**没有数据来源(需要关键词提取 + 环比),一直是 `js/app.js` 里的演示数据。
- **趋势看板另三张图**已经接了 `data/site/trends.json`,但数据覆盖不足
  `MIN_TREND_MONTHS` 个月时会自动退回演示数组 —— 这是有意的,不要为了「让图好看」
  去改阈值或补造月份。
- **政策维度页**(七维分析)仍是静态演示内容。它需要 `affected_parties`、`legal_form.stability`
  等字段有足够样本才能真算,数据够了再单独做。
- LLM 泰译中、PDF 抽取、入 PostgreSQL(见 `pipeline/README.md` 路线图)属于后续阶段。
