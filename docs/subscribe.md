# 订阅:RSS、Telegram 频道、周汇总

本站不收集邮箱(见隐私政策),订阅只提供不需要账号的方式。

## RSS(默认开启,无需配置)
- 全站:`/feed.xml`,最新 50 条。
- 按领域:`/feed/<领域>.xml`,如 `/feed/tax.xml`。首页「订阅更新」卡片里有全部链接。
- 由 `app.export` 生成,`updated` 取数据日期,导出可重复。

## 周汇总(默认开启)
- `/p/week/<YYYY-Www>.html`:按**皇家公报刊登日**分周,每周一页;`/p/week/index.html` 列出全部周。
- 官方数据集比刊登日晚几个月开放,新内容会补进对应的周。

## Telegram 频道(可选)
新上线的政策自动推送到你的公开频道:标题、领域、刊登日、摘要、要点、本站链接与泰文原文链接。

1. Telegram 里找 @BotFather → `/newbot`,得到机器人令牌。
2. 新建一个**公开频道**(例如 @thaipolicy),把机器人加为频道**管理员**(需要「发布消息」权限)。
3. GitHub 仓库 → Settings → Secrets and variables → Actions:
   - Secrets:`TELEGRAM_BOT_TOKEN` = 机器人令牌
   - Variables:`TELEGRAM_CHANNEL` = `@频道名`
4. 把 `config/subscribe.json` 的 `telegram_channel_url` 改成 `https://t.me/频道名` 并提交 —— 首页才会显示 Telegram 按钮。

推送在每日采集之后运行(`python -m app.notify`)。第一次运行只把现有条目记为「已推送」,不会一次推几百条;之后每天最多推 30 条新上线的政策。
已推送记录在 `data/notify/telegram.json`。手动预览:`cd backend && python -m app.notify --dry-run`。
