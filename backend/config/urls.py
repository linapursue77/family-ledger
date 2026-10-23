# -*- coding: utf-8 -*-
"""根路由聚合。"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/families/', include('apps.families.urls')),
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/ledger/', include('apps.ledger.urls')),
    path('api/v1/loans/', include('apps.loans.urls')),
    path('api/v1/core/', include('apps.core.urls')),
    path('api/v1/membership/', include('apps.membership.urls')),
    # 管理后台：账号 / 会员 / 定时任务，仅 is_staff 可访问
    path('api/v1/console/', include('apps.console.urls')),
    # API 文档
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.SERVE_WEB:
    # 单端口跑 H5：Django 同时发接口与前端产物（内网试用、单机云服务器都够用）
    from apps.core.views import web_asset, web_index, web_manifest

    urlpatterns += [
        path('manifest.webmanifest', web_manifest, name='web-manifest'),
        re_path(r'^(?P<path>assets/.+|icons/.+)$', web_asset, name='web-asset'),
        path('favicon.ico', web_asset, {'path': 'icons/favicon-32.png'}, name='web-favicon'),
        path('', web_index, name='web-index'),
    ]
