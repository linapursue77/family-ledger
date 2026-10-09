# -*- coding: utf-8 -*-
"""账本服务层：账户余额、账单导入预览与入库。

导入流程（PRD 4.3）：
    上传 CSV → 解析 → 去重打标 → 规则分类 → 预览（新增/重复/待确认）
    → 用户勾选 → 确认入库（批量事务 + 账户余额同步）
"""
import logging
from datetime import datetime

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Account
from apps.ledger.models import Category, ImportTask, Transaction
from domain.classify import classify
from domain.dedup import mark_statuses
from domain.parse.statement import parse_statement

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # 10MB
ASYNC_THRESHOLD_BYTES = 512 * 1024         # 超过则投递 Django-Q 后台解析
MAX_PREVIEW_ROWS = 5000                    # 预览入库上限，防止 JSON 过大
BATCH_SIZE = 500


def apply_balance(account, tx_type: str, amount_cents: int, reverse: bool = False):
    """支出减、收入加、转账不动。reverse=True 表示冲正。"""
    if account is None or tx_type == 'transfer':
        return 0
    sign = 1 if tx_type == 'income' else -1
    if reverse:
        sign = -sign
    delta = sign * int(amount_cents)
    Account.objects.filter(pk=account.pk).update(balance_cents=F('balance_cents') + delta)
    account.balance_cents = (account.balance_cents or 0) + delta
    return delta


def parse_bytes(data: bytes, platform: str = None) -> dict:
    """解析账单字节流。抛 ValueError 表示文件不可解析。"""
    if not data:
        raise ValueError('文件内容为空')
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f'文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限')
    return parse_statement(data, platform)


def parse_upload(file_obj, platform: str = None) -> dict:
    """读取上传文件并解析。抛 ValueError 表示文件不可解析。"""
    return parse_bytes(file_obj.read(), platform)


def build_preview(records: list[dict], family) -> dict:
    """去重打标 + 规则分类，返回预览行与统计。"""
    dates = [r.get('transaction_date') for r in records if r.get('transaction_date')]
    existing = _existing_hashes(family, min(dates) if dates else None,
                                max(dates) if dates else None)

    mark_statuses(records, existing)
    valid_categories = set(Category.objects.values_list('id', flat=True))

    rows = []
    uncategorized = 0
    for idx, record in enumerate(records[:MAX_PREVIEW_ROWS]):
        category_id, source = classify(record.get('merchant') or '')
        if category_id not in valid_categories:
            category_id, source = 'other', 'default'
        if source == 'default':
            uncategorized += 1
        rows.append({
            'i': idx,
            'status': record.get('status'),
            'date': record.get('transaction_date'),
            'type': record.get('type'),
            'amount_cents': record.get('amount_cents'),
            'merchant': record.get('merchant'),
            'desc': record.get('description'),
            'category': category_id,
            'category_source': source,
            'need_confirm': source == 'default',
            'dedup_hash': record.get('dedup_hash'),
        })

    stats = {
        'total': len(records),
        'new': sum(1 for r in rows if r['status'] == 'new'),
        'duplicate': sum(1 for r in rows if r['status'] == 'duplicate'),
        'internal_duplicate': sum(1 for r in rows if r['status'] == 'internal_duplicate'),
        'uncategorized': uncategorized,
    }
    return {'rows': rows, 'stats': stats}


def commit_import(task: ImportTask, account: Account, user,
                  indexes: list[int] = None, overrides: dict = None) -> dict:
    """确认导入：批量写入流水并同步账户余额（单事务）。

    indexes: 选中的预览行下标；为空表示导入全部「新增」记录
    overrides: {下标: category_id}，用户在预览页手工纠正的分类
    """
    rows = task.preview or []
    selected_indexes = set(indexes) if indexes else None
    chosen = [
        row for row in rows
        if row.get('status') == 'new'
        and (selected_indexes is None or row.get('i') in selected_indexes)
    ]
    # 幂等兜底：预览之后到确认之前可能已导入过（重复提交 / 并发），再过滤一次
    existing = _existing_hashes(task.family)
    if existing:
        chosen = [row for row in chosen
                  if not row.get('dedup_hash') or row['dedup_hash'] not in existing]
    if not chosen:
        return {'created': 0, 'skipped': len(rows), 'delta_cents': 0,
                'income_cents': 0, 'expense_cents': 0}

    valid_categories = set(Category.objects.values_list('id', flat=True))
    overrides = overrides or {}

    objs = []
    delta_cents = 0
    for row in chosen:
        category_id = overrides.get(str(row['i'])) or row.get('category')
        if category_id not in valid_categories:
            category_id = None
        tx_date = _to_datetime(row.get('date'))
        if tx_date is None:
            continue
        tx_type = row.get('type') or 'expense'
        amount_cents = int(row.get('amount_cents') or 0)
        if amount_cents <= 0:
            continue
        objs.append(Transaction(
            family=task.family,
            user=user,
            account=account,
            type=tx_type,
            amount_cents=amount_cents,
            category_id=category_id,
            merchant=(row.get('merchant') or '')[:100],
            description=(row.get('desc') or '')[:255],
            source=task.platform if task.platform in ('wechat', 'alipay') else 'manual',
            transaction_date=tx_date,
            dedup_hash=row.get('dedup_hash') or '',
        ))
        if account is not None and tx_type != 'transfer':
            delta_cents += amount_cents if tx_type == 'income' else -amount_cents

    with db_transaction.atomic():
        Transaction.objects.bulk_create(objs, batch_size=BATCH_SIZE)
        if account is not None and delta_cents:
            Account.objects.filter(pk=account.pk).update(
                balance_cents=F('balance_cents') + delta_cents)

    logger.info('导入完成 task=%s created=%s delta=%s', task.id, len(objs), delta_cents)
    return {
        'created': len(objs),
        'skipped': len(rows) - len(chosen),
        'delta_cents': delta_cents,
        'income_cents': sum(o.amount_cents for o in objs if o.type == 'income'),
        'expense_cents': sum(o.amount_cents for o in objs if o.type == 'expense'),
    }


def _existing_hashes(family, date_from=None, date_to=None) -> set:
    """该家庭已有流水的去重指纹（按时间范围收窄，账单通常跨度几个月）。"""
    queryset = Transaction.objects.filter(family=family).exclude(dedup_hash='')
    if date_from:
        queryset = queryset.filter(transaction_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(transaction_date__lte=date_to)
    return set(queryset.values_list('dedup_hash', flat=True))


def _to_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if timezone.is_naive(naive):
            return timezone.make_aware(naive)
        return naive
    return None
