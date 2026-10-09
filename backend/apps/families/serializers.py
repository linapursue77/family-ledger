# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.families.models import Family, FamilyMember, Invitation, Threshold


class FamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = Family
        fields = ['id', 'name', 'owner', 'created_at']
        read_only_fields = ['id', 'owner', 'created_at']


class MemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = FamilyMember
        fields = ['id', 'user', 'username', 'role', 'nickname', 'book_type',
                  'permissions', 'joined_at']
        read_only_fields = ['id', 'user', 'role', 'joined_at']

    def get_permissions(self, obj):
        return obj.effective_permissions


class MemberPermissionSerializer(serializers.Serializer):
    report_view = serializers.ChoiceField(choices=['all', 'own'], required=False)
    account_view = serializers.ChoiceField(choices=['all', 'own'], required=False)
    allow_record = serializers.BooleanField(required=False)
    show_private = serializers.BooleanField(required=False)
    settings_level = serializers.ChoiceField(choices=['full', 'basic'], required=False)


class InvitationCreateSerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=50)
    contact = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    permissions = serializers.JSONField(required=False, default=dict)


class ThresholdSerializer(serializers.Serializer):
    small_limit = serializers.IntegerField(min_value=0)      # 分
    notify_limit = serializers.IntegerField(min_value=0)
    approve_limit = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        small = attrs.get('small_limit')
        notify = attrs.get('notify_limit')
        approve = attrs.get('approve_limit')
        if small is not None and notify is not None and small >= notify:
            raise serializers.ValidationError('小额自主上限必须小于事后知会上限')
        if notify is not None and approve is not None and notify >= approve:
            raise serializers.ValidationError('事后知会上限必须小于事前申请上限')
        return attrs
