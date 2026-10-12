# -*- coding: utf-8 -*-
from django.contrib import admin

from apps.membership.models import VipConfig, VipOrder, VipPlan, VipSubscription


@admin.register(VipPlan)
class VipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price_cents', 'original_price_cents',
                    'duration_days', 'is_active', 'is_recommend', 'sort')
    list_editable = ('price_cents', 'original_price_cents', 'duration_days',
                     'is_active', 'is_recommend', 'sort')
    search_fields = ('name', 'code')


@admin.register(VipSubscription)
class VipSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_at', 'expire_at', 'source', 'order_no')
    list_filter = ('source', 'plan')


@admin.register(VipOrder)
class VipOrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'user', 'plan', 'amount', 'scene', 'status',
                    'transaction_id', 'created_at', 'paid_at')
    list_filter = ('status', 'scene', 'plan')
    search_fields = ('order_no', 'transaction_id', 'user__username', 'user__phone')

    def has_add_permission(self, request):
        # 订单只能由支付流程产生，避免后台手工造已支付订单
        return False


@admin.register(VipConfig)
class VipConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'trial_enabled', 'trial_days', 'updated_at')
    list_editable = ('trial_enabled', 'trial_days')

    def has_add_permission(self, request):
        # 单例表：只能改，不能建第二条
        return not VipConfig.objects.exists()
