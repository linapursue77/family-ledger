# -*- coding: utf-8 -*-
"""开发辅助：为首个主账号创建一个配偶(子账号)成员，便于联调隐私脱敏。

用法：python manage.py seed_demo_family
会创建/复用：13800138001 / test123456，权限为默认（show_private=False）
"""
from django.core.management.base import BaseCommand

from apps.families.models import DEFAULT_PERMISSIONS, Family, FamilyMember
from apps.users.models import User


class Command(BaseCommand):
    help = '为首个主账号创建配偶子账号，用于联调隐私与权限'

    def handle(self, *args, **options):
        owner = User.objects.filter(phone='13800138000').first()
        if not owner:
            self.stdout.write(self.style.WARNING('请先执行 scripts/smoke.py 创建主账号'))
            return

        family = Family.objects.filter(owner=owner).first()
        spouse, created = User.objects.get_or_create(
            username='13800138001',
            defaults={'phone': '13800138001', 'nickname': '老婆'},
        )
        if created:
            spouse.set_password('test123456')
            spouse.save()

        member, m_created = FamilyMember.objects.get_or_create(
            family=family,
            user=spouse,
            defaults={
                'role': FamilyMember.ROLE_MEMBER,
                'nickname': '老婆',
                'book_type': FamilyMember.BOOK_WIFE,
                'permissions': dict(DEFAULT_PERMISSIONS),
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'配偶账号就绪: 13800138001 / test123456 '
            f'(用户{"新建" if created else "已存在"}，成员{"新建" if m_created else "已存在"})'
        ))
        self.stdout.write(f'权限: {member.effective_permissions}')
