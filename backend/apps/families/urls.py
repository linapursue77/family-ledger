# -*- coding: utf-8 -*-
from django.urls import path

from apps.families.views import (
    FamilyMeView,
    InvitationAcceptView,
    InvitationCreateView,
    InvitationPreviewView,
    InvitationRevokeView,
    MemberDetailView,
    MemberPermissionView,
    ThresholdView,
    TransferOwnerView,
)

urlpatterns = [
    path('me/', FamilyMeView.as_view(), name='family-me'),
    # 邀请：签发 + 列表（同一个视图，owner 专用）、预览与接受（被邀请人用）、撤销
    path('invitations/', InvitationCreateView.as_view(), name='family-invite'),
    path('invitations/preview/', InvitationPreviewView.as_view(), name='family-invite-preview'),
    path('invitations/accept/', InvitationAcceptView.as_view(), name='family-invite-accept'),
    path('invitations/<str:invitation_id>/revoke/', InvitationRevokeView.as_view(),
         name='family-invite-revoke'),
    # 成员：改称呼/账本、移除、授权
    path('members/<str:member_id>/', MemberDetailView.as_view(), name='family-member'),
    path('members/<str:member_id>/permissions/', MemberPermissionView.as_view(),
         name='family-member-permission'),
    # 转让主账号：谁管钱谁当主账号
    path('members/<str:member_id>/transfer-owner/', TransferOwnerView.as_view(),
         name='family-member-transfer-owner'),
    path('thresholds/', ThresholdView.as_view(), name='family-threshold'),
]
