#!/bin/sh
# 每天由 cron 调用:备份 Postgres(统计数据只在数据库里,事实层另有 git 兜底)。保留 14 天。
set -eu
cd "$(dirname "$0")/.."
DIR=/opt/backups/thai-policy
mkdir -p "$DIR"
docker compose -f docker-compose.yml exec -T db \
  pg_dump -U policy -d policy | gzip > "$DIR/policy-$(date +%F).sql.gz"
find "$DIR" -name 'policy-*.sql.gz' -mtime +14 -delete
