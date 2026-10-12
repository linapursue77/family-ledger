# -*- coding: utf-8 -*-
from django.contrib import admin

from apps.accounts.models import (
    Account, AccountSnapshot, BalanceAdjustLog, PrincipalAdjustLog,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'family', 'user', 'type', 'book_type',
                    'balance_cents', 'is_count_total', 'is_invest', 'principal_cents')
    list_filter = ('type', 'book_type', 'is_count_total', 'is_invest')
    search_fields = ('name', 'bank_name')


@admin.register(AccountSnapshot)
class AccountSnapshotAdmin(admin.ModelAdmin):
    list_display = ('account', 'ym', 'balance_cents', 'principal_cents', 'created_at')
    list_filter = ('ym',)


@admin.register(BalanceAdjustLog)
class BalanceAdjustLogAdmin(admin.ModelAdmin):
    list_display = ('account', 'operator', 'before_cents', 'after_cents', 'reason', 'created_at')


@admin.register(PrincipalAdjustLog)
class PrincipalAdjustLogAdmin(admin.ModelAdmin):
    list_display = ('account', 'operator', 'before_cents', 'after_cents', 'reason', 'created_at')
