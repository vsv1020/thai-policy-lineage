#!/bin/sh
# 由服务器 cron 每小时第 7 分钟调用:到点就让 GitHub 立刻运行对应的工作流。
#
# 为什么:GitHub Actions 的 schedule 只是「尽量准时」,实测本仓库延迟 5 小时甚至整晚不触发。
# 服务器的 cron 是准时的,用它按时触发 workflow_dispatch;工作流里的 schedule 保留作备份,
# 同一天已经由这里触发过的,备份那次会自动跳过(见工作流里的 guard 任务)。
#
# 需要在 .env 里配置 GH_DISPATCH_TOKEN:GitHub 细粒度令牌,只授权本仓库,权限 Actions: Read and write。
# 没配就什么都不做。
set -eu
cd "$(dirname "$0")/.."
TOKEN=$(grep '^GH_DISPATCH_TOKEN=' .env 2>/dev/null | cut -d= -f2- || true)
[ -n "$TOKEN" ] || exit 0
REPO="${GH_REPO:-vsv1020/thai-policy-lineage}"
BRANCH="${BRANCH:-main}"

# 曼谷时间几点 → 跑哪个工作流(可用第一个参数强制指定,手动测试用:dispatch.sh seo.yml)
WF="${1:-}"
if [ -z "$WF" ]; then
  case "$(TZ=Asia/Bangkok date +%H)" in
    03) WF=seo.yml ;;        # 每日 SEO / GEO 监控
    07) WF=collect.yml ;;    # 每日政策采集
    *)  exit 0 ;;
  esac
fi

CODE=$(curl -s -o /tmp/thai-policy-dispatch.out -w '%{http_code}' -m 30 -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/actions/workflows/$WF/dispatches" \
  -d "{\"ref\":\"$BRANCH\"}" || echo 000)
if [ "$CODE" = 204 ]; then
  echo "$(date '+%F %T') 已触发 $WF"
else
  echo "$(date '+%F %T') 触发 $WF 失败:HTTP $CODE $(head -c 300 /tmp/thai-policy-dispatch.out 2>/dev/null)"
  exit 1
fi
