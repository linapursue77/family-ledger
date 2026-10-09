# -*- coding: utf-8 -*-
"""初始化系统预设分类（数据源唯一：domain.categories）。

用法：python manage.py seed_categories
"""
from django.core.management.base import BaseCommand

from apps.ledger.models import Category
from domain.categories import all_categories


class Command(BaseCommand):
    help = '初始化系统预设分类（支出 12 类 + 收入 5 类）'

    def handle(self, *args, **options):
        created, updated = 0, 0
        for sort, (kind, meta) in enumerate(all_categories()):
            obj, is_new = Category.objects.update_or_create(
                id=meta['id'],
                defaults={
                    'kind': kind,
                    'name': meta['name'],
                    'icon': meta['icon'],
                    'color': meta['color'],
                    'keywords': meta.get('keywords', []),
                    'is_system': True,
                    'sort': sort,
                },
            )
            created += int(is_new)
            updated += int(not is_new)

        self.stdout.write(self.style.SUCCESS(
            f'分类初始化完成：新增 {created} 个，更新 {updated} 个，共 {created + updated} 个'
        ))
