# 后端服务

Python + FastAPI + SQLAlchemy。一个进程同时提供:**API**、**每日采集定时器**、以及把仓库根当**静态原型站**挂在 `/`。

## 为什么是这套

| 选择 | 理由 |
|---|---|
| FastAPI | 自带 OpenAPI 文档(`/docs`),类型即校验;这套接口以后要给 B 端客户用,文档不能靠手写 |
| SQLAlchemy 2.0 | SQLite 开发 / Postgres 生产同一份模型,不写方言专属 SQL |
| 词表建成真表 + 外键 | 未知领域/机关/工具 id 由数据库拒绝,不依赖应用层记得校验(见 `tests/test_ingest.py`) |
| 关联表而非 JSON 列 | 「机构联署」「工具×目标」就是关联表上的 GROUP BY,不需要在应用层展开数组 |
| APScheduler 进程内 | 部署只有一个进程,不用额外装 cron;想用系统 cron 见下 |

## 快速起步

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env            # 可选,默认值直接能跑(SQLite)

python3 -m app.ingest --reset   # 建表 + 载入词表与事实层
python3 -m app.collect --dry-run  # 探测数据源可达性(不写库)
uvicorn app.main:app --reload --port 8000
```

打开 http://127.0.0.1:8000/ 是原型站(自动走 API),http://127.0.0.1:8000/docs 是接口文档。

## 数据流

```
data/vocab.json ─┐
data/policies/*.jsonl ─┴→ app.ingest ──→ 数据库 ──→ app.api      (前端首选)
                                          │
每日采集 app.collect ──→ 追加 JSONL ───────┤
(官方 data.go.th)   └→ 写库                │
                                          └→ app.export → data/site/*.json (静态降级)
```

JSONL 保留在 git 里作为**可 review 的事实记录**,数据库是它的运行时投影。采集两边都写,不会漂移。
前端三级降级:API → 静态 JSON → HTML 内联占位。

## 常用命令

```bash
python3 -m app.ingest            # 载入/更新(幂等)
python3 -m app.ingest --reset    # 清空事实表后重载(词表保留)
python3 -m app.collect           # 立即跑一轮采集
python3 -m app.collect --dry-run # 只探测源可达性
python3 -m app.export            # 导出静态 JSON
python3 -m pytest tests -q       # 60 个测试
python3 ../tools/validate.py     # 校验 JSONL(纯标准库,无依赖)
```

## 接口

| 路径 | 说明 |
|---|---|
| `GET /api/health` | 存活 + 文件数 + 上次采集结果 |
| `GET /api/overview` | 首页:政策流、风向、生效日历、源状态 |
| `GET /api/trends` | 趋势看板聚合(按月 × 领域 / 机关) |
| `GET /api/dimensions` | 政策维度七维 |
| `GET /api/lineage` | 议题演进脉络 |
| `GET /api/documents` | 分面检索:`q` `domain` `agency` `legal_form` `status` `direction` `date_from` `date_to` `pending_gazette` `limit` `offset` |
| `GET /api/documents/{uid}` | 单件全字段(四类日期、关系、逐字段可信度) |
| `GET /api/vocab` | 受控词表(前端下拉与配色) |
| `GET /api/runs` | 采集运行历史 |

最有价值的一个查询:`GET /api/documents?pending_gazette=true` —— 「内阁已决议但公报未刊」的窗口期条目。
这类状态是泰国政策的常态,也是普通新闻编译看不见的东西。

## 部署

### Docker Compose(推荐)

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
echo "CORS_ORIGINS=https://vsv1020.github.io" >> .env
docker compose up -d --build
```

应用只绑 `127.0.0.1:8000`,前面自己挂 nginx/caddy 做 TLS。`./data` 挂进容器,
采集写入的 JSONL 与导出的 JSON 会落到宿主机,方便 `git commit` 保留审计轨迹。

### systemd(不用容器)

```ini
# /etc/systemd/system/policy-api.service
[Unit]
Description=Thai Policy Lineage API
After=network-online.target

[Service]
WorkingDirectory=/srv/thai-policy-lineage/backend
EnvironmentFile=/srv/thai-policy-lineage/backend/.env
ExecStart=/srv/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
User=policy

[Install]
WantedBy=multi-user.target
```

### 用系统 cron 代替进程内定时器

进程内定时器的缺点是进程崩了就不跑。想更稳:

```bash
# .env 里设 ENABLE_SCHEDULER=0,然后
23 7 * * *  cd /srv/thai-policy-lineage/backend && /srv/venv/bin/python -m app.collect --trigger schedule >> /var/log/policy-collect.log 2>&1
```

系统时区要是 Asia/Bangkok(`timedatectl set-timezone Asia/Bangkok`),否则采集窗口会错开一天。

### Postgres 迁移

模型不含方言专属类型,换 `DATABASE_URL` 再跑 `python3 -m app.ingest` 即可。
目前没上 Alembic —— 表结构还在动,`create_all` + `--reset` 重建更省事。
上线有真实增量数据后应当引入 Alembic,别再靠 `create_all` 改表。

## 采集的边界(重要)

`app.collect` 只做**确定性**的部分:官方 CKAN 接口取回什么就写什么,取不到就诚实记 `error`。
它**不做**公开检索 → 结构化的判断,因为那一步需要人能复核。那部分在
`.claude/skills/autoresearch`(LLM 流程),产出写进 JSONL 留下 git 记录。

三条编辑红线在 `collect.normalize_*()` 里机械执行,有测试覆盖:

1. 王室相关标题一律跳过(`ROYAL_TERMS`)
2. 出现泰文人名前缀一律跳过(不建人名索引)
3. 拿不到可解析日期就不入库,拿不到 PDF 链接就把 `sources` 留空 —— 不编 URL、不编文号

## 已知限制

- **公报索引不含发文机关与领域**,自动入库的条目 `agency_ids` 暂记内阁秘书处口径、
  `domain_ids` 暂记 `biz`,中文标题为空 —— 等 LLM 翻译分类环节补全。这些条目
  `verified=false`,前端不显示「已人工复核」。
- **上升话题榜**没有数据源(需要关键词提取 + 环比),`js/app.js` 里仍是演示数据。
- **趋势四图**在覆盖月份不足 `MIN_TREND_MONTHS` 时退回演示数组;这是有意的。
- 检索用 `LIKE`,几万条以内够用。要做中泰双语相关性排序得上 Meilisearch/OpenSearch。
