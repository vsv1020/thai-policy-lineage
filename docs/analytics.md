# 站点统计

两套可以同时开,看你是否部署了后端:

| | 自建统计(推荐) | Cloudflare Web Analytics / Plausible |
|---|---|---|
| 需要后端 | 是 | 否(纯 GitHub Pages 也能用) |
| 在哪看 | `https://你的域名/admin` | 各自的控制台 |
| 能看到 | 浏览量/访客/来源/热门政策/**站内检索词/零结果检索/官方原文点击/广告 CTR/打赏漏斗**/设备/语言/时段 | 浏览量、来源、页面、国家、设备 |
| Cookie | 无 | 无 |
| 费用 | 0 | Cloudflare 免费;Plausible 付费或自托管 |

**为什么自建是主力**:第三方统计只知道「哪个 URL 被打开了」。这个站真正要回答的问题 ——
读者在搜什么、搜不到什么、广告位给赞助商带来多少点击、有多少人打开打赏弹窗 ——
只有站内事件才能回答。

## 开启自建统计

1. 服务器 `.env` 加两行(`openssl rand -hex 24` 各生成一个):
   ```
   ADMIN_TOKEN=...      # 登录 /admin 用。不设 = 后台关闭(接口 404)
   STATS_SECRET=...     # 访客哈希密钥。不设则每次重启随机,重启当天访客会重复计数
   ```
2. `docker compose up -d` 重启。统计默认开启(`STATS_ENABLED=1`),`config/analytics.json` 的
   `self_hosted.enabled` 默认 `true`。
3. 打开 `https://你的域名/admin`,输入令牌。后台页右上角勾选 **「不统计本机的访问」**,
   把你自己的访问排除掉。
4. 终端也能看:`docker compose exec app python -m app.stats --days 7`。

**前端在 GitHub Pages、后端在另一个域名**:`config/analytics.json` 的 `self_hosted.endpoint`
填后端地址(`https://api.你的域名`),`CORS_ORIGINS` 里加上 Pages 的域名。
后台页在 Pages 上打开 `admin.html`,登录时填后端地址。

## 开启第三方统计

- **Cloudflare Web Analytics**:Cloudflare 控制台 → Web Analytics → 添加站点 → 复制 JS 片段里的
  `token`(32 位十六进制),填到 `config/analytics.json` 的 `cloudflare.token`。
- **Plausible**:`plausible.domain` 填站点域名。
- 改完跑 `python3 tools/validate.py && cd backend && python3 -m app.export`,提交。

## 后台各块怎么用

| 块 | 用来做什么决定 |
|---|---|
| 热门政策(落地页列) | 落地页浏览多 = 搜索引擎开始带流量。优先人工复核这些条目 |
| 站内检索词 | 读者需求的第一手信号 |
| **零结果检索** | **选题清单**:搜了但一条都没有 —— 优先补这些主题 |
| 外链点击(官方) | 读者真的点去看泰文原文 = 「可溯源」被使用的证据 |
| 流量来源 / UTM | 发到微信群、Facebook 群时链接加 `?utm_source=wechat&utm_campaign=xxx`,就能看出哪个群带来了人 |
| 广告位表现 | 每个槽位×赞助方的曝光、点击、CTR;直销续约时截给赞助方 |
| 打赏 | 弹窗打开率、选的金额、入口(顶栏/正文后);实际到账以收款账户为准 |
| 访问时段 | 推送、发社媒的时间参考 |

## 隐私口径

与 `privacy.html`「访问统计」一节一一对应,`backend/tests/test_stats.py` 有测试:

- 不设 Cookie,不用浏览器存储识别用户;
- 不存 IP。访客 = HMAC(密钥, 当天日期 · IP · UA) 前 16 位,跨天不可关联,所以**没有回访率**;
- Do Not Track / Global Privacy Control 开启时前后端都不记;爬虫、curl 等不计入;
- 国家只在 Cloudflare 代理后面且 `TRUST_PROXY=1` 时取 `CF-IPCountry`;
- 原始记录保留 `STATS_RETENTION_DAYS`(默认 400)天,每天自动清理。

改统计口径时,两边一起改。

## 容量

每次浏览或事件写一行。日均一万次浏览,一年约 400 万行 —— SQLite 能扛,Postgres 毫无压力。
流量再大时,把 `/api/t` 的写入改成批量缓冲,或换成专门的统计服务。
