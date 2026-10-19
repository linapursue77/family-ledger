# -*- coding: utf-8 -*-
"""注册 django-q 定时任务。

幂等，容器每次启动都会跑一遍，不会重复建。
任务真正被执行的条件是 qcluster 在跑（compose 里的 queue 服务）。
"""
from django.core.management.base import BaseCommand

from django_q.models import Schedule

# (任务名, 函数路径, 类型, 说明)
SCHEDULES = [
    (
        '每日账户余额快照',
        'apps.accounts.tasks.snapshot_all_accounts',
        Schedule.DAILY,
        '资产净值曲线的数据源；每天刷新当月快照，月底定格，并同步各账户的「上月余额」基准',
    ),
    (
        '每日周期记账',
        'apps.ledger.tasks.run_recurring_rules',
        Schedule.DAILY,
        '按时把启用的周期记账规则生成流水并入账（房租、通勤等固定收支）',
    ),
]


class Command(BaseCommand):
    help = '注册定时任务（幂等）'

    def handle(self, *args, **options):
        created = 0
        for name, func, stype, desc in SCHEDULES:
            _, ok = Schedule.objects.get_or_create(
                name=name,
                defaults={'func': func, 'schedule_type': stype, 'repeats': -1},
            )
            if ok:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  新建：{name} — {desc}'))
        self.stdout.write(
            self.style.SUCCESS(f'定时任务就绪（本次新建 {created} 个，共 {len(SCHEDULES)} 个）')
        )
