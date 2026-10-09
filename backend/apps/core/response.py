# -*- coding: utf-8 -*-
"""统一响应与异常处理。

TestHub 缺的就是这一层：各视图零散返回 {'success':..} / {'message':..} / 裸 data。
本项目强制所有接口走同一信封：

    {"code": 0, "message": "ok", "data": ..., "traceId": "..."}

code 约定：
    0    成功
    4001 参数错误        4002 未认证        4003 无权限
    4004 资源不存在      4005 业务规则拒绝   4006 限流
    5000 服务异常
"""
import logging
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

CODE_OK = 0
CODE_PARAM = 4001
CODE_UNAUTHORIZED = 4002
CODE_FORBIDDEN = 4003
CODE_NOT_FOUND = 4004
CODE_BUSINESS = 4005
CODE_THROTTLED = 4006
CODE_SERVER = 5000


class BusinessError(Exception):
    """业务规则拒绝（可预期错误），会被转成 200 + code=4005。"""

    def __init__(self, message: str, code: int = CODE_BUSINESS, data=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data


def api_response(data=None, message: str = 'ok', code: int = CODE_OK,
                 trace_id: str = None, http_status: int = status.HTTP_200_OK):
    """统一信封响应。"""
    return Response(
        {
            'code': code,
            'message': message,
            'data': data,
            'traceId': trace_id or uuid4().hex,
        },
        status=http_status,
    )


def api_exception_handler(exc, context):
    """DRF EXCEPTION_HANDLER：把各类异常收敛成统一信封。"""
    response = drf_exception_handler(exc, context)

    request = context.get('request')
    trace_id = getattr(request, 'trace_id', None) or uuid4().hex

    if response is None:
        # DRF 未处理的异常
        if isinstance(exc, BusinessError):
            return api_response(exc.data, exc.message, exc.code, trace_id)
        if isinstance(exc, (Http404, ObjectDoesNotExist)):
            return api_response(None, '资源不存在', CODE_NOT_FOUND, trace_id,
                                status.HTTP_200_OK)
        if isinstance(exc, ValidationError):
            return api_response(None, '参数校验失败', CODE_PARAM, trace_id,
                                status.HTTP_200_OK)
        logger.exception('未处理异常 trace=%s', trace_id, exc_info=exc)
        return api_response(None, '服务异常', CODE_SERVER, trace_id,
                            status.HTTP_500_INTERNAL_SERVER_ERROR)

    # DRF 已处理的异常 → 映射 code
    status_code = response.status_code
    code_map = {
        status.HTTP_400_BAD_REQUEST: CODE_PARAM,
        status.HTTP_401_UNAUTHORIZED: CODE_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: CODE_FORBIDDEN,
        status.HTTP_404_NOT_FOUND: CODE_NOT_FOUND,
        # 方法不允许属于「调用方式不对」，落到业务码而不是 5000 服务异常
        status.HTTP_405_METHOD_NOT_ALLOWED: CODE_BUSINESS,
        status.HTTP_429_TOO_MANY_REQUESTS: CODE_THROTTLED,
    }
    code = code_map.get(status_code, CODE_SERVER)
    detail = response.data
    message = '请求失败'
    if isinstance(detail, dict):
        message = detail.get('detail') or detail.get('message') or message
    elif isinstance(detail, list) and detail:
        message = str(detail[0])

    return api_response(
        data=detail if not isinstance(detail, dict) or 'detail' not in detail else None,
        message=str(message),
        code=code,
        trace_id=trace_id,
        http_status=status_code if status_code < 500 else status.HTTP_200_OK,
    )
