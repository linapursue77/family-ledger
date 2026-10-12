# -*- coding: utf-8 -*-
"""初始套餐：部署后会员中心就有东西可卖，价格后续在后台随意调。"""
from django.db import migrations

PLANS = [
    {
        'code': 'year',
        'name': 'VIP 年卡',
        'price_cents': 19900,
        'original_price_cents': 29900,
        'duration_days': 365,
        'is_recommend': True,
        'sort': 0,
        'perks': ['含全部 8 项 VIP 权益', '平均每天不到 6 毛钱', '到期前可续费'],
    },
    {
        'code': 'quarter',
        'name': 'VIP 季卡',
        'price_cents': 6900,
        'original_price_cents': 9900,
        'duration_days': 90,
        'is_recommend': False,
        'sort': 1,
        'perks': ['含全部 8 项 VIP 权益', '先试试合不合适'],
    },
]


def seed(apps, schema_editor):
    VipPlan = apps.get_model('membership', 'VipPlan')
    for item in PLANS:
        VipPlan.objects.update_or_create(code=item['code'], defaults=item)


def unseed(apps, schema_editor):
    VipPlan = apps.get_model('membership', 'VipPlan')
    VipPlan.objects.filter(code__in=[p['code'] for p in PLANS]).delete()


class Migration(migrations.Migration):

    dependencies = [('membership', '0001_initial')]

    operations = [migrations.RunPython(seed, unseed)]
