# -*- coding: utf-8 -*-
from django.urls import path

from apps.core.views import HealthView

urlpatterns = [
    path('health/', HealthView.as_view(), name='core-health'),
]
