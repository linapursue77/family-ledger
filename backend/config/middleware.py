# -*- coding: utf-8 -*-
"""自研中间件（对齐 TestHub 做法，并补齐链路追踪）。"""
import logging
import time
import uuid

logger = logging.getLogger('family-ledger.request')

TRACE_ID_HEADER = 'X-Trace-Id'
SLOW_REQUEST_MS = 500


class TraceIdMiddleware:
    """为每次请求生成 traceId，便于日志串联与前端排障。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = request.headers.get(TRACE_ID_HEADER) or uuid.uuid4().hex
        request.trace_id = trace_id
        response = self.get_response(request)
        response[TRACE_ID_HEADER] = trace_id
        return response


class RequestTimingMiddleware:
    """记录耗时，慢请求告警（阈值 500ms）。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        cost_ms = (time.perf_counter() - start) * 1000
        if cost_ms >= SLOW_REQUEST_MS:
            logger.warning(
                'SLOW %.1fms %s %s trace=%s',
                cost_ms,
                request.method,
                request.path,
                getattr(request, 'trace_id', '-'),
            )
        return response
