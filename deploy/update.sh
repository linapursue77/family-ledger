#!/usr/bin/env bash
# 家庭财务通 · 服务器一键发版（代码走 GitLab，服务器上不装 Node）
#
# 用法：
#   bash deploy/update.sh
#
# 做的是：git pull → 重建 web/queue 镜像 → 建表（entrypoint 自动 migrate）→ 健康检查
# 前端 dist 由 nginx 直接挂载，pull 完刷新页面就生效，不用重建镜像。

set -euo pipefail
[ -n "${BASH_VERSION:-}" ] || { echo '请用 bash 执行：bash deploy/update.sh' >&2; exit 1; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$INSTALL_DIR/deploy"

c_reset=$'\033[0m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'
info()  { printf '%s\n' "${c_green}[ok]${c_reset} $*"; }
warn()  { printf '%s\n' "${c_yellow}[!!]${c_reset} $*" >&2; }
die()   { printf '%s\n' "${c_red}[xx]${c_reset} $*" >&2; exit 1; }
step()  { printf '\n%s\n' "${c_green}==>${c_reset} $*"; }

DC='docker compose'
$DC version >/dev/null 2>&1 || DC='docker-compose'

# ---------------------------------------------------------------- 1. 拉代码
step '拉取代码'
cd "$INSTALL_DIR"
[ -d .git ] || die "$INSTALL_DIR 不是 git 仓库：先 git clone 再执行"

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    warn '工作区有本地改动（多半是改过 deploy/.env，正常）；若有冲突 git pull 会失败'
fi

if ! git pull --ff-only; then
    die 'git pull 失败：常见原因是服务器到 GitLab 不通，或 deploy key 没配/没开读权限'
fi
info "当前版本：$(git log -1 --format='%h %ad %s' --date=short)"

if [ ! -f "$INSTALL_DIR/frontend/dist/index.html" ]; then
    die '仓库里没有 frontend/dist/index.html —— 本机 npm run build 后要把 dist 一起提交再 push'
fi

# ---------------------------------------------------------------- 2. 重启
step '重建后端镜像并重启'
cd "$DEPLOY_DIR"
$DC up -d --build

# ---------------------------------------------------------------- 3. 健康检查
step '等待服务就绪'
ok=0
for _ in $(seq 1 40); do
    if curl -fsS --max-time 5 http://127.0.0.1/api/v1/core/health/ >/dev/null 2>&1; then ok=1; break; fi
    sleep 3
done
if [ "$ok" -ne 1 ]; then
    $DC ps || true
    $DC logs --tail 40 web || true
    die '健康检查未通过：docker compose logs -f web 看具体报错'
fi
info '健康检查通过'

# 前端是挂载的，但入口页设了 no-cache；这里确认一下版本文件在不在
if [ -f "$INSTALL_DIR/frontend/dist/index.html" ]; then
    info "前端产物已就位（构建于 $(date -r "$INSTALL_DIR/frontend/dist/index.html" '+%F %T')）"
fi

step '发版完成'
