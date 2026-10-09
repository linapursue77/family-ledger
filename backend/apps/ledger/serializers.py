# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.ledger.models import Category, Transaction


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'kind', 'name', 'icon', 'color', 'keywords', 'is_system', 'sort']


class CategoryCreateSerializer(serializers.Serializer):
    """新增自定义分类的入参（id/sort/is_system 由服务端生成）。"""

    name = serializers.CharField(max_length=20)
    kind = serializers.ChoiceField(choices=Category.KIND_CHOICES)
    icon = serializers.CharField(max_length=16, required=False, allow_blank=True)
    color = serializers.CharField(max_length=16, required=False, allow_blank=True)

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        name = attrs.get('name') or ''
        if not name:
            # CharField 默认只挡全空白，strip 后为空要单独拦
            raise serializers.ValidationError({'name': '分类名称不能为空'})
        if Category.objects.filter(kind=attrs['kind'], name=name).exists():
            raise serializers.ValidationError({'name': f'已存在同名分类「{name}」'})
        return attrs


class TransactionCreateSerializer(serializers.Serializer):
    """记账入参。金额以「元」提交，服务端转成分存储。"""

    type = serializers.ChoiceField(choices=['expense', 'income', 'transfer'], default='expense')
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    account = serializers.CharField(required=False, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    merchant = serializers.CharField(required=False, allow_blank=True, default='')
    description = serializers.CharField(required=False, allow_blank=True, default='')
    transaction_date = serializers.DateTimeField(required=False)
    is_private = serializers.BooleanField(required=False, default=False)
    is_hidden = serializers.BooleanField(required=False, default=False)
    source = serializers.ChoiceField(choices=['wechat', 'alipay', 'manual', 'voice'],
                                     required=False, default='manual')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('金额必须大于 0')
        return value
