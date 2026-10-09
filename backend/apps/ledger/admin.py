# -*- coding: utf-8 -*-
from django.contrib import admin

from apps.ledger.models import Category, ImportTask, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'kind', 'name', 'icon', 'color', 'is_system', 'sort')
    list_filter = ('kind', 'is_system')
    search_fields = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'family', 'user', 'type', 'amount_cents', 'category',
                    'merchant', 'is_private', 'transaction_date')
    list_filter = ('type', 'source', 'is_private')
    search_fields = ('merchant', 'description')
    date_hierarchy = 'transaction_date'


@admin.register(ImportTask)
class ImportTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'family', 'platform', 'status', 'total_count', 'new_count',
                    'duplicate_count', 'failed_count', 'created_at')
    list_filter = ('platform', 'status')
