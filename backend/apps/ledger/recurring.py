# -*- coding: utf-8 -*-
"""周期记账（定时记账）的执行逻辑。

设计要点：
1. 幂等 —— 规则执行后立即把 next_run 推进到下一次，
   所以同一天重复跑（定时任务补跑、手动触发）不会生成重复流水。
2. 不补历史 —— 错过的周期直接跳过（只记错过笔数，next_run 顺到下一周期点）。
   房租、通勤这类固定收支补记到过去日期没有意义，反而会把当月收支统计冲高；
   真要补，用页面的「立即执行」。
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

# 一次运行最多补跑的笔数。正常每日任务只会到期 1 笔；
# 这是给「任务停了好几天（服务器宕机、qcluster 没起）」兜底的保护上限，
# 超出的部分直接跳过，不往统计里灌历史流水。
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
    # ★ 必须用 localdate()：定时任务排在本地 07:05，此时 UTC 还是前一天 23:05，
    #   用 now().date() 会拿到「昨天」，导致今天到期的规则被判定为未到期而永远跳过。
    today = today or timezone.localdate()
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

    # 到期的每一笔都补（正常每日任务只会有 1 笔）；超过 MAX_CATCHUP 的跳过不补。
    # ★ 推排期前必须判空：next_after(月末) 的下一次可能落在下个月，
    #   若该月没有对应日（如 day_of_month=30 遇到 2 月）→ next_run 会变 None，
    #   再进 <= 比较就抛 TypeError，整条规则从此再也跑不起来。改为停用兜底。
    skipped = 0
    exhausted = False
    while rule.next_run and rule.next_run <= today:
        nxt = rule.next_after(rule.next_run)
        if nxt is None:
            exhausted = True
            rule.is_active = False
            logger.warning('周期记账 rule=%s 无法推到下一次执行日，已自动停用', rule.id)
            break
        if len(created) >= MAX_CATCHUP:
            skipped += 1
        else:
            tx = _write_tx(rule, rule.next_run)
            created.append(tx.id)
            rule.run_count += 1
        rule.next_run = nxt
    rule.last_run_at = timezone.now()
    rule.last_error = ''
    fields = ['run_count', 'last_run_at', 'last_error', 'updated_at']
    if rule.next_run is None:
        # next_run 是 NOT NULL，不能存 None：保持原值并停用
        rule.is_active = False
        fields += ['is_active']
    else:
        fields.append('next_run')
    rule.save(update_fields=fields)
    if skipped:
        logger.warning('周期记账 rule=%s 错过周期过多，跳过 %d 笔未补', rule.id, skipped)
    return created


def run_due_rules(today=None):
    """扫全库到期规则。供定时任务与手动命令调用。

    返回 {'scanned': 扫描到的规则数, 'created': 生成流水数, 'failed': 失败规则数}
    """
    # ★ localdate()：见 execute_rule 里同名说明，用 now().date() 会因 UTC 偏差漏跑当天。
    today = today or timezone.localdate()
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
