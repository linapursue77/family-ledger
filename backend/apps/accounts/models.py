# -*- coding: utf-8 -*-
"""账户、余额快照、余额调整（PRD 6.2.2）。"""
from uuid import uuid4

from django.conf import settings
from django.db import models


def _uuid():
    return uuid4().hex


class Account(models.Model):
    # ★ 复用作「可见性」：personal = 对方可见，private = 仅本人可见
    TYPE_JOINT = 'joint'
    TYPE_PERSONAL = 'personal'
    TYPE_PRIVATE = 'private'
    TYPE_CHOICES = [(TYPE_JOINT, '共同账户'), (TYPE_PERSONAL, '对方可见'), (TYPE_PRIVATE, '仅本人可见')]

    BOOK_HUSBAND = 'husband'
    BOOK_WIFE = 'wife'
    BOOK_SHARED = 'shared'
    BOOK_CHOICES = [(BOOK_HUSBAND, '老公账本'), (BOOK_WIFE, '老婆账本'), (BOOK_SHARED, '共同账本')]

    # 账户介质（前端「账户类型」四选一），与 type（可见性）拆开，语义互不干扰
    CARD_DEBIT = 'debit'
    CARD_CREDIT = 'credit'
    CARD_CASH = 'cash'
    CARD_WALLET = 'wallet'
    CARD_CHOICES = [(CARD_DEBIT, '储蓄卡'), (CARD_CREDIT, '信用卡'),
                    (CARD_CASH, '现金'), (CARD_WALLET, '数字钱包')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey('families.Family', on_delete=models.CASCADE,
                               related_name='accounts', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='accounts', verbose_name='所属用户')
    name = models.CharField('账户名称', max_length=50)
    icon = models.CharField('账户图标', max_length=16, default='💰')
    type = models.CharField('账户类型', max_length=16, choices=TYPE_CHOICES, default=TYPE_PERSONAL)
    book_type = models.CharField('所属账本', max_length=16, choices=BOOK_CHOICES,
                                 default=BOOK_HUSBAND)
    balance_cents = models.BigIntegerField('当前余额(分)', default=0)
    last_balance_cents = models.BigIntegerField('上月余额(分)', default=0)
    card_type = models.CharField('账户介质', max_length=16, choices=CARD_CHOICES,
                                default=CARD_DEBIT)
    bank_name = models.CharField('开户银行/平台', max_length=100, blank=True, default='')
    account_no = models.CharField('账号(脱敏)', max_length=50, blank=True, default='')
    is_count_total = models.BooleanField('计入总资产', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'accounts'
        verbose_name = '账户'
        verbose_name_plural = '账户'
        ordering = ['book_type', '-created_at']
        indexes = [
            models.Index(fields=['family', 'book_type'], name='idx_acc_family_book'),
            models.Index(fields=['family', 'user'], name='idx_acc_family_user'),
        ]

    def __str__(self):
        return f'{self.name}({self.bank_name or self.get_type_display()})'


class AccountSnapshot(models.Model):
    """每月余额快照：支撑「月变化」与「资产净值曲线」。"""

    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE,
                                related_name='snapshots', verbose_name='账户')
    ym = models.CharField('月份', max_length=7)   # 2026-09
    balance_cents = models.BigIntegerField('余额(分)', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'account_snapshots'
        verbose_name = '账户余额快照'
        verbose_name_plural = '账户余额快照'
        unique_together = ('account', 'ym')
        ordering = ['-ym']


class BalanceAdjustLog(models.Model):
    """余额手动调整审计记录（PRD 4.1.4 要求填写调整说明）。"""

    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE,
                                related_name='adjust_logs', verbose_name='账户')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 verbose_name='操作人')
    before_cents = models.BigIntegerField('调整前(分)', default=0)
    after_cents = models.BigIntegerField('调整后(分)', default=0)
    reason = models.CharField('调整说明', max_length=200)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'balance_adjust_logs'
        verbose_name = '余额调整记录'
        verbose_name_plural = '余额调整记录'
        ordering = ['-created_at']
