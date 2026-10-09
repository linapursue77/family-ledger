# -*- coding: utf-8 -*-
from django.contrib import admin

from apps.families.models import Family, FamilyMember, Invitation, Threshold


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'created_at')
    search_fields = ('name',)


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'family', 'user', 'role', 'nickname', 'book_type', 'joined_at')
    list_filter = ('role', 'book_type')
    search_fields = ('nickname',)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'family', 'nickname', 'status', 'expires_at', 'created_at')
    list_filter = ('status',)


@admin.register(Threshold)
class ThresholdAdmin(admin.ModelAdmin):
    list_display = ('family', 'small_limit_cents', 'notify_limit_cents',
                    'approve_limit_cents', 'updated_at')
