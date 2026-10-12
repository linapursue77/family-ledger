# -*- coding: utf-8 -*-
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('id', 'username', 'nickname', 'phone', 'is_staff', 'date_joined')
    search_fields = ('username', 'phone', 'nickname')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('钱来钱往记账', {'fields': ('nickname', 'avatar_url', 'phone', 'openid',
                                   'privacy_limit_cents')}),
    )
