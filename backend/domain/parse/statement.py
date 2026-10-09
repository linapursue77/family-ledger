# -*- coding: utf-8 -*-
"""账单解析入口：自动识别平台 → 映射 → 统一流水结构。

输出结构（供导入服务消费）：
{
  'platform': 'wechat' | 'alipay',
  'encoding': 'utf-8' | 'gbk' | ...,
  'header': [...],
  'records': [ {type, amount_cents, merchant, description,
                transaction_date, status, dedup_hash}, ... ],
  'skipped': [ {'reason', 'raw'}, ... ],
}
"""
from domain.parse.alipay import parse_alipay
from domain.parse.csv import decode, find_header_row, norm_header, read_rows
from domain.parse.wechat import parse_wechat

PLATFORM_ALIASES = {
    'wechat': 'wechat', 'wx': 'wechat', 'weixin': 'wechat', '微信': 'wechat',
    'alipay': 'alipay', 'zfb': 'alipay', 'ali': 'alipay', '支付宝': 'alipay',
}

PARSERS = {'wechat': parse_wechat, 'alipay': parse_alipay}


def normalize_platform(value: str) -> str | None:
    if not value:
        return None
    return PLATFORM_ALIASES.get(str(value).strip().lower())


def detect_platform(header: list[str]) -> str | None:
    """按表头特征识别平台。"""
    norm = {norm_header(c) for c in header}
    if {'交易单号', '商户单号', '支付方式'} & norm:
        return 'wechat'
    if {'商家订单号', '交易号', '交易来源地', '资金状态'} & norm:
        return 'alipay'
    return None


def parse_statement(data: bytes, platform: str = None) -> dict:
    """解析账单文件字节流。解析失败抛 ValueError（由调用方转业务错误）。"""
    if not data:
        raise ValueError('文件内容为空')

    text, encoding = decode(data)
    rows = read_rows(text)
    if not rows:
        raise ValueError('未读取到任何有效行')

    header_idx = find_header_row(rows)
    if header_idx < 0:
        raise ValueError('未识别到账单表头，请确认导出的是微信/支付宝账单 CSV')

    header = rows[header_idx]
    detected = (normalize_platform(platform)
                or detect_platform(header)
                or 'wechat')
    parser = PARSERS.get(detected, parse_wechat)
    records, skipped = parser(rows[header_idx + 1:], header)

    if not records:
        raise ValueError('未解析到可导入的记录（可能全是退款/不计收支）')

    return {
        'platform': detected,
        'encoding': encoding,
        'header': header,
        'records': records,
        'skipped': skipped,
        'total': len(records) + len(skipped),
    }
