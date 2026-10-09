# -*- coding: utf-8 -*-
import re

from rest_framework import serializers

from apps.users.models import User

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


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'nickname', 'avatar_url', 'phone', 'privacy_limit_cents']
        read_only_fields = ['id', 'username']
