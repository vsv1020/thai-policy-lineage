#!/bin/sh
# 备用方案:在泰国服务器上直接跑每日采集,不经 GitHub Actions。
#
# 什么时候用:GitHub Actions 用不了(额度、故障、被停用)时。服务器本身就在泰国,不需要出口代理。
# 开启:在 .env 里加
#   COLLECT_ON_SERVER=1
#   GH_PUSH_TOKEN=github_pat_...   # 细粒度令牌,只授权本仓库,权限 Contents: Read and write
#   (DEEPSEEK_API_KEY 已经在 .env 里;翻译要用)
# 之后 dispatch.sh 每天 07 点改为调用本脚本,不再触发 GitHub 的采集工作流;
# GitHub 上的定时备份看到当天已有采集提交会自动跳过。
#
# 做法:在单独的工作目录(不碰正在服务的 /opt/thai-policy-lineage)拉最新 main,用应用镜像起一个
# 临时容器跑「采集 → 翻译 → 校验 → 导出」,与 collect.yml 同一套命令;通过后提交并推回 main。
# 网站随后由 sync.sh 照常同步。手动跑一次:deploy/collect-local.sh
set -eu
cd "$(dirname "$0")/.."
APP_DIR=$(pwd)
get() { grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }

TOKEN=$(get GH_PUSH_TOKEN)
[ -n "$TOKEN" ] || { echo "$(date '+%F %T') 没有配置 GH_PUSH_TOKEN,无法把采集结果推回 GitHub"; exit 1; }
REPO="${GH_REPO:-vsv1020/thai-policy-lineage}"
BRANCH="${BRANCH:-main}"
WORK="${COLLECT_WORKDIR:-/opt/thai-policy-collect}"
DC="docker compose -f $APP_DIR/docker-compose.yml"

# 令牌只放在 git 的凭据头里,不写进远程地址(避免出现在 .git/config 与日志里)
AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
git_auth() { git -c http.extraheader="$AUTH" "$@"; }

if [ ! -d "$WORK/.git" ]; then
  git_auth clone -q --branch "$BRANCH" "https://github.com/$REPO.git" "$WORK"
fi
cd "$WORK"
git_auth fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
git clean -qfd -e var/

TODAY=$(TZ=Asia/Bangkok date +%F)
if git log --since="$TODAY 00:00 +0700" --format=%s "origin/$BRANCH" | grep -q "^data: 每日采集 $TODAY"; then
  echo "$(date '+%F %T') 今天已经采集过,跳过"; exit 0
fi

# 用正在服务的应用镜像(依赖与线上一致);OCR 工具镜像里没有,临时装上(约 30 秒)
CID=$($DC ps -q app)
[ -n "$CID" ] || { echo "应用容器没有在运行,先 docker compose up -d"; exit 1; }
IMG=$(docker inspect --format '{{.Image}}' "$CID")

docker run --rm -v "$WORK":/repo -w /repo/backend \
  -e TZ=Asia/Bangkok -e PYTHONUNBUFFERED=1 \
  -e DATABASE_URL=sqlite:////tmp/collect.db \
  -e ENABLE_SCHEDULER=0 -e EXPORT_AFTER_COLLECT=1 -e ENRICH_AFTER_COLLECT=1 \
  -e ENRICH_MAX_PER_RUN="${ENRICH_MAX_PER_RUN:-300}" \
  -e SITE_URL="$(get SITE_URL | grep . || echo https://www.thaipolicy.com)" \
  -e DEEPSEEK_API_KEY="$(get DEEPSEEK_API_KEY)" -e ANTHROPIC_API_KEY="$(get ANTHROPIC_API_KEY)" \
  "$IMG" sh -c '
    (apt-get update -qq && apt-get install -y -qq poppler-utils tesseract-ocr tesseract-ocr-tha) >/dev/null 2>&1 \
      || echo "OCR 工具没装上,扫描件只看标题"
    python -m app.ingest --reset >/dev/null
    python -m app.collect --trigger server > /repo/collect-result.json
    python ../tools/validate.py --quiet
    python -m app.ingest --reset >/dev/null && python -m app.export >/dev/null'

STATUS=$(python3 -c "import json;print(json.load(open('collect-result.json'))['status'])" 2>/dev/null || echo unknown)
rm -f collect-result.json
git add -A data/policies data/site p feed sitemap.xml robots.txt feed.xml llms.txt llms-full.txt \
  index.html privacy.html about.html
[ -d zh-hant ] && git add -A zh-hant || true
[ -d data/notify ] && git add -A data/notify || true
if git diff --cached --quiet; then
  echo "$(date '+%F %T') 采集完成($STATUS),无变化"; exit 0
fi
git -c user.name="policy-collector[bot]" -c user.email="policy-collector[bot]@users.noreply.github.com" \
  commit -q -m "data: 每日采集 $TODAY · $STATUS(服务器)"
if git_auth push -q origin "HEAD:$BRANCH"; then
  echo "$(date '+%F %T') 采集完成($STATUS),已推送 $(git rev-parse --short HEAD)"
else
  echo "$(date '+%F %T') 推送被拒(main 刚有新提交),下个小时 dispatch 不会重跑;可手动再跑一次本脚本"; exit 1
fi
