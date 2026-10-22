# -*- coding: utf-8 -*-
"""分类、交易流水、导入任务（PRD 6.2.3）。"""
from datetime import date, timedelta
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone

# next_after 的推进上限（周期数）。只是防死循环的护栏，
# 正常间隔（1~99）下几十次就够，不会影响真实排期。
MAX_PERIOD_STEPS = 1000


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


class RecurringRule(models.Model):
    """周期记账规则（定时记账）。

    到点由定时任务按规则自动生成一笔流水并入账（联动账户余额），
    成员不必每月手动记房租、每周期记通勤这类固定收支。

    ★ next_run 是「下一次该执行的日期」，执行后即推进，
      所以同一个规则在同一天重复跑不会产生重复流水。
    """

    FREQ_DAILY = 'daily'
    FREQ_WEEKLY = 'weekly'
    FREQ_MONTHLY = 'monthly'
    FREQ_CHOICES = [(FREQ_DAILY, '每天'), (FREQ_WEEKLY, '每周'), (FREQ_MONTHLY, '每月')]

    TYPE_CHOICES = [(Transaction.TYPE_EXPENSE, '支出'), (Transaction.TYPE_INCOME, '收入')]

    # 月末兜底：规则里 day_of_month=31 遇到小月时落到该月最后一天
    MONTH_END = 31

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    family = models.ForeignKey('families.Family', on_delete=models.CASCADE,
                               related_name='recurring_rules', verbose_name='家庭')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='recurring_rules', verbose_name='记账人')
    name = models.CharField('规则名称', max_length=50)
    type = models.CharField('类型', max_length=16, choices=TYPE_CHOICES,
                            default=Transaction.TYPE_EXPENSE)
    amount_cents = models.BigIntegerField('金额(分)')
    account = models.ForeignKey('accounts.Account', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='recurring_rules',
                                verbose_name='账户')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='recurring_rules', verbose_name='分类')
    merchant = models.CharField('商户/备注', max_length=100, blank=True, default='')

    frequency = models.CharField('频率', max_length=16, choices=FREQ_CHOICES, default=FREQ_MONTHLY)
    interval = models.IntegerField('间隔', default=1)          # 每 N 天/周/月
    weekday = models.IntegerField('周几', null=True, blank=True)   # 0=周一 … 6=周日（每周）
    day_of_month = models.IntegerField('每月几号', null=True, blank=True)  # 1-31（每月）

    start_date = models.DateField('开始日期')
    end_date = models.DateField('结束日期', null=True, blank=True)
    next_run = models.DateField('下次执行', db_index=True)
    is_active = models.BooleanField('启用', default=True)
    is_private = models.BooleanField('私密消费', default=False)

    run_count = models.IntegerField('已生成笔数', default=0)
    last_run_at = models.DateTimeField('上次执行时间', null=True, blank=True)
    last_error = models.CharField('上次错误', max_length=300, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'recurring_rules'
        verbose_name = '周期记账规则'
        verbose_name_plural = '周期记账规则'
        ordering = ['is_active', 'next_run', '-created_at']
        indexes = [
            models.Index(fields=['family', 'is_active'], name='idx_rec_family_active'),
            models.Index(fields=['is_active', 'next_run'], name='idx_rec_due'),
        ]

    def __str__(self):
        return f'{self.name} · {self.get_frequency_display()} · ¥{self.amount_cents / 100:.2f}'

    # ------------------------------------------------------------------ 排期
    def schedule_text(self):
        """人话描述频率，如「每月 5 日」「每周 一」「每 2 天」。

        ★ 每月规则的「几号」优先取 day_of_month；没填时用开始日期的日号兜底，
          与实际排期（next_after 同样兜底成 1 号）保持一致，避免展示和真实执行日不符。
        """
        if self.frequency == self.FREQ_DAILY:
            return '每天' if self.interval <= 1 else f'每 {self.interval} 天'
        if self.frequency == self.FREQ_WEEKLY:
            names = ['一', '二', '三', '四', '五', '六', '日']
            wd = names[self.weekday] if self.weekday is not None else '一'
            return f'每周 {wd}' if self.interval <= 1 else f'每 {self.interval} 周 周{wd}'
        day = self.day_of_month or 1
        day_text = f'{day} 日' if day != self.MONTH_END else '月末'
        return f'每月 {day_text}' if self.interval <= 1 else f'每 {self.interval} 月 {day_text}'

    def enable(self, today=None):
        """重新启用规则。

        ★ 停用期间 next_run 会停在过去（谁也不会去推它），直接置 is_active=True
          的话规则依然「看起来是开着的，但永远等不到下一次执行」。
          所以启用时把早于今天的排期顺到下一个周期点。
          返回是否有改动，供调用方决定要不要落库。
        """
        today = today or timezone.now().date()
        changed = False
        if not self.is_active:
            self.is_active = True
            changed = True
        if self.next_run < today:
            nxt = self.next_after(today)
            if nxt:
                self.next_run = nxt
            changed = True
        return changed

    def _monthly_date(self, year, month):
        """按月生成日期；day_of_month=31 视为月末，小月自动落到最后一天。"""
        import calendar
        day = self.day_of_month or 1
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(day, last))

    def next_after(self, base):
        """算出 base 之后（严格 > base）的下一次执行日期。

        间隔 > 1 时统一以 start_date 为基准网格推进，避免逐次累加导致漂移。
        推不出来时返回 None（调用方必须判空，不要直接拿去比较）。
        """
        interval = max(int(self.interval or 1), 1)
        start = self.start_date

        if self.frequency == self.FREQ_DAILY:
            return base + timedelta(days=interval)

        if self.frequency == self.FREQ_WEEKLY:
            target = self.weekday if self.weekday is not None else 0
            if interval == 1:
                delta = (target - base.weekday()) % 7
                return base + timedelta(days=delta or 7)
            k = (base - start).days // (7 * interval) + 1
            for _ in range(MAX_PERIOD_STEPS):
                anchor = start + timedelta(weeks=k * interval)
                candidate = anchor + timedelta(days=(target - anchor.weekday()) % 7)
                if candidate > base:
                    return candidate
                k += 1
            return None

        # 每月
        if interval == 1:
            candidate = self._monthly_date(base.year, base.month)
            if candidate > base:
                return candidate
            month, year = base.month + 1, base.year
            if month > 12:
                month, year = 1, year + 1
            return self._monthly_date(year, month)
        k = ((base.year - start.year) * 12 + (base.month - start.month)) // interval + 1
        for _ in range(MAX_PERIOD_STEPS):
            total = (start.month - 1) + k * interval
            candidate = self._monthly_date(start.year + total // 12, total % 12 + 1)
            if candidate > base:
                return candidate
            k += 1
        return None

    def is_expired(self, today=None):
        return bool(self.end_date) and (today or timezone.now().date()) > self.end_date


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
