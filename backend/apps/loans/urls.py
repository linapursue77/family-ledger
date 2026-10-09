# -*- coding: utf-8 -*-
from django.urls import path

from apps.loans.views import (
    LoanDetailView,
    LoanListView,
    LoanRepaymentDetailView,
    LoanRepaymentView,
)

# repayments 具体路径必须排在 <pk>/ 之前，否则会被当成借款 ID 匹配掉
urlpatterns = [
    path('', LoanListView.as_view(), name='loan-list'),
    path('repayments/<str:pk>/', LoanRepaymentDetailView.as_view(), name='loan-repayment'),
    path('<str:pk>/repayments/', LoanRepaymentView.as_view(), name='loan-repayment-create'),
    path('<str:pk>/', LoanDetailView.as_view(), name='loan-detail'),
]
