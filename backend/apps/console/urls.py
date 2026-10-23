# -*- coding: utf-8 -*-
"""管理后台路由。全部要求 is_staff，与 C 端接口完全隔离。"""
from django.urls import path

from apps.console.views import (
    OverviewView,
    PlanListView,
    RecurringOverviewView,
    ScheduleListView,
    ScheduleRunView,
    ScheduleToggleView,
    SubscriptionDetailView,
    SubscriptionListView,
    UserDetailView,
    UserListView,
)

app_name = 'console'

urlpatterns = [
    path('overview/', OverviewView.as_view(), name='overview'),
    # 注册账号
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<str:user_id>/', UserDetailView.as_view(), name='user-detail'),
    # 会员
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('subscriptions/', SubscriptionListView.as_view(), name='subscription-list'),
    path('subscriptions/<str:sub_id>/', SubscriptionDetailView.as_view(),
         name='subscription-detail'),
    # 定时任务
    path('schedules/', ScheduleListView.as_view(), name='schedule-list'),
    path('schedules/<int:schedule_id>/run/', ScheduleRunView.as_view(),
         name='schedule-run'),
    path('schedules/<int:schedule_id>/', ScheduleToggleView.as_view(),
         name='schedule-toggle'),
    # 周期记账
    path('recurring/', RecurringOverviewView.as_view(), name='recurring'),
]
