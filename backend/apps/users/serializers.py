# -*- coding: utf-8 -*-
import re

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password

from apps.users import sms_services
from apps.users.models import SmsCode, User

PHONE_RE = re.compile(r'^1[3-9]\d{9}$')


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    nickname = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    book_type = serializers.ChoiceField(
        choices=['husband', 'wife'], required=False, default='husband'
    )

    def validate_phone(self, value):
        if not PHONE_RE.match(value):
            raise serializers.ValidationError('手机号格式不正确')
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('该手机号已注册')
        return value

    def validate(self, attrs):
        # 注册也要走密码强度校验，否则「注册能设 123456、找回密码却不允许」，标准不一致。
        # 传一个未保存的 User 实例，让「密码不能太像手机号/昵称」这类校验能生效。
        probe = User(phone=attrs['phone'], username=attrs['phone'],
                     nickname=attrs.get('nickname') or '')
        validate_password(attrs['password'], probe)
        return attrs


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    """用户资料。has_password 决定「我的」页显示「设置密码」还是「修改密码」。"""

    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'avatar_url', 'phone',
                  'privacy_limit_cents', 'has_password']
        read_only_fields = ['id', 'username', 'has_password']

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class SmsSendSerializer(serializers.Serializer):
    """发送验证码。"""

    phone = serializers.RegexField(PHONE_RE, error_messages={'invalid': '请输入正确的手机号'})
    scene = serializers.ChoiceField(choices=[SmsCode.SCENE_RESET, SmsCode.SCENE_BIND],
                                   required=False, default=SmsCode.SCENE_RESET)


class PasswordResetSerializer(serializers.Serializer):
    """验证码重置密码。"""

    phone = serializers.RegexField(PHONE_RE, error_messages={'invalid': '请输入正确的手机号'})
    code = serializers.CharField(min_length=4, max_length=8)
    new_password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    confirm_password = serializers.CharField(write_only=True, required=False,
                                             allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('confirm_password') and attrs['confirm_password'] != attrs['new_password']:
            raise serializers.ValidationError('两次输入的新密码不一致')
        phone = attrs['phone']
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            # 不发短信却走到这一步，说明是伪造请求；给统一文案即可
            raise serializers.ValidationError('验证码不正确')
        attrs['user'] = user

        # 顺序很关键：先校验密码强度，再消耗验证码。
        # 反过来的话，用户只是密码格式写错，验证码就被作废了，得重新发短信——体验很差。
        validate_password(attrs['new_password'], user)

        # verify_code 用 ValueError 表达「验证码不对/过期/次数用尽」这类可展示的业务错误，
        # 必须转成 ValidationError，否则会冒泡成 500，用户只看到「服务异常」
        try:
            sms_services.verify_code(phone, SmsCode.SCENE_RESET, attrs['code'])
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        return attrs


class PasswordUpdateSerializer(serializers.Serializer):
    """设置 / 修改登录密码。

    old_password 只在「已经有密码」时必填；微信一键登录建的用户没有密码，
    处于已登录的高信任态，可以直接补一个，不需要原密码。
    """

    old_password = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                         default='')
    new_password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    confirm_password = serializers.CharField(write_only=True, required=False,
                                             allow_blank=True, default='')

    def validate(self, attrs):
        user = self.context['user']
        new_pwd = attrs['new_password']

        if user.has_usable_password():
            if not attrs.get('old_password'):
                raise serializers.ValidationError('请先填写当前密码')
            if not user.check_password(attrs['old_password']):
                raise serializers.ValidationError('当前密码不正确')
        else:
            # 无密码用户（纯微信）不校验 old_password，但也不允许误传后静默忽略
            attrs['old_password'] = ''

        confirm = attrs.get('confirm_password') or ''
        if confirm and confirm != new_pwd:
            raise serializers.ValidationError('两次输入的新密码不一致')

        # 复用 Django 的密码强度校验：≥6 位、不能全数字、不能太像用户名/手机号
        validate_password(new_pwd, user)
        return attrs
