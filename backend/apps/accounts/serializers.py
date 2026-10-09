# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.accounts.models import Account


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    balance_cents = serializers.IntegerField(read_only=True)

    class Meta:
        model = Account
        fields = ['id', 'name', 'icon', 'type', 'card_type', 'book_type', 'balance',
                  'balance_cents', 'last_balance_cents', 'bank_name', 'account_no',
                  'is_count_total', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_balance(self, obj) -> float:
        return round(obj.balance_cents / 100, 2)


class AccountCreateSerializer(serializers.ModelSerializer):
    """新增账户：family / user 由服务端填充。"""

    balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                       default=0, write_only=True)

    class Meta:
        model = Account
        fields = ['id', 'name', 'icon', 'type', 'card_type', 'book_type', 'balance',
                  'bank_name', 'account_no', 'is_count_total']
        read_only_fields = ['id']

    def create(self, validated_data):
        from domain.money import to_cents
        balance = validated_data.pop('balance', 0)
        validated_data['balance_cents'] = to_cents(balance)
        validated_data['last_balance_cents'] = validated_data['balance_cents']
        return super().create(validated_data)


class BalanceAdjustSerializer(serializers.Serializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=200)
