#!/usr/bin/env bash
# 钱来钱往记账 · 服务器一键部署
#
# 首次安装与后续升级都用这一条命令（可重复执行，已存在的 .env 不会被覆盖）。
#
# 前置：代码已在 /opt/family-ledger（含 backend/ deploy/ frontend/dist/）
#   走 GitLab：  git clone git@gitlab.company.com:<group>/family-ledger.git /opt/family-ledger
#   走打包包：  mkdir -p /opt/family-ledger
#               tar -xzf family-ledger-deploy.tar.gz -C /opt/family-ledger
#
# 后续发版用 deploy/update.sh（git pull → 重建镜像 → 健康检查）
#
# 用法：
#   bash deploy/install.sh                    # 自动探测公网 IP 填 ALLOWED_HOSTS
#   bash deploy/install.sh your.domain.com    # 指定域名（同时写进 CSRF_TRUSTED_ORIGINS）
#   bash deploy/install.sh your.domain.com,1.2.3.4
#
# 环境变量：
#   SKIP_DOCKER_INSTALL=1   已有 Docker 时跳过检测安装
#   SKIP_CRON=1             不挂备份定时任务

set -euo pipefail

[ -n "${BASH_VERSION:-}" ] || { echo '请用 bash 执行：bash deploy/install.sh（sh 不支持 BASH_SOURCE）' >&2; exit 1; }

DOMAIN="${1:-}"
pub_ip=''
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$INSTALL_DIR/deploy"
ENV_FILE="$DEPLOY_DIR/.env"

c_reset=$'\033[0m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'
info()  { printf '%s\n' "${c_green}[ok]${c_reset} $*"; }
warn()  { printf '%s\n' "${c_yellow}[!!]${c_reset} $*" >&2; }
die()   { printf '%s\n' "${c_red}[xx]${c_reset} $*" >&2; exit 1; }
step()  { printf '\n%s\n' "${c_green}==>${c_reset} $*"; }

rand_str() {
    local n=$1 out=''
    while [ ${#out} -lt "$n" ]; do
        out="${out}$(openssl rand -base64 48 | tr -d '\n/+=')"
    done
    printf '%s' "${out:0:$n}"
}

detect_public_ip() {
    local ip=''
    for url in https://api.ipify.org https://ifconfig.me/ip https://ip.sb; do
        ip=$(curl -fsS --max-time 5 "$url" 2>/dev/null | head -1 | tr -d '[:space:]') || ip=''
        if printf '%s' "$ip" | grep -qE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
            printf '%s' "$ip"; return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------- 1. 环境
step '检查运行环境'
[ "$(id -u)" -eq 0 ] || die '请用 root 执行（或 sudo bash install.sh）'
command -v openssl >/dev/null 2>&1 || die '缺少 openssl，先装：apt install -y openssl'

if [ "${SKIP_DOCKER_INSTALL:-0}" != '1' ]; then
    if ! command -v docker >/dev/null 2>&1; then
        step '未检测到 Docker，用官方脚本安装'
        warn '国内服务器若长时间卡住：Ctrl+C 后改用阿里云镜像'
        warn '  curl -fsSL https://get.docker.com | sh -s -- --mirror Aliyun'
        command -v curl >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y curl; }
        curl -fsSL https://get.docker.com | sh
        systemctl enable --now docker 2>/dev/null || true
        info 'Docker 安装完成'
    fi
fi

DC='docker compose'
$DC version >/dev/null 2>&1 || DC='docker-compose'
$DC version >/dev/null 2>&1 || die 'docker compose 插件不可用，参考 https://docs.docker.com/compose/install/'

# ---------------------------------------------------------------- 2. 预检
step '预检'
[ -f "$INSTALL_DIR/frontend/dist/index.html" ] \
    || die '缺少 frontend/dist/index.html：先在本机 npm run build，再打包上传'
[ -f "$DEPLOY_DIR/docker-compose.yml" ] || die "找不到 $DEPLOY_DIR/docker-compose.yml"

mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$mem_mb" -lt 1500 ]; then
    warn "内存只有 ${mem_mb}MB：MySQL 8 + 2 个 Python 进程会比较紧张，建议 2G 以上"
else
    info "内存 ${mem_mb}MB"
fi

if command -v ss >/dev/null 2>&1; then
    for p in 80 443; do
        if ss -ltn 2>/dev/null | grep -qE "[:.]${p}([[:space:]]|$)"; then
            warn "端口 ${p} 已被占用，nginx 会起不来：ss -ltnp | grep ':${p}' 查是谁"
        fi
    done
fi

# ---------------------------------------------------------------- 3. 生成 .env
step '准备环境变量'
mkdir -p "$DEPLOY_DIR/certs" "$INSTALL_DIR/backend/logs"

if [ -f "$ENV_FILE" ]; then
    info "沿用现有 $ENV_FILE（不覆盖——改密码会让 web 连不上已初始化的数据库）"
    if [ -n "$DOMAIN" ] && ! grep -qF "$DOMAIN" "$ENV_FILE"; then
        warn "$DOMAIN 不在现有 ALLOWED_HOSTS 里，用它访问会 400；改完需 docker compose restart web"
    fi
else
    pub_ip=''
    if detect_public_ip >/dev/null 2>&1; then pub_ip=$(detect_public_ip); fi
    lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}') || lan_ip=''
    if [ -z "$lan_ip" ]; then
        lan_ip=$(ip -4 addr show scope global 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1) || lan_ip=''
    fi

    hosts='localhost,127.0.0.1'
    if [ -n "$lan_ip" ]; then hosts="${hosts},${lan_ip}"; fi
    if [ -n "$pub_ip" ]; then hosts="${hosts},${pub_ip}"; fi
    if [ -n "$DOMAIN" ]; then hosts="${hosts},${DOMAIN}"; fi

    csrf=''
    if [ -n "$DOMAIN" ]; then csrf="https://${DOMAIN}"; fi

    db_pass=$(rand_str 24)
    root_pass=$(rand_str 24)

    cat > "$ENV_FILE" <<EOF
# 由 deploy/install.sh 自动生成于 $(date '+%F %T')，请勿提交到仓库
DEBUG=False
SECRET_KEY=$(rand_str 50)
ALLOWED_HOSTS=${hosts}
CSRF_TRUSTED_ORIGINS=${csrf}
CORS_ALLOWED_ORIGINS=

DB_HOST=db
DB_PORT=3306
DB_NAME=family_ledger
DB_USER=fl
DB_PASSWORD=${db_pass}
DB_ROOT_PASSWORD=${root_pass}

REDIS_HOST=redis
REDIS_PORT=6379
Q_WORKERS=2

SERVE_WEB=0
WEB_DIST=/app/frontend/dist

# 构建后端镜像时用的 PyPI 源。只有拉官方源慢/超时才需要取消注释，
# 改完执行：docker compose build --no-cache web queue && docker compose up -d
# PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
EOF
    chmod 600 "$ENV_FILE"
    info "已生成 $ENV_FILE（权限 600）"
    if [ -z "$pub_ip" ]; then
        warn '没能自动探测到公网 IP：用公网 IP 访问会 400，请把 IP 手动加进 .env 的 ALLOWED_HOSTS'
    fi
    if [ -z "$csrf" ]; then
        warn '没给域名：CSRF_TRUSTED_ORIGINS 为空，/django-admin 登录会被拒（H5 走 JWT 不受影响）'
    fi
fi

# ---------------------------------------------------------------- 4. 启动
step '构建并启动容器（首次要拉镜像 + 装 Python 依赖 + 建表，慢是正常的）'
cd "$DEPLOY_DIR"
if ! $DC up -d --build; then
    warn '启动失败，公司内网机器按这个顺序排查：'
    warn '  1) 拉不到 python:3.12-slim / mysql:8.0 —— 配镜像加速或公司私有仓库：'
    warn '     写 /etc/docker/daemon.json 后 systemctl restart docker'
    warn '       { "registry-mirrors": ["https://你的加速地址"] }'
    warn '     公司 Harbor：docker pull harbor.xxx/python:3.12-slim && docker tag ... python:3.12-slim'
    warn '  2) pip 装依赖超时 —— 在 deploy/.env 加一行后重跑本脚本：'
    warn '       PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/'
    warn '  3) 被 OOM 杀掉 —— dmesg | tail -20'
    die 'docker compose up 失败'
fi

# ---------------------------------------------------------------- 5. 健康检查
step '等待服务就绪'
if command -v curl >/dev/null 2>&1; then
    ok=0
    for _ in $(seq 1 40); do
        if curl -fsS --max-time 5 http://127.0.0.1/api/v1/core/health/ >/dev/null 2>&1; then ok=1; break; fi
        sleep 3
    done
    if [ "$ok" -eq 1 ]; then
        info '健康检查通过'
    else
        $DC ps || true
        $DC logs --tail 40 web || true
        die '健康检查未通过：常见原因是 migrate 卡住或 .env 里 ALLOWED_HOSTS 不对'
    fi
else
    warn '没装 curl，跳过健康检查：apt install -y curl 后手动 curl http://127.0.0.1/api/v1/core/health/'
fi

# ---------------------------------------------------------------- 6. 备份定时任务
if [ "${SKIP_CRON:-0}" != '1' ]; then
    step '挂载每日备份'
    chmod +x "$DEPLOY_DIR/backup.sh"
    if command -v crontab >/dev/null 2>&1; then
        if crontab -l 2>/dev/null | grep -q 'family-ledger'; then
            info '备份定时任务已存在'
        else
            ( crontab -l 2>/dev/null; echo "0 3 * * * $DEPLOY_DIR/backup.sh >> /var/log/fl-backup.log 2>&1" ) | crontab -
            info '已添加：每天 03:00 备份到 /var/backups/family-ledger'
        fi
    else
        warn '没有 crontab，需自己挂定时任务'
    fi
fi

# ---------------------------------------------------------------- 7. 收尾
$DC ps || true
step '部署完成'
printf '%s\n' "访问： http://${DOMAIN:-${pub_ip:-服务器IP}}"

cat <<'EOF'

上线后还要做几件事（都是手工的，不自动执行）：

 1. 立刻注册你和家人的真实手机号账号，然后删掉演示账号：
      docker compose -f /opt/family-ledger/deploy/docker-compose.yml exec web \
        python manage.py shell -c "from apps.users.models import User; \
        User.objects.filter(username__in=['13800138000','13800138001']).delete()"
    （演示账号密码是 test123456，公网可访问时任何人都能登进去看你们家的账）

 2. 去「借钱来往」删掉那条 ¥50,000 的测试借出（它会扣账户余额）

 3. 安全组/防火墙放行 80（以及 443）

 4. 有域名后配 HTTPS：证书放 deploy/certs/{fullchain.pem,privkey.pem}，
    启用 nginx.conf 里注释掉的 443 段，把 .env 的 CSRF_TRUSTED_ORIGINS 改成 https://你的域名，
    然后 docker compose restart nginx

 5. 验证一次备份真的能恢复（没验过的备份不算备份）：
      bash deploy/backup.sh && ls -lh /var/backups/family-ledger

日常命令：
  docker compose logs -f web      # 看日志
  docker compose logs -f queue    # 账单解析、每日资产快照
  docker compose ps               # 五个服务都该是 Up
EOF
