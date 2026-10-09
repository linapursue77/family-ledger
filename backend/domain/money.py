# -*- coding: utf-8 -*-
"""金额处理：内部一律用「分」(int) 存储与运算，杜绝浮点误差。"""
from decimal import ROUND_HALF_UP, Decimal

Cents = int


def to_cents(value) -> Cents:
    """任意输入（str/int/float/Decimal/'¥12.35'）→ 分。"""
    if value is None or value == '':
        return 0
    text = str(value).strip().replace('¥', '').replace(',', '').replace('￥', '')
    if text.startswith('+'):
        text = text[1:]
    try:
        dec = Decimal(text)
    except Exception:
        raise ValueError(f'无法解析金额: {value!r}')
    return int(dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)


def from_cents(cents: Cents) -> Decimal:
    """分 → Decimal 元。"""
    return (Decimal(int(cents)) / 100).quantize(Decimal('0.01'))


def yuan(cents: Cents) -> float:
    """分 → float 元（仅用于图表，禁止用于计算）。"""
    return round(int(cents) / 100, 2)


def format_cents(cents: Cents, with_symbol: bool = True) -> str:
    """分 → '¥12,350.00'"""
    sign = '-' if cents < 0 else ''
    value = from_cents(abs(int(cents)))
    text = f'{value:,.2f}'
    return f'{sign}¥{text}' if with_symbol else f'{sign}{text}'


def safe_pct(part: Cents, total: Cents) -> float:
    """占比百分比，分母为 0 时返回 0。"""
    if not total:
        return 0.0
    return round(int(part) / int(total) * 100, 2)
