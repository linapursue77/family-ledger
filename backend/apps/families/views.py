# -*- coding: utf-8 -*-
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.response import BusinessError, api_response
from apps.families.models import DEFAULT_PERMISSIONS, FamilyMember, Invitation, Threshold
from apps.families.permissions import IsFamilyManager, IsFamilyMember, IsFamilyOwner
from apps.families.serializers import (
    InvitationCreateSerializer,
    MemberPermissionSerializer,
    MemberSerializer,
    ThresholdSerializer,
)
from apps.families.services import build_viewer_ctx, require_member

# 一个家庭最多 5 位成员（1 主账号 + 4 子账号）：夫妻之外还能拉父母、成年子女
MAX_FAMILY_MEMBERS = 5
# 新成员账本按空缺顺位分配；三个账本都用完后并入「共同账本」，靠归属人区分
BOOK_FALLBACK = (FamilyMember.BOOK_WIFE, FamilyMember.BOOK_HUSBAND, FamilyMember.BOOK_SHARED)
BOOK_CODES = {FamilyMember.BOOK_HUSBAND, FamilyMember.BOOK_WIFE, FamilyMember.BOOK_SHARED}


def _display_name(user) -> str:
    return getattr(user, 'nickname', '') or getattr(user, 'username', '') or '主账号'


def _status_of(inv: Invitation) -> str:
    """待接受但已超时的，展示层直接算作已过期。"""
    if inv.status == Invitation.STATUS_PENDING and inv.expires_at <= timezone.now():
        return Invitation.STATUS_EXPIRED
    return inv.status


def _get_invite(token: str) -> Invitation:
    """按 token 取邀请并校验可用性。"""
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


class FamilyMeView(APIView):
    """当前家庭与成员列表。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        family = member.family
        return api_response({
            'id': family.id,
            'name': family.name,
            'owner_id': family.owner_id,
            'created_at': family.created_at,
            'members': MemberSerializer(family.members.all(), many=True).data,
            'my_role': member.role,
            'my_id': member.id,
            'my_book_type': member.book_type,
            'my_permissions': member.effective_permissions,
            'member_limit': MAX_FAMILY_MEMBERS,
            'book_labels': family.book_labels or {},
        })


class InvitationCreateView(APIView):
    """主账号签发 / 查看邀请（MVP：token 即明文，接入短信前不做哈希）。

    GET  /families/invitations/   邀请列表（不含 token）
    POST /families/invitations/   生成邀请，token 只在响应里出现一次
    """

    permission_classes = [IsAuthenticated, IsFamilyManager]

    def get(self, request):
        member = require_member(request.user)
        items = []
        for inv in Invitation.objects.filter(family=member.family).order_by('-created_at')[:20]:
            items.append({
                'id': inv.id,
                'nickname': inv.nickname,
                'contact': inv.contact,
                'status': _status_of(inv),
                'permissions': {**DEFAULT_PERMISSIONS, **(inv.permissions or {})},
                'created_at': inv.created_at,
                'expires_at': inv.expires_at,
            })
        return api_response({
            'items': items,
            'member_limit': MAX_FAMILY_MEMBERS,
            'member_count': member.family.members.count(),
        })

    def post(self, request):
        ser = InvitationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        member = require_member(request.user)

        if member.family.members.count() >= MAX_FAMILY_MEMBERS:
            raise BusinessError(
                f'家庭已有 {MAX_FAMILY_MEMBERS} 位成员，请先在成员列表移除一位再邀请')

        invitation, token = Invitation.issue(
            family=member.family,
            nickname=ser.validated_data['nickname'],
            contact=ser.validated_data.get('contact', ''),
            permissions=ser.validated_data.get('permissions') or {},
            days=7,
        )
        return api_response({
            'invitation_id': invitation.id,
            'token': token,
            'expires_at': invitation.expires_at,
        }, message='邀请已生成', http_status=status.HTTP_201_CREATED)


class MemberPermissionView(APIView):
    """修改子账号权限（即时生效）：主账号，或被授予设置权的成员。

    ★ 防自提权：非主账号不能改自己的权限，只能互相改或由主账号改。
    """

    permission_classes = [IsAuthenticated, IsFamilyManager]

    def patch(self, request, member_id):
        member = require_member(request.user)
        target = FamilyMember.objects.filter(id=member_id, family=member.family).first()
        if not target:
            raise BusinessError('成员不存在', code=4004)
        if target.role == FamilyMember.ROLE_OWNER:
            raise BusinessError('主账号权限不可修改')
        if str(target.id) == str(member.id) and member.role != FamilyMember.ROLE_OWNER:
            raise BusinessError('不能修改自己的权限，请联系主账号调整', code=4003)

        ser = MemberPermissionSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        merged = dict(target.permissions or {})
        merged.update(ser.validated_data)
        target.permissions = merged
        target.save(update_fields=['permissions'])
        return api_response(MemberSerializer(target).data, message='权限已更新')


class InvitationRevokeView(APIView):
    """POST /families/invitations/{id}/revoke/ —— 撤销尚未接受的邀请。"""
    permission_classes = [IsAuthenticated, IsFamilyManager]

    def post(self, request, invitation_id):
        member = require_member(request.user)
        inv = Invitation.objects.filter(id=invitation_id, family=member.family).first()
        if not inv:
            raise BusinessError('邀请不存在', code=4004)
        if inv.status == Invitation.STATUS_ACCEPTED:
            raise BusinessError('该邀请已被接受，请直接移除对应成员')
        inv.status = Invitation.STATUS_REVOKED
        inv.save(update_fields=['status'])
        return api_response({'id': inv.id, 'status': inv.status}, message='邀请已撤销')


class InvitationPreviewView(APIView):
    """GET /families/invitations/preview/?token= —— 接受前先看清将加入哪个家庭、拿到哪些权限。

    ★ 只要求登录：被邀请人此刻还不是本家庭成员，不能挂 IsFamilyMember。
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inv = _get_invite(request.query_params.get('token'))
        owner_member = inv.family.members.filter(role=FamilyMember.ROLE_OWNER).first()
        inviter = (owner_member.nickname if owner_member and owner_member.nickname
                   else _display_name(inv.family.owner))
        return api_response({
            'family_name': inv.family.name,
            'inviter': inviter,
            'nickname': inv.nickname,
            'permissions': {**DEFAULT_PERMISSIONS, **(inv.permissions or {})},
            'expires_at': inv.expires_at,
            'member_count': inv.family.members.count(),
            'member_limit': MAX_FAMILY_MEMBERS,
        })


class InvitationAcceptView(APIView):
    """POST /families/invitations/accept/ {token} —— 用邀请码正式加入家庭。

    账本按空缺顺位分配（新成员默认拿「老婆账本」，被占则顺位），权限取邀请里的预设值。
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        inv = _get_invite(str((request.data or {}).get('token') or ''))
        user = request.user
        if FamilyMember.objects.filter(user=user).exists():
            raise BusinessError('你已经在一个家庭里了，如需换家庭请先让主账号移除你')
        family = inv.family
        if family.members.count() >= MAX_FAMILY_MEMBERS:
            raise BusinessError(f'该家庭已满 {MAX_FAMILY_MEMBERS} 位成员，请让主账号先移除一位')

        used = set(family.members.values_list('book_type', flat=True))
        book = next((b for b in BOOK_FALLBACK if b not in used), FamilyMember.BOOK_SHARED)
        member = FamilyMember.objects.create(
            family=family,
            user=user,
            role=FamilyMember.ROLE_MEMBER,
            nickname=inv.nickname or _display_name(user),
            book_type=book,
            permissions={**DEFAULT_PERMISSIONS, **(inv.permissions or {})},
        )
        inv.status = Invitation.STATUS_ACCEPTED
        inv.save(update_fields=['status'])
        return api_response({
            'family_name': family.name,
            'book_type': book,
            'member': MemberSerializer(member).data,
        }, message='已加入「%s」' % family.name)


class MemberDetailView(APIView):
    """成员维护。

    PATCH  /families/members/{id}/   改称呼 / 所属账本（本人可改自己称呼，账本仅主账号）
    DELETE /families/members/{id}/   移除成员；历史账单仍留在家庭里
    """
    permission_classes = [IsAuthenticated, IsFamilyMember]

    @staticmethod
    def _target(request, member_id):
        me = require_member(request.user)
        target = (FamilyMember.objects.filter(id=member_id, family=me.family)
                  .select_related('user').first())
        if not target:
            raise BusinessError('成员不存在', code=4004)
        return me, target

    def patch(self, request, member_id):
        me, target = self._target(request, member_id)
        data = request.data or {}
        fields = []
        if 'nickname' in data:
            if target.id != me.id and me.role != FamilyMember.ROLE_OWNER:
                raise BusinessError('只能修改自己的称呼', code=4003)
            target.nickname = str(data.get('nickname') or '').strip()[:50]
            fields.append('nickname')
        if 'book_type' in data:
            if me.role != FamilyMember.ROLE_OWNER:
                raise BusinessError('仅主账号可调整成员账本', code=4003)
            book = str(data.get('book_type') or '').strip()
            if book not in BOOK_CODES:
                raise BusinessError('账本类型不合法', code=4001)
            target.book_type = book
            fields.append('book_type')
        if not fields:
            raise BusinessError('没有需要修改的内容', code=4001)
        target.save(update_fields=fields)
        return api_response(MemberSerializer(target).data, message='已保存')

    def delete(self, request, member_id):
        me, target = self._target(request, member_id)
        if (me.role != FamilyMember.ROLE_OWNER
                and me.effective_permissions.get('settings_level') != 'full'):
            raise BusinessError('仅主账号或被授权的成员可移除成员', code=4003)
        if target.role == FamilyMember.ROLE_OWNER:
            raise BusinessError('主账号不能被移除')
        if str(target.id) == str(me.id):
            raise BusinessError('不能移除自己', code=4003)
        target.delete()
        return api_response({'id': member_id}, message='成员已移除，其历史账单仍保留在家庭账本中')


class TransferOwnerView(APIView):
    """POST /families/members/{id}/transfer-owner/ —— 转让主账号。

    夫妻场景里真正管钱的一方应当是主账号，所以允许现任主账号把身份交给对方。
    转让同时把「家庭归属」和「成员角色」一起改，保证 family.owner 与 role=owner 永远一致。
    """

    permission_classes = [IsAuthenticated, IsFamilyOwner]

    def post(self, request, member_id):
        me = require_member(request.user)
        if str(me.id) == str(member_id):
            raise BusinessError('你已经是主账号了', code=4001)
        target = (FamilyMember.objects.filter(id=member_id, family=me.family)
                  .select_related('user').first())
        if not target:
            raise BusinessError('成员不存在', code=4004)

        family = me.family
        target_name = target.nickname or _display_name(target.user)
        with transaction.atomic():
            # 新主账号：role=owner 本身代表全部权限，无需再存 permissions
            target.role = FamilyMember.ROLE_OWNER
            target.permissions = {}
            target.save(update_fields=['role', 'permissions'])

            # 旧主账号降级为普通成员：仍可看账、可记账，但交出家庭设置权
            me.role = FamilyMember.ROLE_MEMBER
            me.permissions = dict(DEFAULT_PERMISSIONS)
            me.save(update_fields=['role', 'permissions'])

            family.owner = target.user
            family.save(update_fields=['owner'])

        return api_response({
            'family_id': str(family.id),
            'owner_id': str(target.user_id),
            'members': MemberSerializer(family.members.all(), many=True).data,
        }, message=f'主账号已转让给「{target_name}」')


class ThresholdView(APIView):
    """协商阈值（PRD 4.5.2）。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        threshold, _ = Threshold.objects.get_or_create(family=member.family)
        return api_response(threshold.to_dict())

    def put(self, request):
        if not IsFamilyManager().has_permission(request, self):
            raise BusinessError('仅主账号或被授权的成员可修改协商阈值', code=4003)
        member = require_member(request.user)
        ser = ThresholdSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        threshold, _ = Threshold.objects.get_or_create(family=member.family)
        threshold.small_limit_cents = data['small_limit']
        threshold.notify_limit_cents = data['notify_limit']
        threshold.approve_limit_cents = data['approve_limit']
        threshold.updated_at = timezone.now()
        threshold.save()
        return api_response(threshold.to_dict(), message='阈值已保存')
