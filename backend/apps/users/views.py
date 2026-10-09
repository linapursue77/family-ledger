# -*- coding: utf-8 -*-
"""认证相关接口。"""
from django.contrib.auth import authenticate
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.response import BusinessError, api_response
from apps.families.models import Family, FamilyMember, Threshold
from apps.users.models import User
from apps.users.serializers import LoginSerializer, RegisterSerializer, UserSerializer


def _issue_token(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'access_expires_in': 2 * 3600,
        'refresh_expires_in': 30 * 24 * 3600,
    }


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
        family = Family.objects.create(name='我的家庭', owner=user)
        FamilyMember.objects.create(
            family=family,
            user=user,
            role=FamilyMember.ROLE_OWNER,
            nickname=user.nickname,
            book_type=data.get('book_type') or 'husband',
            permissions={},
        )
        Threshold.objects.create(family=family)

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
        privacy_limit_cents = serializers.IntegerField(min_value=10000, max_value=200000,
                                                       required=False)

    def patch(self, request):
        ser = self._InlineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        for key, value in ser.validated_data.items():
            setattr(request.user, key, value)
        request.user.save(update_fields=list(ser.validated_data.keys()))
        return api_response(UserSerializer(request.user).data, message='已更新')
