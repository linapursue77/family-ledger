# -*- coding: utf-8 -*-
"""家庭上下文服务：所有业务视图的公共入口。

★ 铁律：family_id 只从服务端成员关系解析，绝不接受前端传参。
"""
from domain.threshold import DEFAULT_THRESHOLDS
from domain.visibility import ViewerCtx

from apps.families.models import FamilyMember


def get_member(user):
    """当前用户在其家庭中的成员记录。"""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return (FamilyMember.objects
            .filter(user=user)
            .select_related('family')
            .first())


def get_family(user):
    member = get_member(user)
    return member.family if member else None


def require_member(user):
    member = get_member(user)
    if not member:
        from apps.core.response import BusinessError
        raise BusinessError('尚未加入家庭', code=4003)
    return member


def build_viewer_ctx(member: FamilyMember) -> ViewerCtx:
    """构造可见性上下文。"""
    return ViewerCtx(
        viewer_id=str(member.user_id),
        role=member.role,
        permissions=member.effective_permissions,
        family_id=str(member.family_id),
    )


def get_thresholds(family) -> dict:
    """家庭阈值配置（分）。"""
    threshold = getattr(family, 'threshold', None)
    if threshold:
        return threshold.to_dict()
    return {
        'small_limit': DEFAULT_THRESHOLDS['small_limit'],
        'notify_limit': DEFAULT_THRESHOLDS['notify_limit'],
        'approve_limit': DEFAULT_THRESHOLDS['approve_limit'],
    }


def member_nicknames(family) -> dict:
    """{user_id: nickname}"""
    return {
        str(m.user_id): (m.nickname or '')
        for m in family.members.all()
    }
