# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.membership.models import VipConfig, VipPlan


class VipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = VipPlan
        fields = ['id', 'code', 'name', 'price_cents', 'original_price_cents',
                  'duration_days', 'perks', 'is_recommend', 'sort']


class VipSubscribeSerializer(serializers.Serializer):
    # source='plan'：入参叫 plan_id，校验后直接拿到 VipPlan 实例
    plan_id = serializers.PrimaryKeyRelatedField(source='plan',
                                                 queryset=VipPlan.objects.all())


class VipConfigSerializer(serializers.ModelSerializer):
    trial_days = serializers.IntegerField(min_value=0, max_value=365)

    class Meta:
        model = VipConfig
        fields = ['trial_enabled', 'trial_days', 'updated_at']
        read_only_fields = ['updated_at']
