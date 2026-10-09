#!/bin/sh
# 容器启动：等库 → 迁表 → 收静态 → 交给 CMD
# MySQL 容器即便 healthcheck 通过也可能尚未完成初始化，故 migrate 带重试
set -e

cd /app/backend

i=1
until [ $i -gt 30 ]
do
    if python manage.py migrate --noinput; then
        break
    fi
    echo "等待数据库就绪…（第 $i 次，共 30 次）"
    i=$((i + 1))
    sleep 3
done

# admin 静态；失败不阻断启动（用 nginx 发前端时本来也不需要它）
python manage.py collectstatic --noinput || true

# 注册定时任务（资产快照等），幂等；qcluster 没起也只是建了任务不执行
python manage.py setup_schedules || true

exec "$@"
