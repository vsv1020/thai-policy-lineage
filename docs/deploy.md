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
   - `ANTHROPIC_API_KEY` —— 翻译分类用。不配也能跑,但官方接口采回的泰文条目不会上首页。
   - `THAI_EGRESS_PROXY`(可选)—— 形如 `http://user:pass@host:port` 的泰国出口。先不配,看第一次运行结果再决定。
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

## 方案 B:自托管后端

见 [backend/README.md](../backend/README.md) 的部署一节。要点:

- `docker compose up -d --build`,只绑 `127.0.0.1:8000`,前面用 Caddy 做 TLS:
  ```
  你的域名 {
      reverse_proxy 127.0.0.1:8000
  }
  ```
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
- [ ] 首页右上角时间戳、「采集状态」页的源状态与你的预期一致
- [ ] 免责声明在首页页脚、详情页、每个落地页都在

## 日常运维

- 每天看一眼「采集状态」页或 Actions 页面。连续红色 = 出口或数据源出了问题。
- 每周看一次 `/admin` 的「零结果检索」:那是读者在找、站里还没有的主题。
- 「待翻译」队列持续增长 = `ANTHROPIC_API_KEY` 没配或额度用完。
- LLM 翻译的条目一律标「未经人工复核」。人工核对后,在 JSONL 里把 `provenance.verified` 改为 `true`
  并填 `verified_at`,提交即可 —— 这是把内容质量从「能看」变成「可信」的唯一途径。
