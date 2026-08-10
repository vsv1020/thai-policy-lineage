---
name: autoresearch
description: 抓取泰国官方政策最新动态,写入 data/site/policies.json 并推送,使原型站首页/检索页保持最新。用于定时刷新(如每 3 小时一次)或用户手动要求「更新政策数据/更新网页」时。Fetches the latest Thai government policy updates into the site's data file and pushes.
---

# autoresearch —— 定时增量更新政策数据

一次运行 = 一轮增量采集。**唯一写入目标是 `data/site/policies.json`**;不要手改 `index.html`(前端从该 JSON 渲染,改 HTML 会在下一轮被覆盖式重构,且必然产生样式漂移)。

## 三条硬红线(违反即中止本条,不写入)

来自 `docs/research-report.md` 第七章,不可协商:

1. **王室相关内容零加工**:只允许原样转载官方文本 + 规范译名,不写摘要、不做方向标注、不评论。拿不准就跳过。
2. **名单类公告不建人名索引**:归化名单、破产公告、处罚名单只做数量级描述,不写入任何自然人姓名。
3. **不虚构**。没有可核实的发文机关 + 日期就不写入;没拿到原文链接就把 `source_url` 留空,**不要编 URL、不要编公报文号**。宁可这一轮 0 条新增。

## 步骤

### 1. 读取当前状态

```bash
cd <repo> && git fetch origin claude/code-review-loop-autoresearch-pisrof \
  && git checkout claude/code-review-loop-autoresearch-pisrof && git pull origin claude/code-review-loop-autoresearch-pisrof
```

读 `data/site/policies.json`,记下 `updated_at`(本轮时间下界)与全部 `policies[].id` / `title_zh` / `doc_no`(去重用)。

### 2. 官方源(首选,可能被网络策略拦截)

```bash
cd pipeline && python3 fetch_gazette.py --limit 1 && python3 fetch_cabinet.py --limit 1
```

成功 → 读 `data/processed/*.csv`,取 `date > updated_at` 的记录作为候选,`sources[].status = "ok"`、`last_ok` 填当前时间。

失败(`FetchError` / `ProxyError` / 403) → **不要重试超过一次,不要试图绕过**。把该源标 `status: "error"`、`detail` 写明原因,继续走第 3 步。这是预期情况:泰国政府站点对海外 IP 有 WAF 拦截,且本仓库的远程执行环境出口默认只放行 GitHub/包镜像,`data.go.th` 会返回 403 CONNECT。要打通需由用户在环境的网络策略里放行域名(见 https://code.claude.com/docs/en/claude-code-on-the-web)。

### 3. 公开检索(当前唯一稳定可用的通路)

`WebSearch` 可用(走 API 侧),`WebFetch` 在受限出口下会返回 `EGRESS_BLOCKED` —— 试一次即可,失败就只用 WebSearch 的摘要。

按领域各检索 1–2 次,查询模板见 `references/sources.md`。只接受**近 7 天内**的信号。

律所/会计师事务所(Tilleke、Baker McKenzie、Mazars、HLB、KPMG)的更新是**重要性信号**而非一手来源:它们写了 = 值得收录,但文号、生效日期、层级要以正文里引述的官方信息为准,且 `verified` 一律为 `false`(未经人工复核)。

### 4. 写入 JSON

每条新增追加到 `policies[]`,字段规范:

| 字段 | 规则 |
|---|---|
| `id` | `<机关缩写>-<关键词>-<YYYYMMDD>`,如 `rd-foreign-income-20260812`。必须唯一 |
| `date` | 刊登/发布日 `YYYY-MM-DD`(公历。佛历 −543) |
| `domain` | 只能是 `visa` / `tax` / `biz` / `labor` / `land` —— 前端 CSS 只有这五个 chip 类 |
| `domain_label` | 签证居留 / 税务 / 公司投资 / 劳工用工 / 房产土地 |
| `direction` | `tight`(收紧)/ `loose`(放宽)/ `neutral`。判不准填 `neutral` |
| `summary_zh` | 2–3 句,说清「谁受影响、要做什么、什么时候」。不加评论、不加建议 |
| `legal_form` | 如 `ประกาศ 层级`、`มติ ครม.`、`พ.ร.ฎ.`。层级即稳定性信号,尽量填 |
| `status` | `active` / `soon` / `draft`;`status_label` 是页面上那颗药丸的文字 |
| `source_url` | 官方原文链接优先;只有二手来源时留空(**不填二手链接冒充原文**) |
| `verified` | 本流程产出恒为 `false` |
| `provenance` | 恒为 `"research"` |
| `featured` | 只给最近 6 条以内;`research` 条目满 5 条后,把所有 `demo` 条目的 `featured` 改为 `false` |

同时:
- **去重**:标题高度相似或 `doc_no` 相同 → 视为同一条。已存在但有新进展(如「待刊公报」→「已刊登」)时**改原条目**,不新增。
- `calendar[]`:发现明确的未来截止日/生效日就加一条,并删掉已过期的。
- `wind[]`:只有当某领域本轮新增 ≥2 条且方向一致时才微调 `score`(步长 ≤0.1),否则不动。**不要为了让页面「有变化」而编造指数波动。**
- `stats`:重算 `total` / `research` / `demo`。
- `updated_at`:当前时间,**带 `+07:00` 时区**(前端按曼谷时间显示)。
- `sources[]`:每个源都要更新 `status` / `detail`,页面右上角会显示「源 N/M 可用」。

### 5. 自检

```bash
python3 -m json.tool data/site/policies.json > /dev/null   # JSON 合法
```

再确认:新增条目的 `domain` 都在五个白名单里;没有任何自然人姓名;没有王室相关的加工内容;`source_url` 要么是真链接要么为空。

### 6. 提交推送

```bash
git add data/site/policies.json
git commit -m "data: 政策数据增量更新(新增 N 条 / 更新 M 条)"
git push -u origin claude/code-review-loop-autoresearch-pisrof
```

推送失败(网络)按 2s/4s/8s/16s 退避重试至多 4 次。

**即使 0 条新增也要提交**:刷新 `updated_at` 与 `sources[].status`,让页面上的「数据更新 …」时间戳诚实反映最后一次尝试。commit message 写 `data: 本轮无新增,刷新时间戳与源状态`。

### 7. 一句话回报

`新增 N 条 / 更新 M 条 / 源:公报 ✗ 决议 ✗ 检索 ✓ / 已推送 <sha>`。没有新增就直说没有 —— 不要为了显得有产出而堆叙述。

## 不在本流程范围内

- 趋势看板四张图(`js/app.js` 里的硬编码数组)仍是演示数据。它们需要月级发文量聚合,几十条数据撑不起来;等 `policies[]` 破千条再单独做聚合脚本,**不要用现在的小样本去改那些数组**。
- 政策详情页、演进脉络页、政策维度页也仍是静态演示内容,本流程不碰。
- LLM 泰译中、PDF 抽取、入库(见 `pipeline/README.md` 路线图)属于后续阶段。
