# -*- coding: utf-8 -*-
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import (
    LoginView,
    MeView,
    ProfileUpdateView,
    RegisterView,
    WechatAuthorizeView,
    WechatCallbackView,
    WechatOpenidView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('profile/', ProfileUpdateView.as_view(), name='auth-profile'),
    # 微信身份：小程序 code 换 openid / 公众号网页授权（支付前需要）
    path('wechat/openid/', WechatOpenidView.as_view(), name='auth-wechat-openid'),
    path('wechat/authorize/', WechatAuthorizeView.as_view(), name='auth-wechat-authorize'),
    path('wechat/callback/', WechatCallbackView.as_view(), name='auth-wechat-callback'),
]
