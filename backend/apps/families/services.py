# -*- coding: utf-8 -*-
"""家庭上下文服务：所有业务视图的公共入口。

★ 铁律：family_id 只从服务端成员关系解析，绝不接受前端传参。
"""
from django.db import transaction
from django.utils import timezone

from domain.threshold import DEFAULT_THRESHOLDS
from domain.visibility import ViewerCtx

from apps.families.models import DEFAULT_PERMISSIONS, FamilyMember, Invitation

# 新成员账本按空缺顺位分配；三个账本都用完后并入「共同账本」，靠归属人区分
BOOK_FALLBACK = (FamilyMember.BOOK_WIFE, FamilyMember.BOOK_HUSBAND, FamilyMember.BOOK_SHARED)


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


def _display_name(user) -> str:
    return getattr(user, 'nickname', '') or getattr(user, 'username', '') or '主账号'


def get_invitation(token: str) -> Invitation:
    """按 token 取邀请并校验可用性（不存在 / 已用 / 已撤销 / 已过期）。"""
    from apps.core.response import BusinessError

    inv = (Invitation.objects.filter(token_hash=(token or '').strip())
           .select_related('family', 'family__owner').first())
    if not inv:
        raise BusinessError('邀请码无效，请让主账号重新生成', code=4004)
    if inv.status == Invitation.STATUS_ACCEPTED:
        raise BusinessError('该邀请已被使用')
    if inv.status == Invitation.STATUS_REVOKED:
        raise BusinessError('该邀请已被撤销')
    if inv.expires_at <= timezone.now():
        if inv.status != Invitation.STATUS_EXPIRED:
            inv.status = Invitation.STATUS_EXPIRED
            inv.save(update_fields=['status'])
        raise BusinessError('邀请已过期，请让主账号重新生成')
    return inv


def _is_empty_self_family(member: FamilyMember) -> bool:
    """判断「自己一个人、且没有任何数据」的空家庭。

    注册接口会无条件给新用户建家庭，被邀请人走「注册」而非「登录」时
    就会变成自己家庭的主账号，于是接受邀请被拦。这种情况下的家庭是误建的：
    只有本人一个成员、没有账单、没有账户，解散它不会丢任何数据。
    """
    from apps.accounts.models import Account
    from apps.ledger.models import Transaction

    if member.role != FamilyMember.ROLE_OWNER:
        return False
    family = member.family
    if family.members.count() != 1:
        return False
    if Account.objects.filter(family=family).exists():
        return False
    if Transaction.objects.filter(family=family).exists():
        return False
    return True


def join_family_by_invitation(user, token: str, nickname: str = '') -> dict:
    """用邀请码把 user 加入家庭（注册与「接受邀请」共用同一套逻辑）。

    - 账本按空缺顺位分配：主账号占「账本一」，第二人拿「账本二」
    - 权限取邀请里的预设值
    - 若 user 已有「自己一个人的空家庭」，自动解散后加入（修复误注册）
    - 若 user 已在有数据的家庭里，明确报错而不是悄悄换家庭
    """
    from apps.core.response import BusinessError
    from apps.membership.services import member_limit

    inv = get_invitation(token)
    family = inv.family

    existing = FamilyMember.objects.filter(user=user).select_related('family').first()
    if existing:
        if str(existing.family_id) == str(family.id):
            raise BusinessError('你已经是该家庭的成员了')
        if not _is_empty_self_family(existing):
            raise BusinessError('你已经在一个家庭里了，如需换家庭请先让主账号移除你')
        # 误注册出来的空家庭：连同阈值等附属配置一起清掉，不留孤儿数据
        empty_family = existing.family
        existing.delete()
        empty_family.delete()

    # 上限按家庭主账号的会员档算（VIP 可扩到 10 人）
    limit = member_limit(family.owner)
    if family.members.count() >= limit:
        raise BusinessError(f'该家庭已满 {limit} 位成员，请让主账号先移除一位')

    used = set(family.members.values_list('book_type', flat=True))
    book = next((b for b in BOOK_FALLBACK if b not in used), FamilyMember.BOOK_SHARED)
    member = FamilyMember.objects.create(
        family=family,
        user=user,
        role=FamilyMember.ROLE_MEMBER,
        nickname=nickname or inv.nickname or _display_name(user),
        book_type=book,
        permissions={**DEFAULT_PERMISSIONS, **(inv.permissions or {})},
    )
    inv.status = Invitation.STATUS_ACCEPTED
    inv.save(update_fields=['status'])
    return {
        'family_id': str(family.id),
        'family_name': family.name,
        'book_type': book,
        'member': member,
    }
