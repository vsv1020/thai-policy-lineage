# 源清单与检索模板

## 一手源(官方,优先;需要出口放行)

| 源 | 地址 | 接入方式 | 覆盖 |
|---|---|---|---|
| 皇家公报月度 JSON | data.go.th `dataset_02_04` | `pipeline/fetch_gazette.py` | 全领域法定底座(ก 类 + ง 类特别号) |
| 内阁决议年度 JSON | data.go.th `dataset_02_03` | `pipeline/fetch_cabinet.py` | 政策上游,比公报提前数周 |
| 公报主站 | ratchakitcha.soc.go.th | PDF 原件(路线图后续) | 原文归档 |
| 税务厅英文站 | rd.go.th/english | 静态 HTML | 税务 |
| BOI | boi.go.th/en | 官方英文 PDF,低频 | 投资优惠 |
| 劳工部 | mol.go.th/en | WordPress,有官方英译 | 劳工/最低工资 |
| 移民局 | immigration.go.th | 需泰国 IP | 签证居留 |
| 法律草案听证 | law.go.th | 二期 | 草案阶段信号 |

出口被拦时全部不可用 —— 这是环境网络策略问题,不是脚本问题,不要改脚本去绕。

## 二手源(重要性信号,WebSearch 可达)

Tilleke & Gibbins、Baker McKenzie Bangkok、Forvis Mazars Thailand、HLB Thailand、KPMG Thailand、Lexology、Expat Tax Thailand、NNT(泰国国家新闻局英文通稿)。

用途:发现线索 + 判断重要性。文号/生效日/层级以其引述的官方信息为准,`verified` 恒为 `false`。

## 检索模板(按领域各 1–2 条)

把 `<本月>` 替换为当前年月,如 `August 2026`。

**税务**
- `Thailand Revenue Department new regulation <本月> Royal Gazette`
- `泰国 税务 新规 <本月> 公报`

**签证居留**
- `Thailand Immigration Bureau visa rule change <本月>`
- `Thailand DTV LTR visa update <本月> announcement`

**公司投资**
- `Thailand BOI announcement investment incentive <本月>`
- `Thailand Foreign Business Act amendment <本月>`

**劳工用工**
- `Thailand minimum wage work permit announcement <本月>`

**房产土地**
- `Thailand Department of Lands foreign ownership regulation <本月>`
- `Thailand condominium foreign quota nominee <本月>`

**兜底(内阁上游)**
- `Thailand cabinet resolution approved <本月> foreign`

## 取舍标准

收:发布日在近 7 天内;有明确发文机关;属五个领域之一;对在泰外籍人士/中资企业有直接影响。

不收:纯新闻评论、中介软文、无机关无日期的传闻、王室相关、含人名名单、已在 `policies[]` 里的同一事项(改原条目而非新增)。
