# -*- coding: utf-8 -*-
"""django-q 异步/定时任务。

资产净值曲线的「月度快照」必须有东西去记，否则曲线永远是空的。
"""
import logging

from django.utils import timezone

from apps.accounts.models import Account, AccountSnapshot

logger = logging.getLogger(__name__)


def snapshot_all_accounts():
    """记录所有账户当月余额快照。

    幂等（update_or_create），所以每天跑也没关系：
    当月那根柱子会跟着账户余额走，直到月底定格。
    """
    ym = timezone.localdate().strftime('%Y-%m')
    accounts = list(Account.objects.all())
    for account in accounts:
        AccountSnapshot.objects.update_or_create(
            account=account,
            ym=ym,
            defaults={'balance_cents': account.balance_cents},
        )
    logger.info('账户快照 %s：%d 个账户', ym, len(accounts))
    return f'{ym}:{len(accounts)}'
