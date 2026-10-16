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


class RecurringRuleSerializer(serializers.Serializer):
    """周期记账规则入参。金额以「元」提交，与记账接口口径一致。"""

    name = serializers.CharField(max_length=50)
    type = serializers.ChoiceField(choices=['expense', 'income'], default='expense')
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    account = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    merchant = serializers.CharField(required=False, allow_blank=True, default='')
    frequency = serializers.ChoiceField(choices=['daily', 'weekly', 'monthly'], default='monthly')
    interval = serializers.IntegerField(required=False, default=1, min_value=1, max_value=99)
    weekday = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=6)
    day_of_month = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=31)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    is_private = serializers.BooleanField(required=False, default=False)

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('规则名称不能为空')
        return value

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('金额必须大于 0')
        return value

    def validate(self, attrs):
        # 频率对应的定位字段必须给齐，否则排期算不出确定日期。
        #
        # ★ 坑：frequency/interval 带了 default，DRF 会把默认值塞进 validated_data，
        #   所以 attrs.get('frequency') 在 PATCH 只改开关时也会是 'monthly'，
        #   直接用它会误报「每月规则需要指定几号」。必须回看 initial_data
        #   判断「本次是否真的提交了 frequency」。
        submitted = self.initial_data if isinstance(self.initial_data, dict) else {}
        # 创建时始终校验（不给定位字段就排不出日期）；PATCH 只在改频率时校验。
        need_check = ('frequency' in submitted) or not self.partial
        freq = attrs.get('frequency') if need_check else None

        if freq == 'weekly' and attrs.get('weekday') is None:
            raise serializers.ValidationError({'weekday': '每周规则需要指定周几'})
        if freq == 'monthly' and attrs.get('day_of_month') is None:
            raise serializers.ValidationError({'day_of_month': '每月规则需要指定几号'})
        start = attrs.get('start_date')
        end = attrs.get('end_date')
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': '结束日期不能早于开始日期'})
        return attrs
