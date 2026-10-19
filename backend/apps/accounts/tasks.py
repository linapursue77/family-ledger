# -*- coding: utf-8 -*-
"""django-q 异步/定时任务。

资产净值曲线的「月度快照」必须有东西去记，否则曲线永远是空的。
"""
import logging

from django.utils import timezone

from apps.accounts.models import Account, AccountSnapshot

logger = logging.getLogger(__name__)


def _prev_ym(ym: str) -> str:
    """上一个月，如 2026-01 → 2025-12。"""
    year, month = int(ym[:4]), int(ym[5:7])
    if month == 1:
        return f'{year - 1}-12'
    return f'{year}-{month - 1:02d}'


def snapshot_all_accounts():
    """记录所有账户当月余额快照，并同步「上月余额」基准。

    幂等（update_or_create），所以每天跑也没关系：
    当月那根柱子会跟着账户余额走，直到月底定格。

    ★ 同时刷新 Account.last_balance_cents：
      首页「较上月变化」与净值曲线都靠它当作上月末余额，
      而它原来只在建账户 / 手改余额时才写，永远不会按月滚动，
      导致上线越久、这个变化额越失真。
    """
    today = timezone.localdate()
    ym = today.strftime('%Y-%m')
    prev_ym = _prev_ym(ym)

    accounts = list(Account.objects.all())
    for account in accounts:
        AccountSnapshot.objects.update_or_create(
            account=account,
            ym=ym,
            defaults={
                'balance_cents': account.balance_cents,
                'principal_cents': account.principal_cents,
            },
        )

    # 用上月末快照作为「上月余额」；没有历史快照（新账户）就退回当前余额，
    # 这样变化额是 0，而不是被误算成「余额 − 0」的假增长。
    last_map = {
        str(s.account_id): int(s.balance_cents)
        for s in AccountSnapshot.objects.filter(ym=prev_ym)
    }
    updates = []
    for account in accounts:
        new_last = last_map.get(str(account.id), int(account.balance_cents))
        if int(account.last_balance_cents or 0) != new_last:
            account.last_balance_cents = new_last
            updates.append(account)
    if updates:
        Account.objects.bulk_update(updates, ['last_balance_cents'])

    logger.info('账户快照 %s：%d 个账户，回写上月基准 %d 个', ym, len(accounts), len(updates))
    return f'{ym}:{len(accounts)}'
