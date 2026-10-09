# -*- coding: utf-8 -*-
"""协商阈值判定（PRD 4.5.2 四档）。

小额自主 ≤ small_limit           → autonomous
事后知会 small_limit~notify      → notify
事前申请 notify~approve          → approval（需配偶同意）
共同决策 > approve               → joint（需双方一致）
"""

AUTONOMOUS = 'autonomous'
NOTIFY = 'notify'
APPROVAL = 'approval'
JOINT = 'joint'

DEFAULT_THRESHOLDS = {
    'small_limit': 50000,      # ¥500（分）
    'notify_limit': 200000,    # ¥2000
    'approve_limit': 500000,   # ¥5000
}

ACTION_TEXT = {
    AUTONOMOUS: '自己决定，不用报备',
    NOTIFY: '消费后通知对方',
    APPROVAL: '消费前需要对方同意',
    JOINT: '需要双方一致同意',
}


def evaluate(amount_cents: int, thresholds: dict = None) -> str:
    """根据金额判定档位。amount_cents 取绝对值。"""
    cfg = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        cfg.update({k: v for k, v in thresholds.items() if v is not None})
    amount = abs(int(amount_cents))

    if amount <= cfg['small_limit']:
        return AUTONOMOUS
    if amount <= cfg['notify_limit']:
        return NOTIFY
    if amount <= cfg['approve_limit']:
        return APPROVAL
    return JOINT


def describe(amount_cents: int, thresholds: dict = None) -> dict:
    """返回前端可直接展示的判定结果。"""
    action = evaluate(amount_cents, thresholds)
    return {
        'action': action,
        'text': ACTION_TEXT[action],
        'need_notify': action in (NOTIFY, APPROVAL, JOINT),
        'need_approval': action in (APPROVAL, JOINT),
    }
