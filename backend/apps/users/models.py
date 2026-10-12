# -*- coding: utf-8 -*-
"""用户（PRD 6.2.1 users 表）。"""
from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.db import models


def _uuid():
    return uuid4().hex


class User(AbstractUser):
    """自定义用户。username 复用为手机号，便于 DRF 认证与 Admin 登录。"""

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    nickname = models.CharField('称呼', max_length=50, blank=True, default='')
    avatar_url = models.CharField('头像', max_length=255, blank=True, default='')
    phone = models.CharField('手机号', max_length=20, unique=True, null=True, blank=True)
    openid = models.CharField('微信OpenID', max_length=128, unique=True, null=True, blank=True)
    # 隐私空间月度额度（分），默认 ¥5000（不收费阶段按最高档放开，用户仍可自行调低）
    privacy_limit_cents = models.BigIntegerField('隐私额度(分)', default=500000)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'users'
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def __str__(self):
        return self.nickname or self.username

    @property
    def display_name(self) -> str:
        return self.nickname or self.username


class SmsCode(models.Model):
    """短信验证码。

    三条硬规则：
    1. 只存哈希不存明文——DB 泄漏也拿不到可用验证码；
    2. 一次性——用掉即作废，不能重放；
    3. 自带尝试次数——连续输错达到上限立刻失效，挡住暴力枚举。

    验证码放 DB 而不是 cache：开发/单机是 LocMemCache，多 worker 之间不共享，
    会出现「发了码但校验说没有」；DB 天然多进程一致，还留了审计记录。
    """

    SCENE_RESET = 'reset_password'   # 忘记密码 → 重置
    SCENE_BIND = 'bind_phone'        # 补绑手机号
    SCENE_CHOICES = [
        (SCENE_RESET, '重置密码'),
        (SCENE_BIND, '绑定手机号'),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    phone = models.CharField('手机号', max_length=20, db_index=True)
    scene = models.CharField('场景', max_length=20, choices=SCENE_CHOICES,
                             default=SCENE_RESET)
    code_hash = models.CharField('验证码哈希', max_length=128)
    expires_at = models.DateTimeField('过期时间', db_index=True)
    used_at = models.DateTimeField('使用时间', null=True, blank=True)
    try_count = models.PositiveSmallIntegerField('校验次数', default=0)
    ip = models.CharField('来源IP', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'sms_codes'
        verbose_name = '短信验证码'
        verbose_name_plural = '短信验证码'
        indexes = [
            models.Index(fields=['phone', 'scene', '-created_at']),
        ]

    def __str__(self):
        return f'{self.phone}/{self.scene}'

    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    def is_usable(self) -> bool:
        return not self.used_at and not self.is_expired()
