# -*- coding: utf-8 -*-
from rest_framework import serializers

from apps.loans.models import Loan, LoanRepayment
from apps.loans.services import (
    is_overdue,
    remaining_of,
    repaid_of,
    status_of,
)
from domain.money import yuan


class LoanCreateSerializer(serializers.Serializer):
    """入参金额以「元」提交，服务端转分存储，与记账接口保持一致。"""

    direction = serializers.ChoiceField(
        choices=[(Loan.DIRECTION_LEND, '借出'), (Loan.DIRECTION_BORROW, '借入')])
    party = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    account = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    loan_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default='', max_length=255)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('金额必须大于 0')
        return value

    def validate(self, attrs):
        loan_date, due_date = attrs.get('loan_date'), attrs.get('due_date')
        if loan_date and due_date and due_date < loan_date:
            raise serializers.ValidationError('约定还款日不能早于发生日期')
        return attrs


class RepaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    account = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    repay_date = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default='', max_length=255)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('还款金额必须大于 0')
        return value


class RepaymentSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    operator_name = serializers.SerializerMethodField()

    class Meta:
        model = LoanRepayment
        fields = ['id', 'amount_cents', 'amount', 'repay_date', 'note',
                  'account', 'account_name', 'operator_name', 'created_at']

    def get_amount(self, obj):
        return yuan(obj.amount_cents)

    def get_account_name(self, obj):
        return obj.account.name if obj.account else ''

    def get_operator_name(self, obj):
        return obj.operator.display_name if obj.operator else ''


class LoanSerializer(serializers.ModelSerializer):
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    amount = serializers.SerializerMethodField()
    repaid_cents = serializers.SerializerMethodField()
    repaid = serializers.SerializerMethodField()
    remaining_cents = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    created_by = serializers.CharField(source='user_id', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    repayments = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = ['id', 'direction', 'direction_display', 'party', 'amount_cents', 'amount',
                  'repaid_cents', 'repaid', 'remaining_cents', 'remaining',
                  'status', 'status_display', 'overdue',
                  'loan_date', 'due_date', 'note',
                  'account', 'account_name', 'created_by', 'created_by_name',
                  'repayments', 'created_at']

    def get_amount(self, obj):
        return yuan(obj.amount_cents)

    def get_repaid_cents(self, obj):
        return repaid_of(obj)

    def get_repaid(self, obj):
        return yuan(repaid_of(obj))

    def get_remaining_cents(self, obj):
        return remaining_of(obj)

    def get_remaining(self, obj):
        return yuan(remaining_of(obj))

    def get_status(self, obj):
        return status_of(obj)

    def get_status_display(self, obj):
        return Loan.STATUS_LABELS[status_of(obj)]

    def get_overdue(self, obj):
        return is_overdue(obj)

    def get_account_name(self, obj):
        return obj.account.name if obj.account else ''

    def get_created_by_name(self, obj):
        return obj.user.display_name if obj.user else ''

    def get_repayments(self, obj):
        return RepaymentSerializer(obj.repayments.all(), many=True).data
