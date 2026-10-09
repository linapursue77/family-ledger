# -*- coding: utf-8 -*-
"""核心能力与运维接口。"""
import logging
import os
import time

from django.conf import settings
from django.db import connection
from django.http import FileResponse, HttpResponse
from django.views.static import serve as static_serve
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.response import api_response

logger = logging.getLogger(__name__)
START_TIME = time.time()


class HealthView(APIView):
    """健康检查（供 Nginx / Docker healthcheck 使用）。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception as exc:  # pragma: no cover
            db_ok = False
            logger.warning('health check db failed: %s', exc)

        cache_ok = True
        try:
            from django.core.cache import cache
            cache.set('health:ping', 1, 5)
            cache_ok = cache.get('health:ping') == 1
        except Exception as exc:  # pragma: no cover
            cache_ok = False
            logger.warning('health check cache failed: %s', exc)

        ok = db_ok and cache_ok
        return api_response(
            {
                'status': 'ok' if ok else 'degraded',
                'db': db_ok,
                'cache': cache_ok,
                'uptime': int(time.time() - START_TIME),
            },
            http_status=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ---------------------------------------------------------------- H5 静态托管
def _dist_root() -> str:
    return str(getattr(settings, 'WEB_DIST', ''))


def web_index(request):
    """H5 入口页。没构建过时给一句人话，而不是抛 500。"""
    index = os.path.join(_dist_root(), 'index.html')
    if not os.path.isfile(index):
        return HttpResponse(
            '前端还没构建：在 frontend 目录执行 npm run build 后刷新（或关闭 SERVE_WEB 改由 nginx 发静态）',
            status=503, content_type='text/plain; charset=utf-8')
    return FileResponse(open(index, 'rb'), content_type='text/html; charset=utf-8')


def web_manifest(request):
    """manifest 必须带 application/manifest+json，否则 Chrome 不认。"""
    target = os.path.join(_dist_root(), 'manifest.webmanifest')
    if not os.path.isfile(target):
        return HttpResponse('manifest not found', status=404)
    return FileResponse(open(target, 'rb'), content_type='application/manifest+json')


def web_asset(request, path):
    """/assets/xxx.js 与 /icons/xxx.png：只在 dist 根目录内取文件。"""
    if '..' in path:
        return HttpResponse('bad request', status=400)
    return static_serve(request, path, document_root=_dist_root())
