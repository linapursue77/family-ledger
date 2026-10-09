# -*- coding: utf-8 -*-
from rest_framework.permissions import BasePermission

from apps.families.services import get_member


class IsFamilyOwner(BasePermission):
    """仅主账号可操作（转让身份、改成员账本）。"""

    message = '仅家庭主账号可执行该操作'

    def has_permission(self, request, view):
        member = get_member(request.user)
        return bool(member and member.role == 'owner')


class IsFamilyMember(BasePermission):
    """已加入家庭。"""

    message = '尚未加入家庭'

    def has_permission(self, request, view):
        return get_member(request.user) is not None


class IsFamilyManager(BasePermission):
    """家庭设置权：主账号，或被授予 settings_level=full 的子账号。

    覆盖邀请、撤销邀请、改子账号权限、移除成员、改协商阈值。
    转让主账号仍只认 IsFamilyOwner —— 身份交接必须本人点头。
    """

    message = '仅主账号或被授权管理家庭设置的成员可执行该操作'

    def has_permission(self, request, view):
        member = get_member(request.user)
        if not member:
            return False
        if member.role == 'owner':
            return True
        return member.effective_permissions.get('settings_level') == 'full'
