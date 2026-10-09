# -*- coding: utf-8 -*-
"""Django-Q 异步任务（大账单走队列，避免请求超时）。

启动 worker：python manage.py qcluster
"""
import logging

from apps.ledger.models import ImportTask
from apps.ledger.services import build_preview, parse_bytes

logger = logging.getLogger(__name__)


def parse_import_task(task_id: str, data: bytes, platform: str = None) -> dict:
    """后台解析账单并回填预览。由 views.ImportTaskViewSet.create 投递。"""
    task = ImportTask.objects.filter(pk=task_id).first()
    if task is None:
        logger.warning('导入任务不存在 task=%s', task_id)
        return {'ok': False, 'reason': 'task_not_found'}

    try:
        parsed = parse_bytes(data, platform)
        preview = build_preview(parsed['records'], task.family)
    except ValueError as exc:
        task.status = ImportTask.STATUS_FAILED
        task.error_message = str(exc)[:500]
        task.save(update_fields=['status', 'error_message'])
        return {'ok': False, 'reason': str(exc)}

    task.platform = parsed['platform']
    task.status = ImportTask.STATUS_PREVIEW
    task.total_count = preview['stats']['total']
    task.new_count = preview['stats']['new']
    task.duplicate_count = (preview['stats']['duplicate']
                            + preview['stats']['internal_duplicate'])
    task.failed_count = len(parsed['skipped'])
    task.preview = preview['rows']
    task.save(update_fields=['platform', 'status', 'total_count', 'new_count',
                             'duplicate_count', 'failed_count', 'preview'])
    logger.info('后台解析完成 task=%s new=%s', task_id, preview['stats']['new'])
    return {'ok': True, 'stats': preview['stats']}
