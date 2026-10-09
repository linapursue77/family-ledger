# -*- coding: utf-8 -*-
"""ASGI 入口。

启动：python -m uvicorn config.asgi:application --host 0.0.0.0 --port 8000
注意：工作目录必须是 backend/，否则模块导入失败。
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
