# -*- coding: utf-8 -*-
"""借钱来往：借出 / 借入 + 还款台账。

一笔借款只有一个方向：
    lend    借出 —— 钱从我出去，对方欠我
    borrow  借入 —— 钱进我账户，我欠对方
金额恒为正数，方向只由 direction 决定；对余额的影响集中在 balance_delta_cents 一处算，
避免正负号散落在视图和统计里翻车。还款沿同一方向冲减：借出收回是进账，借入归还是出账。
"""
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _uuid():
    return uuid4().hex


class Loan(models.Model):
    DIRECTION_LEND = 'lend'
    DIRECTION_BORROW = 'borrow'
    DIRECTION_CHOICES = [(DIRECTION_LEND, '借出'), (DIRECTION_BORROW, '借入')]

    STATUS_PENDING = 'pending'
    STATUS_PARTIAL = 'partial'
    STATUS_SETTLED = 'settled'
    STATUS_LABELS = {STATUS_PENDING: '未还', STATUS_PARTIAL: '部分还', STATUS_SETTLED: '已还清'}

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey('families.Family', on_delete=models.CASCADE,
                               related_name='loans', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='loans', verbose_name='经办人')
    # 关联账户可空：现金或没建账的渠道也能记台账，只是不动余额
    account = models.ForeignKey('accounts.Account', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='loans',
                                verbose_name='关联账户')
    direction = models.CharField('方向', max_length=8, choices=DIRECTION_CHOICES,
                                 default=DIRECTION_LEND)
    party = models.CharField('对方', max_length=50)
    amount_cents = models.BigIntegerField('金额(分)')
    loan_date = models.DateField('发生日期', default=timezone.localdate, db_index=True)
    due_date = models.DateField('约定还款日', null=True, blank=True)
    note = models.CharField('备注', max_length=255, blank=True, default='')
    # 指向同步生成的流水，删除时可精确定位；不用外键，避免跨应用级联
    tx_id = models.CharField('关联流水', max_length=36, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'loans'
        verbose_name = '借款'
        verbose_name_plural = '借钱来往'
        ordering = ['-loan_date', '-created_at']
        indexes = [
            models.Index(fields=['family', 'direction'], name='idx_loan_fam_dir'),
            models.Index(fields=['family', 'due_date'], name='idx_loan_fam_due'),
        ]

    def __str__(self):
        return f'{self.get_direction_display()} {self.party} {self.amount_cents / 100:.2f}'

    @property
    def balance_delta_cents(self) -> int:
        """这笔借款对关联账户余额的初始影响。"""
        return -int(self.amount_cents) if self.direction == self.DIRECTION_LEND else int(self.amount_cents)

    def repayment_delta_cents(self, amount_cents) -> int:
        """还款对余额的影响：借出收回进账，借入归还是出账。"""
        sign = 1 if self.direction == self.DIRECTION_LEND else -1
        return sign * int(amount_cents)


class LoanRepayment(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE,
                             related_name='repayments', verbose_name='所属借款')
    account = models.ForeignKey('accounts.Account', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='loan_repayments',
                                verbose_name='收付账户')
    amount_cents = models.BigIntegerField('金额(分)')
    repay_date = models.DateField('还款日期', default=timezone.localdate, db_index=True)
    note = models.CharField('备注', max_length=255, blank=True, default='')
    tx_id = models.CharField('关联流水', max_length=36, blank=True, default='')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 verbose_name='记录人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'loan_repayments'
        verbose_name = '还款记录'
        verbose_name_plural = '还款记录'
        ordering = ['-repay_date', '-created_at']

    def __str__(self):
        return f'{self.loan_id} 还 {self.amount_cents / 100:.2f}'
