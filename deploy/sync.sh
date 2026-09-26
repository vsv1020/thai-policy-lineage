#!/bin/sh
# 每小时由 cron 调用:把 GitHub 上的最新数据/代码同步到服务器。
# 采集由 GitHub Actions 负责(每天曼谷 07:23),服务器只拉取,不自己采集、不提交。
set -eu
cd "$(dirname "$0")/.."
BRANCH="${BRANCH:-main}"
DC="docker compose -f docker-compose.yml -f deploy/compose.caddy.yml"

git fetch -q origin "$BRANCH"
OLD=$(git rev-parse HEAD)
NEW=$(git rev-parse "origin/$BRANCH")
[ "$OLD" = "$NEW" ] && exit 0

# 派生文件(data/site、p/)会被服务器按自己的 SITE_URL 重新导出,本地改动直接丢弃即可;
# .env 是未跟踪文件,reset 不会动它
git reset -q --hard "origin/$BRANCH"
echo "$(date '+%F %T') 同步 ${OLD%"${OLD#???????}"} → ${NEW%"${NEW#???????}"}"

if git diff --name-only "$OLD" "$NEW" | grep -qvE '^(data/|p/|sitemap\.xml$|robots\.txt$)'; then
  echo "代码有变动,重建镜像"
  $DC up -d --build
else
  echo "只有数据变动,重新入库并导出"
  $DC exec -T app sh -c "python -m app.ingest && python -m app.export"
fi
