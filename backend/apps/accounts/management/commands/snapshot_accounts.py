# -*- coding: utf-8 -*-
"""记录账户月度余额快照，作为资产净值曲线的数据源。

用法：
    python manage.py snapshot_accounts              # 记录当月
    python manage.py snapshot_accounts --ym 2026-09 # 补录指定月份
"""
import calendar
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.accounts.models import Account, AccountSnapshot
from apps.accounts.tasks import snapshot_all_accounts
from apps.ledger.models import Transaction


def _month_end(ym: str) -> date:
    year, month = int(ym[:4]), int(ym[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


def _rebuild_balance(account, ym: str) -> int:
    """用「当前余额 − 该月之后的所有流水净额」倒推出该月末余额。

    补录历史月份时不能直接写当前余额：那样每个月柱子都一样高，曲线会变成一条直线。
    流水记账口径是「支出减、收入加」，所以 月末余额 = 当前余额 − 之后净额。
    """
    # 分类型求和，避免把支出也当正数加回去
    inc = Transaction.objects.filter(
        account=account, transaction_date__gt=_month_end(ym), type='income'
    ).aggregate(s=Sum('amount_cents'))['s'] or 0
    exp = Transaction.objects.filter(
        account=account, transaction_date__gt=_month_end(ym), type='expense'
    ).aggregate(s=Sum('amount_cents'))['s'] or 0
    return int(account.balance_cents) - int(inc) + int(exp)


class Command(BaseCommand):
    help = '记录账户月度余额快照（资产净值曲线数据源）'

    def add_arguments(self, parser):
        parser.add_argument('--ym', help='月份 YYYY-MM，默认当月')

    def handle(self, *args, **options):
        ym = options.get('ym')
        if ym:
            # 补录历史月份：按流水倒推该月末余额，而不是写当前余额
            accounts = list(Account.objects.all())
            for account in accounts:
                AccountSnapshot.objects.update_or_create(
                    account=account,
                    ym=ym,
                    defaults={'balance_cents': _rebuild_balance(account, ym)},
                )
            self.stdout.write(
                self.style.SUCCESS(f'已补录 {len(accounts)} 个账户 {ym} 的余额快照')
            )
            return
        # 当月：与定时任务共用同一段代码，避免两处逻辑走偏
        snapshot_all_accounts()
        self.stdout.write(
            self.style.SUCCESS(f'已记录 {Account.objects.count()} 个账户当月余额快照')
        )
