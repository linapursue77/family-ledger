# -*- coding: utf-8 -*-
"""把某个已注册账号提升为管理员（is_staff），可撤销。

用法：
    python manage.py make_admin 13800138000          # 提升
    python manage.py make_admin 13800138000 --revoke # 撤销

管理后台（/#/console）只认 is_staff，与家庭里的主账号 / 子账号无关。
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = '把已注册账号设为 / 取消管理后台权限（is_staff）'

    def add_arguments(self, parser):
        parser.add_argument('phone', help='手机号（或 username）')
        parser.add_argument('--revoke', action='store_true', help='撤销管理员权限')

    def handle(self, *args, **options):
        key = options['phone']
        user = User.objects.filter(phone=key).first() or User.objects.filter(username=key).first()
        if user is None:
            raise CommandError(f'找不到账号：{key}')

        target = not options['revoke']
        if user.is_staff == target:
            state = '已经是管理员' if target else '本来就不是管理员'
            self.stdout.write(self.style.WARNING(f'{key} {state}，无需改动'))
            return

        user.is_staff = target
        user.save(update_fields=['is_staff'])
        if target:
            self.stdout.write(self.style.SUCCESS(
                f'✓ {user.display_name}（{key}）已成为管理员，登录后从「我的 → 管理后台」进入'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ 已撤销 {user.display_name}（{key}）的管理员权限'))
