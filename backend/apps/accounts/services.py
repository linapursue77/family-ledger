# -*- coding: utf-8 -*-
"""账户可见性与归属校验 —— 与 domain/visibility.py 的交易过滤保持同一套规则。

规则：
    · 自己的账户：全见、可改、可删、可调余额
    · 对方的账户：可见，但「仅本人可见（private）」的对我不存在
    · 写操作一律只允许账户归属人本人，主账号也不例外（账户是个人财产）
"""
from django.db.models import Q

from apps.accounts.models import Account
from apps.core.response import BusinessError


def visible_accounts(family, user):
    """家庭内对 user 可见的账户 queryset。

    排除「属于他人 且 标记为 private」的账户，避免「仅本人可见」只是加了个锁图标。
    """
    return (Account.objects.filter(family=family)
            .exclude(~Q(user_id=user.id), type=Account.TYPE_PRIVATE))


def assert_own_account(account, user, action='操作'):
    """写操作归属校验：只能动自己的账户。"""
    if str(account.user_id) != str(user.id):
        raise BusinessError(f'只能{action}自己的账户', code=4003)
    return account
