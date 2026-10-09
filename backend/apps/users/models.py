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
    # 隐私空间月度额度（分），默认 ¥500
    privacy_limit_cents = models.BigIntegerField('隐私额度(分)', default=50000)
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
