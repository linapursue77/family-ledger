# -*- coding: utf-8 -*-
"""认证相关接口。"""
import logging
from urllib.parse import quote, urlparse

from django.conf import settings
from django.contrib.auth import authenticate
from django.core import signing
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.views import book_labels
from apps.core.response import BusinessError, api_response
from apps.families.models import Family, FamilyMember, Threshold
from apps.membership import pay as wxpay
from apps.users import sms_services
from apps.users.models import SmsCode, User
from apps.users.serializers import (PHONE_RE, LoginSerializer, PasswordResetSerializer,
                                    PasswordUpdateSerializer, RegisterSerializer,
                                    SmsSendSerializer, UserSerializer)

logger = logging.getLogger('django.request')
# 网页授权 state 的签名盐值与有效期
OAUTH_SALT = 'wechat-oauth'
OAUTH_MAX_AGE = 10 * 60


def _client_ip(request) -> str:
    """取客户端 IP（用于短信限流）。取 X-Forwarded-For 最左段，伪造只影响限流不越权。"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def _issue_token(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'access_expires_in': 2 * 3600,
        'refresh_expires_in': 30 * 24 * 3600,
    }


def _create_family_for(user: User, book_type: str = 'husband') -> None:
    """新用户落地：默认建一个家庭并成为主账号。"""
    family = Family.objects.create(name='我的家庭', owner=user)
    FamilyMember.objects.create(
        family=family,
        user=user,
        role=FamilyMember.ROLE_OWNER,
        nickname=user.nickname,
        book_type=book_type or 'husband',
        permissions={},
    )
    Threshold.objects.create(family=family)


def _me_payload(user: User) -> dict:
    member = FamilyMember.objects.filter(user=user).select_related('family').first()
    if not member:
        return {'user': UserSerializer(user).data, 'family': None, 'member': None}

    threshold = Threshold.objects.filter(family=member.family).first()
    return {
        'user': UserSerializer(user).data,
        'family': {
            'id': member.family_id,
            'name': member.family.name,
            'owner_id': member.family.owner_id,
            # 账本自定义名：记账页等场景要按登录身份默认选中账本并展示其名称
            'book_labels': book_labels(member.family),
        },
        'member': {
            'id': member.id,
            'role': member.role,
            'nickname': member.nickname,
            'book_type': member.book_type,
            'permissions': member.effective_permissions,
        },
        'thresholds': threshold.to_dict() if threshold else None,
    }


class RegisterView(APIView):
    """注册：自动创建家庭并成为主账号。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=RegisterSerializer,
                   responses=OpenApiResponse(description='注册成功返回 token'))
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        user = User.objects.create_user(
            username=data['phone'],
            password=data['password'],
            phone=data['phone'],
            nickname=data.get('nickname') or data['phone'][-4:],
        )
        _create_family_for(user, data.get('book_type'))

        return api_response(
            {'user': UserSerializer(user).data, 'token': _issue_token(user)},
            message='注册成功',
            http_status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """登录：手机号 + 密码。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        user = authenticate(request, username=data['phone'], password=data['password'])
        if user is None:
            raise BusinessError('手机号或密码错误', code=4002)

        return api_response({
            'token': _issue_token(user),
            'profile': _me_payload(user),
        })


class MeView(APIView):
    """当前登录用户与家庭上下文。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_response(_me_payload(request.user))


class ProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    class _InlineSerializer(serializers.Serializer):
        nickname = serializers.CharField(max_length=50, required=False)
        avatar_url = serializers.CharField(max_length=255, required=False, allow_blank=True)
        # ¥100 ~ ¥5000：不收费阶段上限按最高档放开
        privacy_limit_cents = serializers.IntegerField(min_value=10000, max_value=500000,
                                                       required=False)

    def patch(self, request):
        ser = self._InlineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        for key, value in ser.validated_data.items():
            setattr(request.user, key, value)
        request.user.save(update_fields=list(ser.validated_data.keys()))
        return api_response(UserSerializer(request.user).data, message='已更新')


# --------------------------------------------------------------------------- 微信身份
def _bind_openid(user: User, openid: str) -> bool:
    """把 openid 绑到当前账号；已被别人占用时不覆盖，也不让授权流程中断。"""
    if not openid or user.openid == openid:
        return False
    if User.objects.filter(openid=openid).exclude(pk=user.pk).exists():
        logger.warning('openid 已被其它账号占用 user=%s', user.id)
        return False
    user.openid = openid
    user.save(update_fields=['openid'])
    return True


def _safe_next(url: str) -> str:
    """只允许跳回本站路径，避免授权回调变成开放重定向。

    前端是 hash 路由（/#/member），绝对地址要保留 query 与 hash，否则跳丢页面。
    """
    if not url or url.startswith('//') or url.startswith('/\\'):
        return '/'
    parsed = urlparse(url)
    if parsed.scheme and not parsed.netloc:  # javascript: 之类
        return '/'
    if parsed.netloc:
        target = (parsed.path or '/') or '/'
        if parsed.query:
            target += '?' + parsed.query
        if parsed.fragment:
            target += '#' + parsed.fragment
        return target if target.startswith('/') else '/'
    return url if url.startswith('/') else '/'


class WechatOpenidView(APIView):
    """小程序支付前绑定身份：wx.login 拿 code，后端换 openid 存到当前账号。"""

    permission_classes = [IsAuthenticated]

    class _InlineSerializer(serializers.Serializer):
        code = serializers.CharField(max_length=128)

    def post(self, request):
        ser = self._InlineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            openid = wxpay.jscode2session(ser.validated_data['code'])
        except BusinessError:
            raise
        except Exception as exc:
            logger.warning('微信 code2session 失败: %s', exc)
            raise BusinessError('微信登录失败，请重试')
        if not openid:
            raise BusinessError('未取到微信身份，请重试')
        _bind_openid(request.user, openid)
        return api_response({'openid_bound': True}, message='已绑定微信')


class WechatLoginView(APIView):
    """微信一键登录：wx.login 的 code 换 openid，首次进入自动建号，无需密码。

    两层能力：
    1. 静默登录（所有主体可用）：只传 code，用 openid 定位/创建账号；
    2. 手机号快捷验证（限非个人主体+已认证，0.03 元/次）：额外传 phone_code，
       把微信手机号绑到账号。权限不足或额度用尽时静默降级，不影响登录。

    账号合并：手机号已存在且未绑微信时，直接把 openid 绑到老账号，避免一人两号。
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    class _InlineSerializer(serializers.Serializer):
        code = serializers.CharField(max_length=128)
        phone_code = serializers.CharField(max_length=128, required=False,
                                           allow_blank=True, default='')
        nickname = serializers.CharField(max_length=50, required=False,
                                        allow_blank=True, default='')
        avatar_url = serializers.CharField(max_length=255, required=False,
                                          allow_blank=True, default='')
        book_type = serializers.ChoiceField(choices=['husband', 'wife'],
                                            required=False, default='husband')

    def post(self, request):
        ser = self._InlineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            openid = wxpay.jscode2session(data['code'])
        except BusinessError:
            raise
        except Exception as exc:
            logger.warning('微信 code2session 失败: %s', exc)
            raise BusinessError('微信登录失败，请重试')
        if not openid:
            raise BusinessError('未取到微信身份，请重试')

        # 手机号是可选增强：拿不到只降级，不阻断登录
        phone, phone_error = '', ''
        if data.get('phone_code'):
            try:
                phone = wxpay.get_phone_number(data['phone_code'])
            except Exception as exc:
                phone_error = str(exc)
                logger.warning('微信手机号获取失败 openid=%s: %s', openid, exc)
        if phone and not PHONE_RE.match(phone):
            phone = ''

        user = User.objects.filter(openid=openid).first()
        by_phone = (User.objects.filter(phone=phone).exclude(openid=openid).first()
                    if phone else None)
        is_new = merged = False

        if user is None and by_phone is not None and not by_phone.openid:
            # 老账号（手机号注册）首次用微信登录 → 合并，而不是新建第二个账号
            by_phone.openid = openid
            by_phone.save(update_fields=['openid'])
            user, merged = by_phone, True
        elif user is None:
            is_new = True
            # 手机号可能已被别的微信账号占用（by_phone 已绑过），这时只建无手机号的账号，
            # 不能硬写，否则撞 phone 唯一索引直接 500。
            safe_phone = (phone if phone
                          and not User.objects.filter(phone=phone).exists() else None)
            user = User.objects.create_user(
                username=f'wx_{openid}',  # openid 28 位，全局唯一，不会撞号
                openid=openid,
                phone=safe_phone,
                nickname=data.get('nickname') or f'微信用户{openid[-4:]}',
                avatar_url=data.get('avatar_url') or '',
            )
            user.set_unusable_password()  # 纯微信账号没有密码，只能走微信登录
            user.save(update_fields=['password', 'avatar_url'])
            _create_family_for(user, data.get('book_type'))
        else:
            updates = []
            if data.get('nickname') and not user.nickname:
                user.nickname = data['nickname']
                updates.append('nickname')
            if data.get('avatar_url') and not user.avatar_url:
                user.avatar_url = data['avatar_url']
                updates.append('avatar_url')
            if phone and not user.phone:
                # 手机号已被别人占用时不抢，只回报未绑定，让前端提示
                if not User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
                    user.phone = phone
                    updates.append('phone')
            if updates:
                user.save(update_fields=updates)

        return api_response({
            'token': _issue_token(user),
            'profile': _me_payload(user),
            'is_new': is_new,
            'merged': merged,
            'phone_bound': bool(user.phone),
            'phone_error': phone_error,
        })


class SmsSendView(APIView):
    """发送短信验证码（找回密码 / 绑定手机号）。

    注意：手机号未注册时也返回「已发送」，内部不真发——防止被拿来做用户枚举。
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = SmsSendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        scene = data['scene']

        try:
            # 绑定手机号场景：号被别人占了要挡住，否则会把别人账号的密码改掉
            if scene == SmsCode.SCENE_BIND and User.objects.filter(
                    phone=data['phone']).exists():
                raise BusinessError('该手机号已被注册，请更换')
            result = sms_services.send_code(
                data['phone'], scene, ip=_client_ip(request),
                must_registered=(scene == SmsCode.SCENE_RESET),
            )
        except sms_services.SmsThrottled as exc:
            raise BusinessError(str(exc))

        payload = {'sent': True}
        if result.get('error'):
            raise BusinessError(result['error'])
        if settings.DEBUG and not result['sent']:
            # 开发模式：未注册的号直接提示，方便自测；生产不会走到这里
            payload['debug_hint'] = '手机号未注册（生产环境不返回该提示）'
        return api_response(payload)


class PasswordResetView(APIView):
    """验证码重置密码：手机号 + 验证码 → 新密码。重置后可直接登录。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data['user']
        user.set_password(ser.validated_data['new_password'])
        user.save(update_fields=['password'])
        logger.info('用户 %s 通过短信验证码重置密码', user.username)
        return api_response({'phone': user.phone})


class PasswordUpdateView(APIView):
    """设置 / 修改登录密码。

    微信一键登录建的用户没有密码（set_unusable_password），这里让他在已登录状态下补一个，
    之后就能用「手机号 + 密码」在 H5 端登录。已有密码的用户改密码必须验证原密码。
    """

    def post(self, request):
        ser = PasswordUpdateSerializer(data=request.data,
                                       context={'user': request.user})
        ser.is_valid(raise_exception=True)
        user = request.user
        user.set_password(ser.validated_data['new_password'])
        user.save(update_fields=['password'])
        logger.info('用户 %s %s登录密码', user.username,
                    '修改' if user.has_usable_password() else '设置')
        return api_response({'has_password': True})


class WechatAuthorizeView(APIView):
    """公众号网页授权入口：302 到微信授权页（snsapi_base 静默，用户无感）。

    授权完微信带 code 回 callback，绑好 openid 再跳回 next 指定的前端页面。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (settings.WXPAY_APPID and settings.WXPAY_APP_SECRET):
            raise BusinessError('未配置公众号 appid / secret，无法完成微信授权')
        next_url = _safe_next(request.GET.get('next') or '/')
        state = signing.dumps({'uid': request.user.id, 'next': next_url}, salt=OAUTH_SALT)
        callback = request.build_absolute_uri(reverse('auth-wechat-callback'))
        url = ('https://open.weixin.qq.com/connect/oauth2/authorize'
               f'?appid={settings.WXPAY_APPID}'
               f'&redirect_uri={quote(callback, safe="")}'
               '&response_type=code&scope=snsapi_base'
               f'&state={quote(state)}#wechat_redirect')
        return redirect(url)


class WechatCallbackView(APIView):
    """公众号授权回调：code 换 openid → 绑定 → 跳回前端继续支付。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            data = signing.loads(request.GET.get('state') or '', salt=OAUTH_SALT,
                                 max_age=OAUTH_MAX_AGE)
        except Exception:
            return HttpResponseBadRequest('授权已过期，请重新发起支付')

        user = User.objects.filter(pk=data.get('uid')).first()
        if not user:
            return HttpResponseBadRequest('账号不存在')
        code = request.GET.get('code')
        if code:
            try:
                _bind_openid(user, wxpay.oauth_openid(code))
            except Exception as exc:
                logger.warning('网页授权换 openid 失败 user=%s: %s', user.id, exc)
        return redirect(_safe_next(data.get('next') or '/'))
