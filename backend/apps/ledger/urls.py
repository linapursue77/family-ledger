# -*- coding: utf-8 -*-
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.ledger.views import (
    AIConfigTestView,
    AIConfigView,
    CategoryViewSet,
    ImportTaskViewSet,
    MerchantHistoryView,
    OverviewView,
    ReportInsightView,
    ReportView,
    TransactionViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'imports', ImportTaskViewSet, basename='import-task')

urlpatterns = [
    path('overview/', OverviewView.as_view(), name='ledger-overview'),
    path('merchants/history/', MerchantHistoryView.as_view(), name='ledger-merchant-history'),
    path('report/', ReportView.as_view(), name='ledger-report'),
    path('report/insight/', ReportInsightView.as_view(), name='ledger-report-insight'),
    path('ai/config/', AIConfigView.as_view(), name='ledger-ai-config'),
    path('ai/config/test/', AIConfigTestView.as_view(), name='ledger-ai-config-test'),
] + router.urls
