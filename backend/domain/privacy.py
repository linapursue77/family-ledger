# -*- coding: utf-8 -*-
"""隐私消费规则（PRD 4.4）。

- 单笔 ≤ 月度额度：用户可自行选择是否私密
- 单笔 > 月度额度：不允许私密，直接计入共同支出
- 当月累计私密 ≥ 月度额度：超出部分自动公开
"""

DEFAULT_LIMIT_CENTS = 50000   # ¥500
MIN_LIMIT_CENTS = 10000       # ¥100
MAX_LIMIT_CENTS = 200000      # ¥2000


def check_quota(amount_cents: int, used_cents: int, limit_cents: int) -> dict:
    """记账前校验。返回是否允许私密、用量与超出部分。"""
    limit = clamp_limit(limit_cents)
    amount = abs(int(amount_cents))
    used = int(used_cents)

    allow_private = amount <= limit
    remaining = max(0, limit - used)
    # 超出额度的部分
    overflow = max(0, used + amount - limit)

    return {
        'allow_private': allow_private,
        'limit_cents': limit,
        'used_cents': used,
        'remaining_cents': remaining,
        'overflow_cents': overflow,
        'will_auto_public': overflow > 0,
        'reason': '' if allow_private else '单笔金额超过隐私额度，将计入共同支出',
    }


def split_private_amount(amount_cents: int, used_cents: int, limit_cents: int) -> tuple[int, int]:
    """把一笔私密消费拆成 (私密部分, 自动公开部分)。"""
    limit = clamp_limit(limit_cents)
    amount = abs(int(amount_cents))
    remaining = max(0, limit - int(used_cents))
    private_part = min(amount, remaining)
    public_part = amount - private_part
    return private_part, public_part


def clamp_limit(limit_cents: int) -> int:
    """额度上下限收敛。"""
    try:
        value = int(limit_cents)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT_CENTS
    return max(MIN_LIMIT_CENTS, min(MAX_LIMIT_CENTS, value))
