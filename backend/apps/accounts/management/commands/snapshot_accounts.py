# -*- coding: utf-8 -*-
"""记录账户月度余额快照，作为资产净值曲线的数据源。

用法：
    python manage.py snapshot_accounts              # 记录当月
    python manage.py snapshot_accounts --ym 2026-09 # 补录指定月份
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import Account, AccountSnapshot
from apps.accounts.tasks import snapshot_all_accounts


class Command(BaseCommand):
    help = '记录账户月度余额快照（资产净值曲线数据源）'

    def add_arguments(self, parser):
        parser.add_argument('--ym', help='月份 YYYY-MM，默认当月')

    def handle(self, *args, **options):
        ym = options.get('ym')
        if ym:
            # 补录历史月份，走自己的逻辑
            accounts = list(Account.objects.all())
            for account in accounts:
                AccountSnapshot.objects.update_or_create(
                    account=account,
                    ym=ym,
                    defaults={'balance_cents': account.balance_cents},
                )
        else:
            # 当月：与定时任务共用同一段代码，避免两处逻辑走偏
            result = snapshot_all_accounts()
            ym, accounts = result.split(':'), list(Account.objects.all())
        self.stdout.write(
            self.style.SUCCESS(f'已记录 {len(accounts)} 个账户 {ym if isinstance(ym, str) else ym[0]} 的余额快照')
        )
