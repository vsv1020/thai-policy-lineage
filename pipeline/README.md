# 数据管线 PoC

把泰国官方政策数据源接入本项目的第一步:**不硬爬公报主站,优先走官方开放数据接口**。

## 数据源

| 脚本 | 数据集 | 说明 |
|---|---|---|
| `fetch_gazette.py` | data.go.th `dataset_02_04` | 皇家公报月度 JSON 索引(内阁秘书处官方发布,含标题/卷/期/类别/日期/PDF 链接),2023-06 起逐月更新 |
| `fetch_cabinet.py` | data.go.th `dataset_02_03` | 内阁决议年度 JSON(决议库 resolution.soc.go.th 存量约 10.9 万条,政策的"上游"信号) |

## 用法

```bash
pip install -r requirements.txt

python fetch_gazette.py --list       # 查看可用月度资源
python fetch_gazette.py --limit 3    # 下载最近 3 个月并规范化为 CSV
python fetch_cabinet.py --limit 2    # 下载最近 2 个年度决议并规范化
```

输出:

```
data/raw/         原始 JSON 永久归档(抓取层与解析层解耦的基础)
data/processed/   规范化 CSV(gazette_index.csv / cabinet_index.csv)
```

## 注意事项

- **海外 IP**:泰国政府站点对部分海外 IP / 非浏览器 UA 有 WAF 拦截。脚本失败时会给出明确提示;建议在泰国网络环境运行,或设置 `HTTPS_PROXY` 指向泰国出口。
- **礼貌抓取**:内置全局限速(≥1s/请求)、可识别 UA、超时重试 —— 对应泰国《计算机犯罪法》第 10 条(干扰计算机系统)的合规边界,也是对公共服务的基本尊重。
- **字段映射**:公报/决议 JSON 的键名可能是泰文,`KEY_ALIASES` 做宽松映射;遇到未识别结构时原始文件仍完整归档,补充别名后重跑即可。
- **佛历**:泰国公文使用佛历(พ.ศ. = 公历 + 543),`common.be_to_ce()` 统一转换。

## 路线图(对应调研报告第六章)

```
[本 PoC] 官方 JSON 索引 → 结构化 CSV
   ↓ 下一步
PDF 下载(公报原件归档,hash 去重)
   → 文本抽取(PyMuPDF;扫描件转 Typhoon OCR)
   → LLM 批处理:泰译中 + 摘要 + 领域分类 + 字段抽取(生效日期/适用对象/主管部门)
   → PostgreSQL(+pgvector)入库 → Meilisearch 中泰双索引
   → 网站呈现(见仓库根目录原型)+ 订阅推送
```
