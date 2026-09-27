# 上线手册

## 先选架构

| 方案 | 采集由谁跑 | 呈现 | 需要服务器 | 适合 |
|---|---|---|---|---|
| **A. 纯 GitHub(推荐起步)** | GitHub Actions 每天一次 | GitHub Pages 静态站 | 不需要 | 先上线、先积累 SEO |
| B. 自托管后端 | 后端进程内定时器 | FastAPI 同时出 API 与站点 | 需要(最好在泰国) | 需要分面检索、实时 API |
| C. 两者结合 | GitHub Actions | 服务器 `git pull` 后重新入库 | 需要 | 已有服务器、又想要 git 审计轨迹 |

A 方案下站点的全部页面都能用,唯一退化是检索页的分面下拉(需要后端接口),会显示「静态快照模式」提示。
**不要同时开两个采集器**(Actions 的 schedule 和后端的 `ENABLE_SCHEDULER=1`),会互相覆盖写入。

## 方案 A:纯 GitHub

1. **合并到 `main`**。GitHub 的定时触发器只在默认分支上运行,工作分支上的 `collect.yml` 不会自动跑。
2. **开 Pages**:仓库 Settings → Pages → Source 选 `Deploy from a branch`,分支 `main`,目录 `/ (root)`。
3. **配 Secrets**(Settings → Secrets and variables → Actions):
   - `DEEPSEEK_API_KEY` —— 翻译分类用(DeepSeek 开放平台申请)。也可以改配 `ANTHROPIC_API_KEY` 用 Claude,
     两个都配时默认 DeepSeek。都不配也能跑,但官方接口采回的泰文条目不会上首页。
   - `THAI_EGRESS_PROXY` —— **data.go.th 只允许泰国 IP 访问**,GitHub Actions 在美国,必须配泰国出口。
     支持 `http://user:pass@host:port`、`socks5://user:pass@host:port`、`socks5h://…`(域名由代理端解析)。
     只用于访问泰国政府数据源,DeepSeek、git push 不走它。
4. **配 Variables**:`SITE_URL` = 你的正式域名(无结尾斜杠)。落地页 canonical 与 sitemap 都用它。
5. **手动跑一次**:Actions → 每日政策采集 → Run workflow。看运行摘要:
   - 数据源 `ok` → 出口没问题,之后每天曼谷时间 07:23 自动跑。
   - 数据源 `error: 403` → 泰国站点拦了 GitHub 的美国 IP,配 `THAI_EGRESS_PROXY` 后重跑。
   - **全部源失败时这次运行会变红,GitHub 会给仓库所有者发邮件。** 不会再有「显示成功、实际零产出」。
6. **第一次真采到数据后**,检查 `data/policies/documents.jsonl` 新增行的 `titles.th` 与 `dates.published_at`。
   如果标题为空或日期全是 null,是 `backend/app/collect.py` 里 `pick()` 的键名没对上真实 JSON —— 那套映射是按文档写的,没见过真数据,第一次校准是预期内的。
7. **提交 sitemap**:Google Search Console 添加站点,提交 `https://你的域名/sitemap.xml`。

### 绑定自定义域名

Pages → Custom domain 填域名,DNS 加 CNAME 指向 `vsv1020.github.io`,勾 Enforce HTTPS。
然后把 Variables 里的 `SITE_URL` 改成新域名,手动跑一次采集工作流让落地页重新生成。

## 方案 B0:一键脚本(推荐)

一台全新的 Linux 服务器(Ubuntu / Debian / CentOS / Alibaba Cloud Linux),root 登录后:

```bash
git clone https://github.com/vsv1020/thai-policy-lineage.git /opt/thai-policy-lineage
bash /opt/thai-policy-lineage/deploy/install.sh                       # 先用 <IP>.sslip.io 临时域名
DOMAIN=你的域名 bash /opt/thai-policy-lineage/deploy/install.sh        # 买好域名、A 记录生效后重跑
```

脚本做的事:装 Docker → 拉代码 → 生成 `.env`(数据库密码、`ADMIN_TOKEN`、`STATS_SECRET` 随机生成,
重跑不会覆盖)→ Postgres + 应用启动 → 宿主机 nginx 配置 + Let's Encrypt 证书 → 装定时任务 → 自检。
最后会打印网址、统计后台地址和后台令牌。

- **云安全组要放行 80 和 443**(阿里云:ECS → 安全组 → 入方向),脚本改不了这个。
- **HTTPS 用宿主机 nginx**(`deploy/nginx-setup.sh`,模板 `deploy/nginx.conf.template`):
  写 `/etc/nginx/conf.d/<裸域>.conf`,先只装 80 端口 → certbot 申请证书 → 再写 443;
  每一步 `nginx -t`,失败自动回滚。**文件已存在就跳过**,不碰同机其他站点,不改 `nginx.conf`。
  排查:`nginx -t`、`/var/log/nginx/thaipolicy.error.log`、`/var/log/letsencrypt/letsencrypt.log`。
- **服务器在中国大陆**:任何域名走 80/443 都需要 ICP 备案,脚本会提示。建议选曼谷/新加坡/香港地域。
- **采集分工**:GitHub Actions 每天采集并提交;服务器每小时 17 分 `deploy/sync.sh` 同步 ——
  只有数据变了就重新入库导出,代码变了就重建镜像。服务器不自己采集,避免两份数据各走各的。
- **备份**:每天 03:40 `deploy/backup.sh` 导出 Postgres 到 `/opt/backups/thai-policy/`,保留 14 天。
  统计数据只在数据库里,建议再定期拷到别处。
- 自检会顺带测本机能否访问 data.go.th。能访问的话,这台机器可以作为 Actions 的泰国出口
  (`THAI_EGRESS_PROXY`)。
- 在 GitHub 仓库的 Variables 里把 `SITE_URL` 也设成同一个域名,Actions 导出的落地页 canonical 才一致。

## 方案 B:自托管后端

见 [backend/README.md](../backend/README.md) 的部署一节。要点:

- `docker compose up -d --build`,只绑 `127.0.0.1:8000`,前面用宿主机 nginx 做 TLS,
  配置照 `deploy/nginx.conf.template`(或直接跑 `deploy/nginx-setup.sh`)。
  注意反代时 `X-Forwarded-For` 要设成 `$remote_addr`,不能用 `$proxy_add_x_forwarded_for`(可被伪造)。
- 在反向代理后面时 `TRUST_PROXY=1`(限流才能认出真实 IP);直接暴露公网时必须是 `0`。
- 服务器放在泰国(曼谷机房),或给容器配泰国出口,否则采集会一直 403。
- `.env` 里设 `ADMIN_TOKEN` 与 `STATS_SECRET`,即可在 `https://你的域名/admin` 看站点统计,
  见 [analytics.md](analytics.md)。纯 GitHub 方案没有后端,用 Cloudflare Web Analytics。

## 上线前检查清单

- [ ] `cd backend && python3 -m pytest tests -q` 全过(含 `test_security.py`:私有路径一律 404)
- [ ] `curl -s -o /dev/null -w '%{http_code}' https://你的域名/.git/config` 返回 404
- [ ] `https://你的域名/robots.txt` 里的 Sitemap 地址是正式域名
- [ ] `config/ads.json` 的 `enabled` 是你想要的值(默认 false)
- [ ] `/admin` 能用令牌登录;勾上「不统计本机的访问」;没设 `ADMIN_TOKEN` 时 `/api/admin/stats` 返回 404
- [ ] 首页右上角的数据更新时间、后台 `/admin` →「采集状态」的源状态与你的预期一致
- [ ] 免责声明在首页页脚、详情页、每个落地页都在

## 日常运维

- 每天看一眼后台 `/admin` →「采集状态」或 Actions 页面。连续红色 = 出口或数据源出了问题。
- **历史数据**:日常同步每天重新下载最近 3 个月份的官方文件(`SYNC_RESOURCES`),已入库记录在官方源里有改动时随之更新;
  泰文标题变了会自动重新翻译,人工整理的条目不会被覆盖。
  **第一次上线或想补齐历史**:Actions → 每日政策采集 → Run workflow,勾选 **backfill**,会下载回溯期
  (`LOOKBACK_DAYS`,默认 730 天)内的全部月份并翻译,可能要跑一两个小时。
- 泰国官方公报数据集本身滞后数月(2026-09 时最新到 2026-03),趋势页会注明「数据截至 X 月」。
- 每周看一次 `/admin` 的「零结果检索」:那是读者在找、站里还没有的主题。
- 「待翻译」队列持续增长 = 翻译 key(`DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY`)没配或余额用完。
  Actions 运行摘要里「翻译分类」一行会显示用的是哪个模型、成功几条。
- **前台只收录有官方原文的内容**:`sources` 里要有 `{"role": "official", "url": "https://….go.th/…"}`。后台 `/admin#ops`「缺官方原文 · 未上线」列出缺链接的条目,补上并提交后,下次同步自动上线。
- LLM 翻译的条目在数据层记为 `verified=false`(前台不单独标注)。人工核对后,在 JSONL 里把 `provenance.verified` 改为 `true`
  并填 `verified_at`,提交即可 —— 这是把内容质量从「能看」变成「可信」的唯一途径。
