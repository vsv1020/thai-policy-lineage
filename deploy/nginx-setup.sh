#!/usr/bin/env bash
# 宿主机 nginx 反代 + Let's Encrypt 证书。由 install.sh 调用,也可以单独运行:
#
#   DOMAIN=www.example.com ALT_DOMAIN=example.com bash deploy/nginx-setup.sh
#
# 规则:
# - 每个站点一个 /etc/nginx/conf.d/<裸域>.conf(www.example.com → example.com.conf)
# - 目标文件已存在(且不是本脚本写的临时引导配置)就跳过 —— 服务器上可能有人手工调过
# - 不碰其他站点的配置,不改 /etc/nginx/nginx.conf
# - 先写只有 80 端口的配置 → certbot 申请证书 → 再写完整的 443 配置
# - 每次写入后 nginx -t;失败就回滚到上一份(没有上一份就删掉),保证 nginx 不会挂
#
# 可选环境变量:CERTBOT_EMAIL(证书到期提醒邮箱;不设则不登记邮箱)、APP_PORT(默认 8000)、
# LOG_NAME(日志文件名前缀,默认 thaipolicy)。
# 测试用:NGINX_CONF_DIR、LE_DIR、TEMPLATE、SKIP_PKG_INSTALL=1。
set -euo pipefail

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*"; exit 1; }

: "${DOMAIN:?需要 DOMAIN,例如 DOMAIN=www.example.com}"
ALT_DOMAIN="${ALT_DOMAIN:-}"
HERE=$(cd "$(dirname "$0")" && pwd)
TEMPLATE="${TEMPLATE:-$HERE/nginx.conf.template}"
CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx/conf.d}"
LE_DIR="${LE_DIR:-/etc/letsencrypt}"
APP_PORT="${APP_PORT:-8000}"
LOG_NAME="${LOG_NAME:-thaipolicy}"
CERT_NAME="$DOMAIN"
CONF="$CONF_DIR/${DOMAIN#www.}.conf"
MARKER="thai-policy-lineage bootstrap: 仅 80 端口的临时配置,证书申请成功后会被完整配置替换"
NGINX_ERR=/var/log/nginx/$LOG_NAME.error.log
LE_LOG=/var/log/letsencrypt/letsencrypt.log

reload_nginx() {
  systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null \
    || warn "nginx 未在运行,已跳过 reload(配置已通过 nginx -t)"
}

install_packages() {
  [ "${SKIP_PKG_INSTALL:-0}" = 1 ] && return 0
  local need=()
  command -v nginx >/dev/null || need+=(nginx)
  command -v certbot >/dev/null || need+=(certbot)
  if ! command -v certbot >/dev/null || ! certbot plugins 2>/dev/null | grep -qE '^\* nginx'; then
    need+=(python3-certbot-nginx)
  fi
  [ ${#need[@]} -eq 0 ] && return 0
  say "安装 ${need[*]}"
  if command -v apt-get >/dev/null; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}" >/dev/null
  else
    local pm; pm=$(command -v dnf || command -v yum) || die "不认识的包管理器,请手动安装 ${need[*]}"
    $pm install -y -q "${need[@]}" >/dev/null 2>&1 \
      || { $pm install -y -q epel-release >/dev/null 2>&1 && $pm install -y -q "${need[@]}" >/dev/null; } \
      || die "安装 ${need[*]} 失败"
  fi
  systemctl enable --now nginx >/dev/null 2>&1 || true
}

# render http|full:从模板生成配置。http 只保留 80 端口段;ALT_DOMAIN 为空时去掉跳转段;
# certbot 的 TLS 参数文件、IPv6 不存在时去掉对应行,避免 nginx -t 因为缺文件失败
render() {
  local mode="$1" server_names="$DOMAIN${ALT_DOMAIN:+ $ALT_DOMAIN}"
  awk -v mode="$mode" -v alt="$ALT_DOMAIN" '
    /#@HTTPS_BEGIN/ { inh = 1; next }  /#@HTTPS_END/ { inh = 0; next }
    /#@ALT_BEGIN/   { ina = 1; next }  /#@ALT_END/   { ina = 0; next }
    (inh && mode == "http") { next }
    (ina && alt == "")      { next }
    { print }' "$TEMPLATE" \
  | sed -e "s|{{SERVER_NAMES}}|$server_names|g" -e "s|{{ALT_DOMAIN}}|$ALT_DOMAIN|g" \
        -e "s|{{DOMAIN}}|$DOMAIN|g" -e "s|{{CERT_NAME}}|$CERT_NAME|g" -e "s|{{LE_DIR}}|$LE_DIR|g" \
        -e "s|{{APP_PORT}}|$APP_PORT|g" -e "s|{{LOG_NAME}}|$LOG_NAME|g" \
  | { if [ "$mode" = http ]; then sed "s|{{MARKER}}|$MARKER|"; else sed "s|{{MARKER}}|$DOMAIN|"; fi; } \
  | { [ -f "$LE_DIR/options-ssl-nginx.conf" ] && cat || grep -v 'options-ssl-nginx.conf'; } \
  | { [ -f "$LE_DIR/ssl-dhparams.pem" ] && cat || grep -v 'ssl-dhparams.pem'; } \
  | { [ -f /proc/net/if_inet6 ] && cat || grep -v 'listen \[::\]'; }
}

# apply <文件>:装上新配置并 nginx -t;失败则回滚到上一份并返回 1
apply() {
  local new="$1" backup=""
  if [ -e "$CONF" ]; then backup=$(mktemp); cp -p "$CONF" "$backup"; fi
  cp "$new" "$CONF"
  local out
  if out=$(nginx -t 2>&1); then
    reload_nginx
    [ -n "$backup" ] && rm -f "$backup"
    return 0
  fi
  printf '%s\n' "$out" >&2
  if [ -n "$backup" ]; then mv "$backup" "$CONF"; else rm -f "$CONF"; fi
  if nginx -t >/dev/null 2>&1; then
    warn "新配置未通过 nginx -t,已回滚到上一份,nginx 未受影响"
  else
    warn "回滚后 nginx -t 仍然失败 —— 问题出在其他站点的配置,不是本脚本写的文件,请检查 nginx -t 输出"
  fi
  return 1
}

# ── 已存在就跳过(我们自己写的临时引导配置除外:那说明上次证书没申请成功,继续完成)──
if [ -e "$CONF" ] && ! grep -qF "$MARKER" "$CONF"; then
  warn "$CONF 已存在,不覆盖(可能有人手工调过),跳过 nginx 配置与证书申请。"
  warn "要重新生成:先备份并删除这个文件,再重跑。"
  exit 0
fi

install_packages
mkdir -p "$CONF_DIR"
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT

say "nginx:先装只有 80 端口的配置 → $CONF"
render http > "$TMP"
apply "$TMP" || die "80 端口配置未通过 nginx -t,已回滚"

if [ -f "$LE_DIR/live/$CERT_NAME/fullchain.pem" ]; then
  say "证书已存在:$LE_DIR/live/$CERT_NAME/,跳过申请"
else
  say "申请 Let's Encrypt 证书:$DOMAIN${ALT_DOMAIN:+ + $ALT_DOMAIN}"
  args=(certonly --nginx --non-interactive --agree-tos --cert-name "$CERT_NAME" -d "$DOMAIN")
  [ -n "$ALT_DOMAIN" ] && args+=(-d "$ALT_DOMAIN")
  if [ -n "${CERTBOT_EMAIL:-}" ]; then args+=(--email "$CERTBOT_EMAIL"); else args+=(--register-unsafely-without-email); fi
  args+=(--deploy-hook "systemctl reload nginx")
  if ! certbot "${args[@]}"; then
    warn "证书申请失败。80 端口的临时配置保留,修好后直接重跑即可(脚本会接着完成)。常见原因:"
    warn "  · 域名还没解析到本机,或云安全组没放行 80 端口"
    warn "  · 详细日志:$LE_LOG"
    exit 1
  fi
fi

say "nginx:写入完整的 443 配置"
render full > "$TMP"
apply "$TMP" || die "完整配置未通过 nginx -t,已回滚到 80 端口配置(nginx 未受影响)。排查:$NGINX_ERR"
say "nginx 配置完成:$CONF"
