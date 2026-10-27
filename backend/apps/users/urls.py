# -*- coding: utf-8 -*-
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import (
    BindPhoneView,
    LoginView,
    MeView,
    PasswordResetView,
    PasswordUpdateView,
    ProfileUpdateView,
    RegisterView,
    SmsSendView,
    WechatAuthorizeView,
    WechatCallbackView,
    WechatLoginView,
    WechatMpCallbackView,
    WechatMpConfigView,
    WechatMpLoginView,
    WechatMpTicketView,
    WechatOpenidView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('profile/', ProfileUpdateView.as_view(), name='auth-profile'),
    # 打通两端账号：给微信账号补手机号（顺带可设密码），之后 H5 也能登录
    path('bind-phone/', BindPhoneView.as_view(), name='auth-bind-phone'),
    # 设置 / 修改登录密码：微信一键登录的用户在这里补密码，之后可用手机号登录 H5
    path('password/', PasswordUpdateView.as_view(), name='auth-password'),
    # 忘记密码：短信验证码 → 重置密码
    path('sms/send/', SmsSendView.as_view(), name='auth-sms-send'),
    path('password/reset/', PasswordResetView.as_view(), name='auth-password-reset'),
    # 微信身份：小程序 code 换 openid / 公众号网页授权（支付前需要）
    path('wechat/login/', WechatLoginView.as_view(), name='auth-wechat-login'),
    path('wechat/openid/', WechatOpenidView.as_view(), name='auth-wechat-openid'),
    path('wechat/authorize/', WechatAuthorizeView.as_view(), name='auth-wechat-authorize'),
    path('wechat/callback/', WechatCallbackView.as_view(), name='auth-wechat-callback'),
    # 公众号网页授权登录（H5 端「微信一键登录」）：登录态不是前提，授权回来直接发 token
    path('wechat/mp/config/', WechatMpConfigView.as_view(), name='auth-wechat-mp-config'),
    path('wechat/mp/authorize/', WechatMpLoginView.as_view(), name='auth-wechat-mp-authorize'),
    path('wechat/mp/callback/', WechatMpCallbackView.as_view(), name='auth-wechat-mp-callback'),
    path('wechat/mp/ticket/', WechatMpTicketView.as_view(), name='auth-wechat-mp-ticket'),
]
