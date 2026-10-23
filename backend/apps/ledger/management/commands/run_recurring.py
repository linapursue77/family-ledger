# -*- coding: utf-8 -*-
"""手动跑一次到期周期记账：python manage.py run_recurring [--dry-run] [--force ID]

定时任务由 django-q 的 qcluster 驱动；本地开发或没起队列时用这条命令补跑。
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ledger.models import RecurringRule
from apps.ledger.recurring import execute_rule, run_due_rules


class Command(BaseCommand):
    help = '执行到期的周期记账规则'

    def add_arguments(self, parser):
        parser.add_argument('--force', help='强制执行指定规则（立即记一笔，不论是否到期）')
        parser.add_argument('--dry-run', action='store_true', help='只列出将执行的规则，不落库')

    def handle(self, *args, **options):
        rule_id = options.get('force')
        if rule_id:
            rule = RecurringRule.objects.filter(id=rule_id).first()
            if rule is None:
                self.stdout.write(self.style.ERROR(f'规则不存在：{rule_id}'))
                return
            if options['dry_run']:
                self.stdout.write(f'将立即记账：{rule.name}（{rule.schedule_text()}）')
                return
            created = execute_rule(rule, force=True)
            self.stdout.write(self.style.SUCCESS(f'已生成 {len(created)} 笔：{rule.name}'))
            return

        if options['dry_run']:
            rules = RecurringRule.objects.filter(is_active=True, next_run__lte=timezone.localdate())
            for r in rules:
                self.stdout.write(f'待执行：{r.name} · {r.schedule_text()} · ¥{r.amount_cents / 100:.2f} · {r.next_run}')
            self.stdout.write(f'共 {len(rules)} 条')
            return

        stats = run_due_rules()
        self.stdout.write(self.style.SUCCESS(
            f"扫描 {stats['scanned']} 条，生成 {stats['created']} 笔"))
        for f in stats['failed']:
            self.stdout.write(self.style.ERROR(f"失败：{f['name']} — {f['error']}"))
