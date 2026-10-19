# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.accounts.models import Account


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    balance_cents = serializers.IntegerField(read_only=True)
    principal = serializers.SerializerMethodField()
    profit = serializers.SerializerMethodField()
    profit_cents = serializers.SerializerMethodField()
    profit_rate = serializers.SerializerMethodField()
    # ★ 账户是否属于当前登录用户。记账页要按「只记我名下的账户」过滤，
    #   但出于隐私不暴露 user_id，只回一个布尔值，前端据此筛选即可。
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ['id', 'name', 'icon', 'type', 'card_type', 'book_type', 'balance',
                  'balance_cents', 'last_balance_cents', 'bank_name', 'account_no',
                  'is_count_total', 'is_invest', 'principal_cents', 'principal',
                  'profit_cents', 'profit', 'profit_rate', 'is_mine',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_is_mine(self, obj) -> bool:
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if not viewer or not getattr(viewer, 'is_authenticated', False):
            return False
        return str(obj.user_id) == str(viewer.id)

    def get_balance(self, obj) -> float:
        return round(obj.balance_cents / 100, 2)

    def get_principal(self, obj) -> float:
        return round(int(obj.principal_cents or 0) / 100, 2)

    def get_profit_cents(self, obj) -> int:
        return obj.profit_cents

    def get_profit(self, obj) -> float:
        return round(obj.profit_cents / 100, 2)

    def get_profit_rate(self, obj):
        """收益率 = 收益 / 本金，本金为 0 时无意义，返回 None。"""
        principal = int(obj.principal_cents or 0)
        if principal <= 0:
            return None
        return round(obj.profit_cents / principal * 100, 2)


class AccountCreateSerializer(serializers.ModelSerializer):
    """新增/编辑账户：family / user 由服务端填充。"""

    balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                       default=0, write_only=True)
    # 本金：不填时默认等于初始余额（收益从 0 起算），避免新建投资账户凭空多出一笔收益
    principal = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                         write_only=True)

    class Meta:
        model = Account
        fields = ['id', 'name', 'icon', 'type', 'card_type', 'book_type', 'balance',
                  'bank_name', 'account_no', 'is_count_total',
                  'is_invest', 'principal']
        read_only_fields = ['id']

    def create(self, validated_data):
        from domain.money import to_cents
        balance = validated_data.pop('balance', 0)
        principal = validated_data.pop('principal', None)
        validated_data['balance_cents'] = to_cents(balance)
        validated_data['last_balance_cents'] = validated_data['balance_cents']
        if not validated_data.get('is_invest'):
            validated_data['principal_cents'] = 0
        else:
            validated_data['principal_cents'] = (validated_data['balance_cents']
                                                 if principal is None else to_cents(principal))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        from domain.money import to_cents
        balance = validated_data.pop('balance', None)
        principal = validated_data.pop('principal', None)
        if balance is not None:
            validated_data['balance_cents'] = to_cents(balance)
        if principal is not None:
            validated_data['principal_cents'] = to_cents(principal)
        is_invest = validated_data.get('is_invest', instance.is_invest)
        if not is_invest:
            validated_data['principal_cents'] = 0
        elif 'principal_cents' not in validated_data and not instance.principal_cents:
            # 首次开启收益管理：本金未填时以现值起算，收益从 0 开始
            validated_data['principal_cents'] = validated_data.get('balance_cents',
                                                                   instance.balance_cents)
        return super().update(instance, validated_data)


class BalanceAdjustSerializer(serializers.Serializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=200)


class PrincipalAdjustSerializer(serializers.Serializer):
    """本金调整（资产盘点 / 加仓 / 减仓）。"""

    principal = serializers.DecimalField(max_digits=12, decimal_places=2)
    # set = 直接设为该值（盘点）；add = 在现有本金上追加（定投加仓）
    mode = serializers.ChoiceField(choices=['set', 'add'], required=False, default='set')
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
