# -*- coding: utf-8 -*-
"""周期记账（定时记账）的执行逻辑。

设计要点：
1. 幂等 —— 规则执行后立即把 next_run 推进到下一次，
   所以同一天重复跑（定时任务补跑、手动触发）不会生成重复流水。
2. 补跑有上限 —— 规则停用了很久再启用，最多补 MAX_CATCHUP 笔，
   避免一次性灌进几百笔历史流水把统计冲垮。
3. 单笔失败不影响其它规则 —— 失败只记录 last_error，规则保持启用。
"""
import logging
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from apps.ledger.models import RecurringRule, Transaction
from apps.ledger.services import apply_balance
from domain.dedup import dedup_hash

logger = logging.getLogger(__name__)

# 单次运行最多补跑的笔数（防止长期停用的规则一次性补出大量流水）
MAX_CATCHUP = 3


def rule_to_dict(rule):
    """给接口/两端页面用的展示结构（金额统一以「元」返回）。"""
    return {
        'id': rule.id,
        'name': rule.name,
        'type': rule.type,
        'amount': rule.amount_cents / 100,
        'amount_cents': rule.amount_cents,
        'account_id': rule.account_id or '',
        'account_name': rule.account.name if rule.account else '',
        'account_icon': rule.account.icon if rule.account else '',
        'category_id': rule.category_id or '',
        'category_name': rule.category.name if rule.category else '',
        'category_icon': rule.category.icon if rule.category else '',
        'category_color': rule.category.color if rule.category else '',
        'merchant': rule.merchant,
        'frequency': rule.frequency,
        'schedule_text': rule.schedule_text(),
        'interval': rule.interval,
        'weekday': rule.weekday,
        'day_of_month': rule.day_of_month,
        'start_date': rule.start_date.isoformat(),
        'end_date': rule.end_date.isoformat() if rule.end_date else '',
        'next_run': rule.next_run.isoformat(),
        'is_active': rule.is_active,
        'is_private': rule.is_private,
        'run_count': rule.run_count,
        'last_run_at': rule.last_run_at.isoformat() if rule.last_run_at else '',
        'last_error': rule.last_error,
        'created_at': rule.created_at.isoformat(),
    }


def _write_tx(rule, run_date, now=None):
    """按规则生成一笔流水并入账（联动账户余额）。"""
    tx_date = timezone.make_aware(datetime.combine(run_date, time(9, 0)))
    merchant = rule.merchant or rule.name
    tx = Transaction.objects.create(
        family=rule.family,
        user=rule.user,
        account=rule.account,
        type=rule.type,
        amount_cents=rule.amount_cents,
        category=rule.category,
        merchant=merchant,
        description=f'自动记账：{rule.name}',
        source=Transaction.SOURCE_MANUAL,
        is_private=bool(rule.is_private) and rule.type == Transaction.TYPE_EXPENSE,
        transaction_date=tx_date,
        dedup_hash=dedup_hash(tx_date, rule.amount_cents, merchant),
    )
    apply_balance(rule.account, rule.type, rule.amount_cents)
    return tx


def execute_rule(rule, force=False, today=None):
    """执行一条规则。

    force=False：只跑到期的（next_run <= today），正常定时任务走这条；
    force=True ：立即生成一笔（日期取今天），用于页面的「立即执行」。

    返回本次生成的流水 id 列表。
    """
    today = today or timezone.now().date()
    created = []

    if force:
        # ★ 立即执行：以今天补一笔，仅在 next_run 恰好是今天时才推进排期，
        #   否则会打乱原本的下次执行日。
        tx = _write_tx(rule, today)
        created.append(tx.id)
        rule.run_count += 1
        rule.last_run_at = timezone.now()
        rule.last_error = ''
        if rule.next_run == today:
            rule.next_run = rule.next_after(today)
        rule.save(update_fields=['next_run', 'run_count', 'last_run_at', 'last_error', 'updated_at'])
        return created

    if not rule.is_active or rule.next_run > today:
        return created
    if rule.end_date and today > rule.end_date:
        rule.is_active = False
        rule.save(update_fields=['is_active', 'updated_at'])
        return created

    # 补跑：逐条推进，最多 MAX_CATCHUP 笔，剩下的顺延到今天之后
    for _ in range(MAX_CATCHUP):
        if rule.next_run > today:
            break
        tx = _write_tx(rule, rule.next_run)
        created.append(tx.id)
        rule.run_count += 1
        rule.next_run = rule.next_after(rule.next_run)
    rule.last_run_at = timezone.now()
    rule.last_error = ''
    rule.save(update_fields=['next_run', 'run_count', 'last_run_at', 'last_error', 'updated_at'])
    return created


def run_due_rules(today=None):
    """扫全库到期规则。供定时任务与手动命令调用。

    返回 {'scanned': 扫描到的规则数, 'created': 生成流水数, 'failed': 失败规则数}
    """
    today = today or timezone.now().date()
    qs = RecurringRule.objects.filter(is_active=True, next_run__lte=today)
    stats = {'scanned': 0, 'created': 0, 'failed': []}
    for rule in qs:
        stats['scanned'] += 1
        try:
            with transaction.atomic():
                created = execute_rule(rule, today=today)
            stats['created'] += len(created)
        except Exception as exc:  # 单条失败不影响其它规则
            logger.exception('周期记账执行失败 rule=%s', rule.id)
            rule.last_error = str(exc)[:300]
            rule.save(update_fields=['last_error', 'updated_at'])
            stats['failed'].append({'id': rule.id, 'name': rule.name, 'error': str(exc)[:300]})
    return stats
