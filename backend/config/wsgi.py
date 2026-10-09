# -*- coding: utf-8 -*-
"""WSGI 入口（生产部署用 gunicorn / uWSGI）。"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
