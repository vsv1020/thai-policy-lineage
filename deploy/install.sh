#!/usr/bin/env bash
# 一键部署到一台全新的 Linux 服务器(Ubuntu / Debian / CentOS / Alibaba Cloud Linux)。
#
#   git clone https://github.com/vsv1020/thai-policy-lineage.git /opt/thai-policy-lineage
#   bash /opt/thai-policy-lineage/deploy/install.sh
#
# HTTPS 由宿主机 nginx + certbot 负责(deploy/nginx-setup.sh):每个站点一个 conf.d 文件,
# 不碰同机其他站点;应用容器只绑 127.0.0.1:8000。
#
# 可选环境变量:
#   DOMAIN=example.com   正式域名(先把 A 记录指到本机);不填则沿用 .env 里的,再没有就用
#                        <IP>.sslip.io 临时域名(certbot 同样能签证书)
#                        填 www.example.com 时,example.com 自动 301 跳到 www;反之亦然
#   BRANCH=main          跟踪的分支
#   CERTBOT_EMAIL=...    证书到期提醒邮箱(可不填)
#
# 可重复运行:已有的 .env 密钥会保留;已有的 nginx 站点配置不会被覆盖。
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/vsv1020/thai-policy-lineage.git}"
APP_DIR="${APP_DIR:-/opt/thai-policy-lineage}"
BRANCH="${BRANCH:-main}"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 运行"

# ── 1. 基础工具 ──
say "安装基础工具"
if command -v apt-get >/dev/null; then
  apt-get update -qq && apt-get install -y -qq git curl openssl ca-certificates cron >/dev/null
  systemctl enable --now cron >/dev/null 2>&1 || true
elif command -v dnf >/dev/null || command -v yum >/dev/null; then
  PM=$(command -v dnf || command -v yum)
  $PM install -y -q git curl openssl ca-certificates cronie >/dev/null
  systemctl enable --now crond >/dev/null 2>&1 || true
fi

PUBLIC_IP=$(curl -fsS -m 8 https://api.ipify.org 2>/dev/null || curl -fsS -m 8 https://ifconfig.me 2>/dev/null \
            || hostname -I | awk '{print $1}')
COUNTRY=$(curl -fsS -m 8 "https://ipinfo.io/${PUBLIC_IP}/country" 2>/dev/null | tr -d '[:space:]' || true)
[ -z "${DOMAIN:-}" ] && [ -f "$APP_DIR/.env" ] && DOMAIN=$(grep '^DOMAIN=' "$APP_DIR/.env" | cut -d= -f2 || true)
DOMAIN="${DOMAIN:-${PUBLIC_IP//./-}.sslip.io}"
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"   # 容错:误填了协议或路径
# 另一种写法统一跳转到 DOMAIN;临时域名与多级子域名不处理
case "$DOMAIN" in
  *.sslip.io) ALT_DOMAIN="" ;;
  www.*)      ALT_DOMAIN="${DOMAIN#www.}" ;;
  *.*.*)      ALT_DOMAIN="" ;;
  *)          ALT_DOMAIN="www.$DOMAIN" ;;
esac
echo "公网 IP:$PUBLIC_IP  所在地:${COUNTRY:-未知}  域名:$DOMAIN"

if [ "$COUNTRY" = "CN" ]; then
  warn "服务器在中国大陆:80/443 端口上的任何域名都需要 ICP 备案,未备案会被云厂商拦截。"
  warn "本站面向在泰华人,建议换到阿里云曼谷/新加坡/香港地域的服务器。"
fi

# ── 2. Docker ──
if ! command -v docker >/dev/null; then
  say "安装 Docker"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  MIRROR=""; [ "$COUNTRY" = "CN" ] && MIRROR="--mirror Aliyun"
  if ! sh /tmp/get-docker.sh $MIRROR; then
    # Alibaba Cloud Linux 等发行版官方脚本不认,改用 CentOS 源安装
    command -v dnf >/dev/null || die "Docker 安装失败,请按 https://docs.docker.com/engine/install/ 手动安装后重跑"
    dnf install -y -q dnf-plugins-core >/dev/null
    dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
    dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  fi
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 || die "缺少 docker compose 插件,请安装 docker-compose-plugin 后重试"

# ── 3. 代码 ──
say "获取代码($BRANCH)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$BRANCH"
  git -C "$APP_DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q -b "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 4. .env:密钥只生成一次,之后重跑保留 ──
say "写配置 .env"
touch .env && chmod 600 .env
setenv() {   # setenv KEY VALUE [keep]:keep=1 时已有值不覆盖
  if grep -q "^$1=" .env; then
    [ "${3:-0}" = 1 ] && return 0
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}
setenv POSTGRES_PASSWORD "$(openssl rand -hex 16)" 1
setenv ADMIN_TOKEN "$(openssl rand -hex 24)" 1
setenv STATS_SECRET "$(openssl rand -hex 24)" 1
setenv DOMAIN "$DOMAIN"
setenv ALT_DOMAIN "$ALT_DOMAIN"
setenv SITE_URL "https://$DOMAIN"
setenv CORS_ORIGINS "https://$DOMAIN"
# 采集由 GitHub Actions 负责并提交进仓库;服务器每小时同步,不自己采集,避免两个采集器各写各的
setenv ENABLE_SCHEDULER 0
setenv BRANCH "$BRANCH"

# ── 5. DNS 检查(sslip.io 自动解析,不用检查)──
for H in $DOMAIN $ALT_DOMAIN; do
  [[ "$H" == *.sslip.io ]] && continue
  RESOLVED=$(getent ahostsv4 "$H" | awk 'NR==1{print $1}' || true)
  if [ "$RESOLVED" != "$PUBLIC_IP" ]; then
    warn "$H 当前解析到「${RESOLVED:-无}」,不是本机 $PUBLIC_IP。"
    warn "先去域名注册商加 A 记录 → $PUBLIC_IP,生效后重跑本脚本;否则 HTTPS 证书会申请失败。"
  fi
done

# ── 6. 启动 ──
say "构建并启动(首次约 3–5 分钟)"
DC="docker compose -f docker-compose.yml"
# --remove-orphans:清掉旧版本留下的 caddy 容器(改用宿主机 nginx 之前的部署方式)
$DC up -d --build --remove-orphans

say "等待服务就绪"
for i in $(seq 1 60); do
  if curl -fsS -m 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 3
  [ "$i" = 60 ] && { $DC logs --tail 50 app; die "应用 3 分钟内没有起来,日志见上"; }
done
curl -fsS http://127.0.0.1:8000/api/health; echo

# ── 6b. HTTPS:宿主机 nginx + Let's Encrypt ──
# 失败不中断部署:应用已经在跑,修好 DNS/安全组后重跑本脚本即可接着完成
DOMAIN="$DOMAIN" ALT_DOMAIN="$ALT_DOMAIN" CERTBOT_EMAIL="${CERTBOT_EMAIL:-}" \
  bash "$APP_DIR/deploy/nginx-setup.sh" \
  || warn "nginx / 证书这一步没有完成(原因见上),应用容器不受影响;修好后重跑本脚本"

# ── 7. 定时任务:每小时同步、每天备份 ──
say "安装定时任务"
cat > /etc/cron.d/thai-policy <<CRON
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# 每小时同步 GitHub 上的数据与代码(Actions 每天 07:23 曼谷时间采集后提交)
17 * * * * root BRANCH=$BRANCH $APP_DIR/deploy/sync.sh >> /var/log/thai-policy-sync.log 2>&1
# 每天 03:40 备份数据库,保留 14 天
40 3 * * * root $APP_DIR/deploy/backup.sh >> /var/log/thai-policy-backup.log 2>&1
# 准时触发 GitHub 工作流(03 点 SEO 监控、07 点采集;GitHub 自带的定时常延迟数小时)。
# 需要 .env 里的 GH_DISPATCH_TOKEN,没配则什么都不做
7 * * * * root BRANCH=$BRANCH $APP_DIR/deploy/dispatch.sh >> /var/log/thai-policy-dispatch.log 2>&1
CRON
chmod 644 /etc/cron.d/thai-policy

# ── 8. 外网自检 ──
say "自检"
sleep 5
CODE=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "https://$DOMAIN/api/health" || true)
if [ "$CODE" = 200 ]; then
  echo "HTTPS 正常:https://$DOMAIN"
else
  warn "https://$DOMAIN 暂时不通(HTTP ${CODE:-000})。常见原因:"
  warn "  · 云控制台的安全组没放行 80 和 443 端口(阿里云:ECS → 安全组 → 入方向加 80、443)"
  warn "  · 域名还没解析到本机"
  warn "  · nginx:nginx -t 检查配置;错误日志 /var/log/nginx/thaipolicy.error.log"
  warn "  · 证书:/var/log/letsencrypt/letsencrypt.log"
fi
TH=$(curl -s -o /dev/null -m 15 -w '%{http_code}' https://data.go.th/ || true)
echo "本机访问泰国政府开放数据 data.go.th:HTTP ${TH:-000}(200 = 这台机器可以当采集出口)"

ADMIN_TOKEN=$(grep '^ADMIN_TOKEN=' .env | cut -d= -f2)
cat <<DONE

────────────────────────────────────────────
  部署完成
  网站        https://$DOMAIN${ALT_DOMAIN:+(https://$ALT_DOMAIN 自动跳转过来)}
  统计后台    https://$DOMAIN/admin
  后台令牌    $ADMIN_TOKEN
              (保存在 $APP_DIR/.env,不要发给别人)
  API 文档    https://$DOMAIN/docs

  日志        cd $APP_DIR && $DC logs -f app
  同步日志    tail -f /var/log/thai-policy-sync.log
  换正式域名  A 记录指向 $PUBLIC_IP 后:DOMAIN=你的域名 bash $APP_DIR/deploy/install.sh
────────────────────────────────────────────
DONE
