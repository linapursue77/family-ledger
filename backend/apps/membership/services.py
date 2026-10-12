# -*- coding: utf-8 -*-
"""会员判权：所有「VIP 才能用」的判断都走这里，禁止在业务接口里另写一套。"""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.response import BusinessError
from apps.membership.models import (
    FREE_MEMBER_LIMIT,
    FREE_PRIVACY_LIMIT_CENTS,
    VIP_MEMBER_LIMIT,
    VIP_ONLY,
    VIP_PRIVACY_LIMIT_CENTS,
    VipConfig,
    VipOrder,
    VipPlan,
    VipSubscription,
)

logger = logging.getLogger('django.request')


def active_subscription(user):
    """当前生效的订阅（取到期最晚的那条）。"""
    if not user or not getattr(user, 'id', None):
        return None
    return (VipSubscription.objects
            .filter(user_id=user.id, expire_at__gt=timezone.now())
            .order_by('-expire_at')
            .first())


def is_vip(user) -> bool:
    """含试用期——试用期内等同 VIP，权益全部开放。"""
    return active_subscription(user) is not None


def has_benefit(user, key: str) -> bool:
    """权益判权：非 VIP 专属权益人人可用，VIP 专属的看会员状态。

    settings.VIP_GATED=False 时（当前）付费权益一律放行——先用起来攒粘性，
    要收费时把开关打开即可，调用方不用改。
    """
    if key not in VIP_ONLY:
        return True
    if not settings.VIP_GATED:
        return True
    return is_vip(user)


def member_limit(user) -> int:
    """家庭成员上限：关闸时按 VIP 档放行。"""
    if not settings.VIP_GATED:
        return VIP_MEMBER_LIMIT
    return VIP_MEMBER_LIMIT if is_vip(user) else FREE_MEMBER_LIMIT


def privacy_limit_cents(user) -> int:
    """隐私月度额度：关闸时按 VIP 档放行。"""
    if not settings.VIP_GATED:
        return VIP_PRIVACY_LIMIT_CENTS
    return VIP_PRIVACY_LIMIT_CENTS if is_vip(user) else FREE_PRIVACY_LIMIT_CENTS


def trial_used(user) -> bool:
    """试用每人限一次：历史上领过就算用过（哪怕已过期）。"""
    if not user or not getattr(user, 'id', None):
        return False
    return VipSubscription.objects.filter(user_id=user.id,
                                          source=VipSubscription.SOURCE_TRIAL).exists()


def grant(user, days: int, plan=None, source=VipSubscription.SOURCE_ADMIN, order_no=''):
    """开通/续期：已有有效期就在其后顺延，避免续费反而缩短。"""
    now = timezone.now()
    current = active_subscription(user)
    start = max(current.expire_at, now) if current else now
    return VipSubscription.objects.create(
        user=user,
        plan=plan,
        start_at=start if current else now,
        expire_at=start + timezone.timedelta(days=days),
        source=source,
        order_no=order_no,
    )


def describe(user) -> dict:
    """我的会员状态：给前端卡片用。"""
    sub = active_subscription(user)
    cfg = VipConfig.get()
    data = {
        'is_vip': sub is not None,
        'expire_at': sub.expire_at.isoformat() if sub else None,
        'remain_days': sub.remain_days if sub else 0,
        'source': sub.get_source_display() if sub else '',
        'is_trial': bool(sub and sub.source == VipSubscription.SOURCE_TRIAL),
        'plan_name': sub.plan.name if sub and sub.plan else '',
        'trial_enabled': cfg.trial_enabled,
        'trial_days': cfg.trial_days,
        'trial_used': trial_used(user),
        'can_trial': cfg.trial_enabled and not trial_used(user) and sub is None,
        'member_limit': member_limit(user),
        'privacy_limit': privacy_limit_cents(user) / 100,
    }
    return data


# ---------------------------------------------------------------- 微信支付订单
def _new_order_no() -> str:
    """商户订单号：VIP + 时间戳 + 随机位，保证唯一。"""
    return f'VIP{timezone.now():%Y%m%d%H%M%S}{uuid.uuid4().hex[:8].upper()}'


def order_view(order: VipOrder) -> dict:
    """订单对前端的视图。"""
    return {
        'order_no': order.order_no,
        'plan_id': order.plan_id,
        'plan_name': order.plan.name,
        'amount': order.amount,
        'amount_yuan': order.amount / 100,
        'status': order.status,
        'scene': order.scene,
        'created_at': order.created_at.isoformat(),
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
    }


def _write_off(order: VipOrder, status: str, **fields) -> None:
    fields.update({'status': status})
    VipOrder.objects.filter(pk=order.pk).update(**fields)


def create_vip_order(user, plan: VipPlan, scene: str = VipOrder.SCENE_H5,
                     client_ip: str = '') -> VipOrder:
    """创建会员订单并向微信下单，返回带 prepay_id / h5_url 的订单。"""
    from apps.membership import pay

    if plan.price_cents <= 0:
        raise BusinessError('套餐价格未配置，暂不可购买')
    if plan.duration_days <= 0:
        raise BusinessError('套餐时长未配置')

    openid = '' if scene == VipOrder.SCENE_H5 else (user.openid or '')
    order = VipOrder.objects.create(
        order_no=_new_order_no(),
        user=user,
        plan=plan,
        scene=scene,
        amount=int(plan.price_cents),
        openid=openid,
        description=f'钱来钱往记账-{plan.name}'[:127],
        expired_at=timezone.now() + timedelta(seconds=settings.WXPAY_ORDER_TTL),
    )
    try:
        if scene == VipOrder.SCENE_H5:
            order.h5_url = pay.h5_prepay(order.order_no, order.description,
                                         order.amount, client_ip)
        else:
            order.prepay_id = pay.jsapi_prepay(order.order_no, order.description,
                                               order.amount, openid, scene)
    except Exception as exc:
        # 下单失败留痕，方便在后台看是配置问题还是参数问题
        _write_off(order, VipOrder.STATUS_FAILED, errmsg=str(exc)[:255])
        raise
    order.save(update_fields=['h5_url', 'prepay_id', 'updated_at'])
    return order


def pay_params(order: VipOrder) -> dict:
    """前端调起支付所需的参数：H5 场景给跳转链接，JSAPI / 小程序给签名参数。"""
    from apps.membership import pay

    if order.scene == VipOrder.SCENE_H5:
        return {'mweb_url': order.h5_url}
    return pay.build_pay_params(order.prepay_id, order.scene)


def settle_order(order: VipOrder, transaction_id: str = '', payload: dict | None = None) -> bool:
    """支付成功 → 开通 / 续期会员。行锁 + 状态判断保证重复回调只生效一次。"""
    with transaction.atomic():
        locked = VipOrder.objects.select_for_update().get(pk=order.pk)
        if locked.status == VipOrder.STATUS_PAID:
            return False
        if locked.status != VipOrder.STATUS_PENDING:
            logger.warning('订单状态不是待支付，跳过发货 order_no=%s status=%s',
                           locked.order_no, locked.status)
            return False
        locked.status = VipOrder.STATUS_PAID
        locked.transaction_id = transaction_id
        locked.paid_at = timezone.now()
        locked.notify_payload = payload or {}
        locked.save(update_fields=['status', 'transaction_id', 'paid_at',
                                   'notify_payload', 'updated_at'])
        grant(locked.user, days=locked.plan.duration_days, plan=locked.plan,
              source=VipSubscription.SOURCE_PURCHASE, order_no=locked.order_no)
    return True


def settle_notify(resource: dict) -> bool:
    """处理微信回调：校验订单与金额后发货。"""
    out_trade_no = resource.get('out_trade_no')
    if not out_trade_no:
        logger.warning('微信回调缺少 out_trade_no')
        return False
    if resource.get('trade_state') != 'SUCCESS':
        return False

    order = VipOrder.objects.filter(order_no=out_trade_no).first()
    if not order:
        logger.warning('微信回调订单不存在 order_no=%s', out_trade_no)
        return False
    total = (resource.get('amount') or {}).get('total')
    if total and int(total) != order.amount:
        logger.error('订单金额不符 order_no=%s 微信=%s 本地=%s',
                     out_trade_no, total, order.amount)
        return False
    return settle_order(order, resource.get('transaction_id') or '', resource)


def sync_order(order: VipOrder) -> bool:
    """主动向微信查单：回调丢失时的兜底，也用于前端轮询时确认结果。"""
    from apps.membership import pay

    if order.status != VipOrder.STATUS_PENDING or not settings.WXPAY_ENABLED:
        return order.is_paid
    try:
        data = pay.query_order(order.order_no)
    except Exception as exc:
        logger.warning('查单失败 order_no=%s: %s', order.order_no, exc)
        return False

    state = data.get('trade_state')
    if state == pay.TRADE_STATE_SUCCESS:
        settle_order(order, data.get('transaction_id') or '', data)
        return True
    if state in pay.TRADE_STATE_FAILED or order.is_expired:
        close_pending_order(order)
    return False


def close_pending_order(order: VipOrder) -> None:
    """关闭未支付订单（超时或用户在微信侧取消）。"""
    from apps.membership import pay

    if order.status != VipOrder.STATUS_PENDING:
        return
    if settings.WXPAY_ENABLED:
        pay.close_order(order.order_no)
    _write_off(order, VipOrder.STATUS_CLOSED)
