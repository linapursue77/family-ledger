# -*- coding: utf-8 -*-
"""统一分页器。

DRF 默认分页会直接返回 {count, next, previous, results}，
绕过统一信封，导致前端要为「分页接口」和「非分页接口」写两套解析。
这里强制所有列表接口都返回：

    {"code":0,"message":"ok","data":{"items":[...], "pagination":{...}}, "traceId":"..."}
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.response import CODE_OK, api_response


class ApiPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        trace_id = getattr(self.request, 'trace_id', None)
        return api_response({
            'items': data,
            'pagination': {
                'count': self.page.paginator.count,
                'page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'total_pages': self.page.paginator.num_pages,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
        }, trace_id=trace_id)

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'code': {'type': 'integer'},
                'message': {'type': 'string'},
                'traceId': {'type': 'string'},
                'data': {
                    'type': 'object',
                    'properties': {
                        'items': schema,
                        'pagination': {'type': 'object'},
                    },
                },
            },
        }
