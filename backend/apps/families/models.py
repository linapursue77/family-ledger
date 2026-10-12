# -*- coding: utf-8 -*-
"""家庭、成员、权限、邀请、协商阈值（PRD 6.2.5 / 6.2.6 / 6.2.7）。"""
import secrets
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _uuid():
    return uuid4().hex


DEFAULT_PERMISSIONS = {
    'report_view': 'all',       # all | own
    'account_view': 'all',      # all | own
    'allow_record': True,
    'show_private': False,
    'settings_level': 'basic',  # full | basic
}


class Family(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    name = models.CharField('家庭名称', max_length=50, default='我的家庭')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='owned_families', verbose_name='主账号')
    # 账本自定义名称：{'shared': '共同账本', 'husband': '爸爸的账'}，缺省用内置默认名
    book_labels = models.JSONField('账本名称', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'families'
        verbose_name = '家庭'
        verbose_name_plural = '家庭'

    def __str__(self):
        return self.name


class FamilyMember(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [(ROLE_OWNER, '主账号'), (ROLE_MEMBER, '子账号')]

    BOOK_HUSBAND = 'husband'
    BOOK_WIFE = 'wife'
    BOOK_SHARED = 'shared'
    # 展示层默认名保持中性：不预设成员关系，家庭可在「账本名称」里改成任意叫法
    BOOK_CHOICES = [(BOOK_HUSBAND, '账本一'), (BOOK_WIFE, '账本二'), (BOOK_SHARED, '共同账本')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey(Family, on_delete=models.CASCADE,
                               related_name='members', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='family_members', verbose_name='用户')
    role = models.CharField('角色', max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    nickname = models.CharField('家庭内称呼', max_length=50, blank=True, default='')
    book_type = models.CharField('所属账本', max_length=16, choices=BOOK_CHOICES,
                                 default=BOOK_HUSBAND)
    permissions = models.JSONField('权限配置', default=dict, blank=True)
    joined_at = models.DateTimeField('加入时间', auto_now_add=True)

    class Meta:
        db_table = 'family_members'
        verbose_name = '家庭成员'
        verbose_name_plural = '家庭成员'
        unique_together = ('family', 'user')

    def __str__(self):
        return f'{self.family.name} - {self.nickname or self.user_id}'

    @property
    def effective_permissions(self) -> dict:
        """主账号永远拥有全部权限；子账号以 JSON 配置为准（缺省补默认值）。"""
        if self.role == self.ROLE_OWNER:
            return {
                'report_view': 'all',
                'account_view': 'all',
                'allow_record': True,
                'show_private': True,
                'settings_level': 'full',
            }
        merged = dict(DEFAULT_PERMISSIONS)
        merged.update(self.permissions or {})
        return merged


class Invitation(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_EXPIRED = 'expired'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [(STATUS_PENDING, '待接受'), (STATUS_ACCEPTED, '已接受'),
                      (STATUS_EXPIRED, '已过期'), (STATUS_REVOKED, '已撤销')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey(Family, on_delete=models.CASCADE,
                               related_name='invitations', verbose_name='家庭')
    token_hash = models.CharField('邀请令牌哈希', max_length=64, unique=True)
    nickname = models.CharField('成员称呼', max_length=50, blank=True, default='')
    contact = models.CharField('联系方式', max_length=64, blank=True, default='')
    permissions = models.JSONField('预设权限', default=dict, blank=True)
    expires_at = models.DateTimeField('过期时间')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_PENDING)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'invitations'
        verbose_name = '邀请'
        verbose_name_plural = '邀请'

    @classmethod
    def issue(cls, family, nickname='', contact='', permissions=None, days=7):
        """签发邀请：明文 token 只在此刻返回一次，库里只存哈希。"""
        token = secrets.token_urlsafe(24)
        return cls.objects.create(
            family=family,
            token_hash=token,  # MVP 阶段简化存储，接入短信校验前改为哈希
            nickname=nickname,
            contact=contact,
            permissions=permissions or dict(DEFAULT_PERMISSIONS),
            expires_at=timezone.now() + timezone.timedelta(days=days),
        ), token

    @property
    def is_valid(self) -> bool:
        return self.status == self.STATUS_PENDING and self.expires_at > timezone.now()


class Threshold(models.Model):
    """协商阈值（PRD 4.5.2），金额单位为分。"""

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.OneToOneField(Family, on_delete=models.CASCADE,
                                  related_name='threshold', verbose_name='家庭')
    small_limit_cents = models.BigIntegerField('小额自主上限(分)', default=50000)
    notify_limit_cents = models.BigIntegerField('事后知会上限(分)', default=200000)
    approve_limit_cents = models.BigIntegerField('事前申请上限(分)', default=500000)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'thresholds'
        verbose_name = '协商阈值'
        verbose_name_plural = '协商阈值'

    def to_dict(self) -> dict:
        return {
            'small_limit': self.small_limit_cents,
            'notify_limit': self.notify_limit_cents,
            'approve_limit': self.approve_limit_cents,
        }
