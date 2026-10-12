# -*- coding: utf-8 -*-
"""不收费阶段：隐私额度按最高档 ¥5000 放开（原默认 ¥500）。

只把「从未自己调过」的默认档（恰好 50000 分）提上去，
用户自定义过的额度（如 ¥300 / ¥800）保持原样。
将来开启会员闸门想收回时，反向迁移即可。
"""

from django.db import migrations, models

OLD_DEFAULT = 50000      # ¥500
NEW_DEFAULT = 500000     # ¥5000


def upgrade_default_quota(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(privacy_limit_cents=OLD_DEFAULT).update(
        privacy_limit_cents=NEW_DEFAULT)


def downgrade_default_quota(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(privacy_limit_cents=NEW_DEFAULT).update(
        privacy_limit_cents=OLD_DEFAULT)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='privacy_limit_cents',
            field=models.BigIntegerField(default=500000, verbose_name='隐私额度(分)'),
        ),
        migrations.RunPython(upgrade_default_quota, downgrade_default_quota),
    ]
