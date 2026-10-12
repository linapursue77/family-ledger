# -*- coding: utf-8 -*-
"""会员体系：套餐、订阅、试用配置。

设计要点：
· 权益以 key 声明（BENEFITS），业务侧统一调 services.has_benefit(user, key) 判权，
  避免「是不是 VIP」的判断散落进各个接口，也方便日后按 key 单独放权益。
· 套餐价格、时长、卖点全部落在 VipPlan 里，管理员在后台就能调价，不用改代码。
· 试用天数等开关落在 VipConfig（单例表）里，同样后台可调。
"""
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _uuid():
    return uuid4().hex


# —— 权益清单：key / 名称 / 说明 / 是否 VIP 专属 ——
BENEFITS = [
    {'key': 'basic_book', 'name': '记账与账本管理', 'desc': '收支流水、分类、3 个账本、多账户', 'vip': False},
    {'key': 'basic_report', 'name': '基础报表', 'desc': '近 1 周 / 近 1 月 / 近 3 月收支概览', 'vip': False},
    {'key': 'basic_return', 'name': '收益总览', 'desc': '投资账户累计收益、收益率', 'vip': False},
    {'key': 'loans', 'name': '借钱来往', 'desc': '借出借入台账、部分还款与结清', 'vip': False},
    {'key': 'ai_insight', 'name': 'AI 财务分析', 'desc': 'AI 解读账单结构，给出可执行的省钱建议', 'vip': True},
    {'key': 'ai_config', 'name': '自定义 AI 模型', 'desc': '接入自己的 DeepSeek / OpenAI 密钥', 'vip': True},
    {'key': 'bulk_import', 'name': '账单批量导入', 'desc': '微信 / 支付宝 / CSV 账单一键导入', 'vip': True},
    {'key': 'full_report', 'name': '全周期报表', 'desc': '本月 / 今年 / 近一年 / 自定义区间，含年度对比', 'vip': True},
    {'key': 'return_pro', 'name': '收益管理进阶', 'desc': '一年收益变化、今年收益明细、按账本切换、资产盘点', 'vip': True},
    {'key': 'data_export', 'name': '数据导出', 'desc': '导出全部账单明细 CSV', 'vip': True},
    {'key': 'privacy_up', 'name': '私密额度提升', 'desc': '私密消费月额度 ¥500 → ¥5,000', 'vip': True},
    {'key': 'more_members', 'name': '家庭成员扩容', 'desc': '家庭人数上限 5 人 → 10 人', 'vip': True},
]

# VIP 专属权益的 key 集合：不在集合里的一律对所有人开放
VIP_ONLY = {b['key'] for b in BENEFITS if b['vip']}

# 两类用户的额度差异
FREE_MEMBER_LIMIT = 5
VIP_MEMBER_LIMIT = 10
FREE_PRIVACY_LIMIT_CENTS = 50000
VIP_PRIVACY_LIMIT_CENTS = 500000


class VipConfig(models.Model):
    """全局会员配置（单例，pk 固定为 1）：试用开关与天数，管理员可调。"""

    id = models.IntegerField(primary_key=True, default=1)
    trial_enabled = models.BooleanField('开放免费试用', default=True)
    trial_days = models.PositiveIntegerField('试用天数', default=3)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'vip_configs'
        verbose_name = '会员配置'
        verbose_name_plural = '会员配置'

    def __str__(self):
        return f'试用 {self.trial_days} 天' if self.trial_enabled else '未开放试用'

    @classmethod
    def get(cls) -> 'VipConfig':
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class VipPlan(models.Model):
    """会员套餐：价格 / 时长 / 卖点全部后台可改。"""

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    code = models.CharField('套餐编码', max_length=32, unique=True)
    name = models.CharField('套餐名称', max_length=50)
    price_cents = models.BigIntegerField('售价(分)', default=0)
    original_price_cents = models.BigIntegerField('原价(分)', default=0)
    duration_days = models.PositiveIntegerField('时长(天)', default=365)
    perks = models.JSONField('卖点', default=list, blank=True)
    is_active = models.BooleanField('在售', default=True)
    is_recommend = models.BooleanField('推荐', default=False)
    sort = models.IntegerField('排序', default=0)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'vip_plans'
        verbose_name = '会员套餐'
        verbose_name_plural = '会员套餐'
        ordering = ['sort', 'price_cents']

    def __str__(self):
        return f'{self.name} ¥{self.price_cents / 100:.0f}'


class VipSubscription(models.Model):
    """一条会员有效期记录。续费时另起一条，历史可追溯。"""

    SOURCE_PURCHASE = 'purchase'
    SOURCE_TRIAL = 'trial'
    SOURCE_ADMIN = 'admin'
    SOURCE_CHOICES = [(SOURCE_PURCHASE, '购买'), (SOURCE_TRIAL, '试用'),
                      (SOURCE_ADMIN, '管理员赠送')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='vip_subs', verbose_name='用户')
    plan = models.ForeignKey(VipPlan, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='subs', verbose_name='套餐')
    start_at = models.DateTimeField('生效时间')
    expire_at = models.DateTimeField('到期时间')
    source = models.CharField('来源', max_length=16, choices=SOURCE_CHOICES,
                              default=SOURCE_PURCHASE)
    order_no = models.CharField('订单号', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'vip_subscriptions'
        verbose_name = '会员订阅'
        verbose_name_plural = '会员订阅'
        ordering = ['-expire_at']

    def __str__(self):
        return f'{self.user_id} → {self.expire_at:%Y-%m-%d}'

    @property
    def is_active(self) -> bool:
        return self.expire_at > timezone.now()

    @property
    def remain_days(self) -> int:
        delta = self.expire_at - timezone.now()
        return max(delta.days + (1 if delta.seconds else 0), 0)


class VipOrder(models.Model):
    """会员支付订单：开通 / 续费都先落一条订单，微信回调成功后再开通会员。

    订单号自己生成（out_trade_no），回调按订单号回写状态，
    重复回调靠 status 幂等，不会重复加时长。
    """

    SCENE_JSAPI = 'jsapi'
    SCENE_H5 = 'h5'
    SCENE_MINI = 'mini'
    SCENE_CHOICES = [(SCENE_JSAPI, '微信内JSAPI'), (SCENE_H5, '微信H5'),
                     (SCENE_MINI, '小程序')]

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CLOSED = 'closed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_PENDING, '待支付'), (STATUS_PAID, '已支付'),
                      (STATUS_CLOSED, '已关闭'), (STATUS_FAILED, '下单失败')]

    id = models.CharField(primary_key=True, max_length=36, default=_uuid, editable=False)
    order_no = models.CharField('订单号', max_length=32, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='vip_orders', verbose_name='用户')
    plan = models.ForeignKey(VipPlan, on_delete=models.PROTECT,
                             related_name='orders', verbose_name='套餐')
    scene = models.CharField('支付场景', max_length=16, choices=SCENE_CHOICES,
                             default=SCENE_JSAPI)
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    amount = models.BigIntegerField('金额(分)', default=0)
    openid = models.CharField('支付OpenID', max_length=128, blank=True, default='')
    description = models.CharField('商品描述', max_length=127, blank=True, default='')
    prepay_id = models.CharField('预支付ID', max_length=64, blank=True, default='')
    transaction_id = models.CharField('微信订单号', max_length=64, blank=True,
                                      default='', db_index=True)
    h5_url = models.CharField('H5支付链接', max_length=512, blank=True, default='')
    paid_at = models.DateTimeField('支付时间', null=True, blank=True)
    expired_at = models.DateTimeField('订单失效时间', null=True, blank=True)
    notify_payload = models.JSONField('回调内容', default=dict, blank=True)
    errmsg = models.CharField('错误信息', max_length=255, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'vip_orders'
        verbose_name = '会员订单'
        verbose_name_plural = '会员订单'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_no} {self.get_status_display()}'

    @property
    def is_paid(self) -> bool:
        return self.status == self.STATUS_PAID

    @property
    def is_expired(self) -> bool:
        return self.status == self.STATUS_PENDING and bool(
            self.expired_at and self.expired_at <= timezone.now())
