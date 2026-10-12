# -*- coding: utf-8 -*-
from django.urls import path

from apps.membership.views import (
    AdminConfigView,
    MembershipView,
    MineView,
    OrderCloseView,
    OrderDetailView,
    SubscribeView,
    TrialView,
    WechatNotifyView,
)

app_name = 'membership'

urlpatterns = [
    path('', MembershipView.as_view(), name='membership-home'),
    path('mine/', MineView.as_view(), name='membership-mine'),
    path('trial/', TrialView.as_view(), name='membership-trial'),
    # 开通 / 续费下单：返回调起微信支付所需参数
    path('subscribe/', SubscribeView.as_view(), name='membership-subscribe'),
    path('orders/<str:order_no>/', OrderDetailView.as_view(), name='membership-order-detail'),
    path('orders/<str:order_no>/close/', OrderCloseView.as_view(), name='membership-order-close'),
    # 微信支付结果通知（公网回调，无鉴权，靠签名校验）
    path('notify/wechat/', WechatNotifyView.as_view(), name='membership-notify-wechat'),
    path('admin/config/', AdminConfigView.as_view(), name='membership-admin-config'),
]
