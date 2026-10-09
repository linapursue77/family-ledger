#!/usr/bin/env bash
# 每日备份：mysqldump 压缩归档，保留最近 30 天
#
# 挂定时任务（每天凌晨 3 点）：
#   0 3 * * * /opt/family-ledger/deploy/backup.sh >> /var/log/fl-backup.log 2>&1
#
# 手动恢复：
#   gunzip < /var/backups/family-ledger/ledger_2026-10-09_0300.sql.gz \
#     | docker compose -f /opt/family-ledger/deploy/docker-compose.yml exec -T db \
#       mysql -uroot -p"$DB_ROOT_PASSWORD" family_ledger

set -euo pipefail
cd "$(dirname "$0")"

BACKUP_DIR=${BACKUP_DIR:-/var/backups/family-ledger}
KEEP_DAYS=${KEEP_DAYS:-30}
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%F_%H%M)
TARGET="$BACKUP_DIR/ledger_${STAMP}.sql.gz"

# --single-transaction：不锁表，线上也能跑
if docker compose exec -T db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  | gzip > "$TARGET"; then
  SIZE=$(du -h "$TARGET" | cut -f1)
  echo "$(date '+%F %T') 备份完成 $TARGET ($SIZE)"
else
  echo "$(date '+%F %T') 备份失败，请检查 db 容器是否在运行" >&2
  rm -f "$TARGET"
  exit 1
fi

find "$BACKUP_DIR" -name 'ledger_*.sql.gz' -mtime "+${KEEP_DAYS}" -delete
