# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.response import BusinessError, api_response
from apps.membership import pay as wxpay
from apps.membership.models import BENEFITS, VipConfig, VipOrder, VipPlan, VipSubscription
from apps.membership.serializers import (
    VipConfigSerializer,
    VipPlanSerializer,
)
from apps.membership.services import (
    close_pending_order,
    create_vip_order,
    describe,
    grant,
    is_vip,
    order_view,
    pay_params,
    settle_notify,
    sync_order,
    trial_used,
)
from domain.money import yuan

logger = logging.getLogger('django.request')


def _plan_view(plan: VipPlan) -> dict:
    data = VipPlanSerializer(plan).data
    data['price'] = yuan(plan.price_cents)
    data['original_price'] = yuan(plan.original_price_cents)
    return data


def _client_ip(request) -> str:
    """H5 下单要带用户真实 IP（微信会校验）。"""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR') or ''
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or ''


def _guess_scene(request) -> str:
    """前端没传场景时按 UA 猜：微信内 JSAPI，其它浏览器走 H5。"""
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    return VipOrder.SCENE_JSAPI if 'micromessenger' in ua else VipOrder.SCENE_H5


def _need_openid_payload(request, scene: str, next_url: str = '') -> dict:
    """还没绑微信：公众号给授权跳转地址，小程序提示前端先 wx.login。"""
    if scene == VipOrder.SCENE_MINI:
        return {
            'need_openid': True,
            'scene': scene,
            'auth_url': '',
            'message': '请先在小程序内完成微信登录再支付',
        }
    auth_url = reverse('auth-wechat-authorize')
    target = quote(next_url or '/', safe='')
    return {
        'need_openid': True,
        'scene': scene,
        'auth_url': f'{auth_url}?next={target}',
        'message': '正在跳转微信授权…',
    }


def _order_payload(order: VipOrder) -> dict:
    """订单 + 调起支付的参数。"""
    data = order_view(order)
    if order.status == VipOrder.STATUS_PENDING:
        data['pay_params'] = pay_params(order)
    else:
        data['pay_params'] = None
    data['mweb_url'] = order.h5_url if order.scene == VipOrder.SCENE_H5 else None
    return data


class MembershipView(APIView):
    """会员中心首页数据：权益对比 + 在售套餐 + 我的状态 + 试用配置。

    允许未登录访问（游客也能看到介绍页），登录后带上自己的状态。
    """

    permission_classes = [AllowAny]

    def get(self, request):
        plans = [_plan_view(p) for p in VipPlan.objects.filter(is_active=True)]
        cfg = VipConfig.get()
        user = request.user if request.user.is_authenticated else None
        return api_response({
            'benefits': BENEFITS,
            'plans': plans,
            'trial_days': cfg.trial_days,
            'trial_enabled': cfg.trial_enabled,
            'mine': describe(user) if user else None,
        })


class MineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_response(describe(request.user))


class TrialView(APIView):
    """领取免费试用：每人限一次，天数由管理员配置。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        cfg = VipConfig.get()
        if not cfg.trial_enabled:
            raise BusinessError('免费试用未开放')
        if cfg.trial_days <= 0:
            raise BusinessError('试用天数未配置')
        if trial_used(request.user):
            raise BusinessError('免费试用每人仅限一次')
        # 已是会员就不再消耗试用机会
        from apps.membership.services import active_subscription

        if active_subscription(request.user):
            raise BusinessError('你已是会员，无需试用')
        grant(request.user, days=cfg.trial_days, source=VipSubscription.SOURCE_TRIAL)
        return api_response(describe(request.user),
                            message=f'已开通 {cfg.trial_days} 天 VIP 试用')


class SubscribeView(APIView):
    """开通 / 续费：下单 → 前端调起微信支付 → 回调到账后开通会员。

    入参 scene 决定支付渠道：
    · mini  —— 小程序内 JSAPI 支付（需 wx.login 绑定过 openid）
    · jsapi —— 微信浏览器内 JSAPI 支付（需公众号网页授权拿到 openid）
    · h5    —— 微信外浏览器，下单拿 mweb_url 跳转微信收银台
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = 'writes'

    class _InlineSerializer(serializers.Serializer):
        plan_id = serializers.PrimaryKeyRelatedField(source='plan',
                                                     queryset=VipPlan.objects.all())
        scene = serializers.ChoiceField(choices=VipOrder.SCENE_CHOICES, required=False)
        # 需要网页授权时，授权完回跳的前端地址
        next_url = serializers.CharField(required=False, allow_blank=True)

    def post(self, request):
        ser = self._InlineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        plan = ser.validated_data['plan']
        scene = ser.validated_data.get('scene') or _guess_scene(request)
        if not plan.is_active:
            raise BusinessError('该套餐已下架')

        # 未配置支付：正式环境直接拒绝，DEBUG 下即开即用，方便本地联调
        if not settings.WXPAY_ENABLED:
            if not settings.DEBUG:
                raise BusinessError('在线支付未开通，请稍后再试')
            order_no = f'VIP{timezone.now():%Y%m%d%H%M%S}{request.user.id[:6]}'
            grant(request.user, days=plan.duration_days, plan=plan,
                  source=VipSubscription.SOURCE_PURCHASE, order_no=order_no)
            return api_response(
                {'mode': 'mock', 'status': 'paid', 'mine': describe(request.user)},
                message=f'已开通{plan.name}（本地联调，未真实扣款）')

        # JSAPI / 小程序必须要有 openid，没有就先让前端去授权
        if scene != VipOrder.SCENE_H5 and not request.user.openid:
            return api_response(_need_openid_payload(
                request, scene, ser.validated_data.get('next_url') or ''))

        # 同一套餐已有待支付订单就复用，避免用户多点几次堆出一堆订单
        order = (VipOrder.objects
                 .filter(user=request.user, plan=plan, scene=scene,
                         status=VipOrder.STATUS_PENDING)
                 .order_by('-created_at')
                 .first())
        if order and order.is_expired:
            close_pending_order(order)
            order = None
        if order:
            return api_response(_order_payload(order), message='请在微信内完成支付')

        try:
            order = create_vip_order(request.user, plan, scene,
                                     client_ip=_client_ip(request))
        except BusinessError:
            raise
        except Exception as exc:
            logger.exception('微信下单失败 user=%s plan=%s', request.user.id, plan.id)
            raise BusinessError(f'下单失败：{exc}')

        return api_response(_order_payload(order), message='订单已创建，请在微信内完成支付')


class OrderDetailView(APIView):
    """查询订单状态。

    前端支付完轮询这个接口；只要回调没到，这里会主动向微信查一次单补发，
    避免用户付了钱但会员没到账。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, order_no):
        order = VipOrder.objects.filter(order_no=order_no, user=request.user).first()
        if not order:
            raise BusinessError('订单不存在')
        if order.status == VipOrder.STATUS_PENDING:
            if order.is_expired:
                close_pending_order(order)
            elif settings.WXPAY_ENABLED:
                # 给微信一点时间落单，刚创建就查会查不到
                sync_order(order)
            order.refresh_from_db()
        payload = _order_payload(order)
        payload['is_vip'] = is_vip(request.user)
        return api_response(payload)


class OrderCloseView(APIView):
    """用户放弃支付：主动关单。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, order_no):
        order = VipOrder.objects.filter(order_no=order_no, user=request.user).first()
        if not order:
            raise BusinessError('订单不存在')
        close_pending_order(order)
        return api_response(order_view(order), message='订单已关闭')


@method_decorator(csrf_exempt, name='dispatch')
class WechatNotifyView(APIView):
    """微信支付结果通知（公网可访问，无鉴权，靠签名校验）。

    流程：验签 → AES-GCM 解密 → 校验金额 → 发货（幂等）。
    微信要求 2xx + {"code":"SUCCESS"} 才算通知成功，否则会重复投递。
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            resource = wxpay.parse_notify(request.headers, request.body)
        except Exception as exc:
            logger.warning('微信支付回调验签失败: %s', exc)
            return Response({'code': 'FAIL', 'message': '签名校验失败'},
                            status=status.HTTP_401_UNAUTHORIZED)

        try:
            settle_notify(resource)
        except Exception:
            logger.exception('微信支付回调处理失败 order_no=%s',
                             resource.get('out_trade_no'))
            return Response({'code': 'FAIL', 'message': '处理失败'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'code': 'SUCCESS', 'message': '成功'})


class AdminConfigView(APIView):
    """管理员配置：调整试用开关与天数（套餐价格在 Django 后台改 VipPlan）。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return api_response(VipConfigSerializer(VipConfig.get()).data)

    def patch(self, request):
        cfg = VipConfig.get()
        ser = VipConfigSerializer(cfg, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return api_response(VipConfigSerializer(cfg).data, message='配置已保存',
                            http_status=status.HTTP_200_OK)
