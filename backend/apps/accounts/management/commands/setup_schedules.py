# -*- coding: utf-8 -*-
"""注册 django-q 定时任务。

幂等：容器每次启动都会跑一遍，不会重复建，也不会覆盖已有排期。
任务真正被执行的条件是 qcluster 在跑（compose 里的 queue 服务）。

★ 两个坑（这就是「定时任务看着注册了却一直不执行」的根因）：
  1. Schedule.next_run 建的时候如果不给，默认是 timezone.now()（UTC），
     而 django-q 的调度器比较的是 localtime()，必须显式给一个本地时间。
  2. 已存在的 Schedule 绝不能只 get_or_create 就完事——旧逻辑里 next_run
     一直停在建库那一刻，再叠加 catch_up 的推进方式，排期会一天一天往前挪，
     永远追不上当前时间。现在每次启动都会检查并自愈。
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

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

# 每天这个点跑（本地时区）。上午跑，用户白天打开 App 时当月快照已经是新的。
RUN_AT = (7, 5)


def _next_local_run(now=None):
    """下一个本地时间 07:05（已过则顺延到明天），返回带时区的本地时间。"""
    now = now or timezone.localtime()
    target = now.replace(hour=RUN_AT[0], minute=RUN_AT[1], second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class Command(BaseCommand):
    help = '注册定时任务（幂等，且会自愈错误的排期）'

    def handle(self, *args, **options):
        now = timezone.localtime()
        created = 0
        fixed = 0
        for name, func, stype, desc in SCHEDULES:
            obj, ok = Schedule.objects.get_or_create(
                name=name,
                defaults={
                    'func': func,
                    'schedule_type': stype,
                    'repeats': -1,
                    'next_run': _next_local_run(now),
                },
            )
            # get_or_create 给的 defaults 不会写进已存在的记录，下面统一校正
            dirty = []
            if obj.func != func:
                obj.func = func
                dirty.append('func')
            if obj.schedule_type != stype:
                obj.schedule_type = stype
                dirty.append('schedule_type')
            if obj.repeats == 0:
                obj.repeats = -1
                dirty.append('repeats')
            # next_run 不合法时重排到下一个执行点，判据有三条：
            #   1. 为空
            #   2. 本地时分与 RUN_AT 不符（曾被手动拨动 / 旧版本按建库时刻写入）
            #   3. 已经过去（说明今天这一次没跑成）
            # 都在「未来且时分正确」时不改动，保证幂等，不会每次启动都往后推。
            nxt_ok = False
            if obj.next_run:
                lt = timezone.localtime(obj.next_run)
                nxt_ok = (lt.hour, lt.minute) == RUN_AT and lt > now - timedelta(minutes=5)
            if not nxt_ok:
                obj.next_run = _next_local_run(now)
                dirty.append('next_run')
            if dirty:
                obj.save(update_fields=dirty)
                fixed += 1

            if ok:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  新建：{name} — {desc}'))
            elif dirty:
                self.stdout.write(self.style.WARNING(f'  修正排期：{name} → {timezone.localtime(obj.next_run)}'))

        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING('当前是 DEBUG 模式：定时任务只有在运行 qcluster 时才会触发，'
                                   '本地开发请另开一个终端跑 python manage.py qcluster')
            )
        self.stdout.write(
            self.style.SUCCESS(
                f'定时任务就绪（新建 {created} 个，修正 {fixed} 个，共 {len(SCHEDULES)} 个）')
        )
