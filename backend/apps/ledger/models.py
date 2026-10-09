# -*- coding: utf-8 -*-
"""分类、交易流水、导入任务（PRD 6.2.3）。"""
from uuid import uuid4

from django.conf import settings
from django.db import models


def _uuid():
    return uuid4().hex


class Category(models.Model):
    KIND_EXPENSE = 'expense'
    KIND_INCOME = 'income'
    KIND_CHOICES = [(KIND_EXPENSE, '支出'), (KIND_INCOME, '收入')]

    id = models.CharField(primary_key=True, max_length=32)   # food / salary / ...
    kind = models.CharField('类型', max_length=16, choices=KIND_CHOICES)
    name = models.CharField('名称', max_length=20)
    icon = models.CharField('图标', max_length=16, default='💰')
    color = models.CharField('颜色', max_length=16, default='#8D6E63')
    keywords = models.JSONField('匹配关键词', default=list, blank=True)
    is_system = models.BooleanField('系统预设', default=True)
    sort = models.IntegerField('排序', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name = '分类'
        verbose_name_plural = '分类'
        ordering = ['kind', 'sort', 'id']

    def __str__(self):
        return f'{self.icon} {self.name}'


class Transaction(models.Model):
    TYPE_EXPENSE = 'expense'
    TYPE_INCOME = 'income'
    TYPE_TRANSFER = 'transfer'
    # 借贷流水：只反映资金进出，绝不计入收入/支出统计（由借钱来往模块同步生成，不可手动记）
    TYPE_LOAN_IN = 'loan_in'      # 流入：借入本金、收回借出
    TYPE_LOAN_OUT = 'loan_out'    # 流出：借出本金、归还借入
    TYPE_CHOICES = [
        (TYPE_EXPENSE, '支出'),
        (TYPE_INCOME, '收入'),
        (TYPE_TRANSFER, '转账'),
        (TYPE_LOAN_IN, '借入/回款'),
        (TYPE_LOAN_OUT, '借出/还款'),
    ]

    SOURCE_WECHAT = 'wechat'
    SOURCE_ALIPAY = 'alipay'
    SOURCE_MANUAL = 'manual'
    SOURCE_VOICE = 'voice'
    SOURCE_CHOICES = [(SOURCE_WECHAT, '微信账单'), (SOURCE_ALIPAY, '支付宝账单'),
                      (SOURCE_MANUAL, '手动记账'), (SOURCE_VOICE, '语音记账')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey('families.Family', on_delete=models.CASCADE,
                               related_name='transactions', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='transactions', verbose_name='记账人')
    account = models.ForeignKey('accounts.Account', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='transactions',
                                verbose_name='账户')
    type = models.CharField('类型', max_length=16, choices=TYPE_CHOICES, default=TYPE_EXPENSE)
    # 金额恒为正，方向由 type 决定；单位：分
    amount_cents = models.BigIntegerField('金额(分)')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True,
                                 blank=True, related_name='transactions', verbose_name='分类')
    merchant = models.CharField('商户', max_length=100, blank=True, default='')
    description = models.CharField('备注', max_length=255, blank=True, default='')
    source = models.CharField('来源', max_length=16, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    is_private = models.BooleanField('私密消费', default=False)
    is_hidden = models.BooleanField('对配偶隐藏详情', default=False)
    auto_public = models.BooleanField('超额自动公开', default=False)
    transaction_date = models.DateTimeField('交易时间', db_index=True)
    dedup_hash = models.CharField('去重指纹', max_length=32, blank=True, default='', db_index=True)
    # 借贷流水指回借款记录；用普通字段而非外键，避免跨应用级联与循环依赖
    loan_id = models.CharField('关联借款', max_length=36, blank=True, default='', db_index=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'transactions'
        verbose_name = '交易流水'
        verbose_name_plural = '交易流水'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['family', 'transaction_date'], name='idx_tx_family_date'),
            models.Index(fields=['family', 'category'], name='idx_tx_family_cat'),
            models.Index(fields=['family', 'dedup_hash'], name='idx_tx_family_dedup'),
        ]

    def __str__(self):
        return f'{self.get_type_display()} {self.amount_cents} {self.merchant}'


class AISettings(models.Model):
    """大模型分析配置（家庭级）。

    ★ 界面可改、存库、即时生效，无需改 .env 或重启后端；
      没有这条记录时，domain.ai 自动回落到 .env 的配置；
      .env 也没有 Key 时，报告页走本地规则引擎，功能不受影响。
    """
    family = models.OneToOneField('families.Family', on_delete=models.CASCADE,
                                  related_name='ai_settings', verbose_name='家庭')
    enabled = models.BooleanField('启用AI分析', default=False)
    provider = models.CharField('服务商', max_length=32, default='deepseek')
    base_url = models.CharField('接口地址', max_length=200, default='https://api.deepseek.com/v1')
    model = models.CharField('模型名', max_length=80, default='deepseek-chat')
    api_key = models.CharField('API Key', max_length=300, blank=True, default='')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'ai_settings'
        verbose_name = 'AI 分析配置'
        verbose_name_plural = 'AI 分析配置'

    def __str__(self):
        return f'{self.family_id} · {self.model} · {"on" if self.enabled else "off"}'


class ImportTask(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PREVIEW = 'preview'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_PENDING, '待解析'), (STATUS_PREVIEW, '待确认'),
                      (STATUS_DONE, '已完成'), (STATUS_FAILED, '失败')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey('families.Family', on_delete=models.CASCADE,
                               related_name='import_tasks', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='导入人')
    platform = models.CharField('平台', max_length=16, default='wechat')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_count = models.IntegerField('总记录', default=0)
    new_count = models.IntegerField('新增', default=0)
    duplicate_count = models.IntegerField('重复', default=0)
    failed_count = models.IntegerField('失败', default=0)
    preview = models.JSONField('预览数据', default=list, blank=True)
    error_message = models.CharField('错误信息', max_length=500, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'import_tasks'
        verbose_name = '账单导入任务'
        verbose_name_plural = '账单导入任务'
        ordering = ['-created_at']
