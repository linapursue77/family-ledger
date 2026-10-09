# -*- coding: utf-8 -*-
"""借钱来往接口。

台账在家庭内共享：夫妻都能看到谁欠谁多少钱，这本身就是「透明」的一部分，
所以这里不做私密裁剪；真正涉及资金流向的只有「关联账户」，它沿用账户可见性规则。
"""
from django.db.models import F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.response import BusinessError, api_response
from apps.families.permissions import IsFamilyMember
from apps.families.services import require_member
from apps.loans import services
from apps.loans.models import Loan, LoanRepayment
from apps.loans.serializers import (
    LoanCreateSerializer,
    LoanSerializer,
    RepaymentCreateSerializer,
    RepaymentSerializer,
)
from domain.money import to_cents


def _loan_qs(family):
    """带「已还」注解与还款预取，避免列表里逐条查。"""
    return (Loan.objects
            .filter(family=family)
            .select_related('account', 'user')
            .prefetch_related(Prefetch(
                'repayments',
                queryset=LoanRepayment.objects.select_related('account', 'operator')))
            .annotate(repaid_cents=Coalesce(Sum('repayments__amount_cents'), Value(0))))


class LoanListView(APIView):
    """GET  /loans/?direction=lend&status=pending&q=张三      列表 + 总览
       POST /loans/                                           记一笔借出/借入
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        qs = _loan_qs(member.family)
        params = request.query_params

        direction = (params.get('direction') or '').strip()
        if direction in (Loan.DIRECTION_LEND, Loan.DIRECTION_BORROW):
            qs = qs.filter(direction=direction)
        keyword = (params.get('q') or '').strip()
        if keyword:
            qs = qs.filter(party__icontains=keyword)

        state = (params.get('status') or '').strip()
        if state == Loan.STATUS_PENDING:
            qs = qs.filter(repaid_cents=0)
        elif state == Loan.STATUS_PARTIAL:
            qs = qs.filter(repaid_cents__gt=0, repaid_cents__lt=F('amount_cents'))
        elif state == Loan.STATUS_SETTLED:
            qs = qs.filter(repaid_cents__gte=F('amount_cents'))

        items = list(qs)
        if state == 'overdue':
            items = [loan for loan in items if services.is_overdue(loan)]

        return api_response({
            'items': LoanSerializer(items, many=True).data,
            'summary': services.summarize(member.family),
        })

    def post(self, request):
        member = require_member(request.user)
        ser = LoanCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        account = services.resolve_account(member, request.user, data.get('account') or None)
        loan = services.create_loan(
            member,
            request.user,
            direction=data['direction'],
            party=data['party'].strip(),
            amount_cents=to_cents(data['amount']),
            account=account,
            loan_date=data.get('loan_date'),
            due_date=data.get('due_date'),
            note=(data.get('note') or '').strip(),
        )
        verb = '借出' if loan.direction == Loan.DIRECTION_LEND else '借入'
        return api_response(LoanSerializer(loan).data,
                            message=f'已记录{verb} ¥{loan.amount_cents / 100:.2f}')


class LoanDetailView(APIView):
    """GET    /loans/{id}/        详情（含还款明细）
       PATCH  /loans/{id}/        只能改对方、备注、约定还款日
       DELETE /loans/{id}/        已还过款的需先撤销还款
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    @staticmethod
    def _loan(request, pk):
        member = require_member(request.user)
        loan = _loan_qs(member.family).filter(id=pk).first()
        if not loan:
            raise BusinessError('记录不存在', code=4004)
        return loan

    def get(self, request, pk):
        return api_response(LoanSerializer(self._loan(request, pk)).data)

    def patch(self, request, pk):
        loan = self._loan(request, pk)
        data = request.data or {}
        fields = []
        if 'party' in data:
            party = str(data.get('party') or '').strip()
            if not party:
                raise BusinessError('对方名称不能为空', code=4001)
            loan.party = party[:50]
            fields.append('party')
        if 'note' in data:
            loan.note = str(data.get('note') or '').strip()[:255]
            fields.append('note')
        if 'due_date' in data:
            raw = str(data.get('due_date') or '').strip()
            loan.due_date = raw or None
            fields.append('due_date')
        if not fields:
            raise BusinessError('借款金额与方向不可修改，可改的只有对方、备注、约定还款日',
                                code=4001)
        loan.save(update_fields=fields + ['updated_at'])
        return api_response(LoanSerializer(loan).data, message='已保存')

    def delete(self, request, pk):
        loan = self._loan(request, pk)
        services.remove_loan(loan)
        return api_response({'id': pk}, message='已删除，账户余额同步回退')


class LoanRepaymentView(APIView):
    """POST /loans/{id}/repayments/ —— 记一笔还款（可分多次还）。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def post(self, request, pk):
        member = require_member(request.user)
        loan = _loan_qs(member.family).filter(id=pk).first()
        if not loan:
            raise BusinessError('记录不存在', code=4004)

        ser = RepaymentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        account = services.resolve_account(member, request.user, data.get('account') or None)
        repayment = services.add_repayment(
            loan,
            request.user,
            amount_cents=to_cents(data['amount']),
            account=account,
            repay_date=data.get('repay_date'),
            note=(data.get('note') or '').strip(),
        )
        fresh = _loan_qs(member.family).filter(id=loan.id).first()
        return api_response({
            'repayment': RepaymentSerializer(repayment).data,
            'loan': LoanSerializer(fresh).data,
        }, message=f'已还 ¥{repayment.amount_cents / 100:.2f}')


class LoanRepaymentDetailView(APIView):
    """DELETE /loans/repayments/{id}/ —— 撤销一笔还款（余额同时回退）。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def delete(self, request, pk):
        member = require_member(request.user)
        repayment = (LoanRepayment.objects
                     .filter(id=pk, loan__family=member.family)
                     .select_related('loan', 'account')
                     .first())
        if not repayment:
            raise BusinessError('还款记录不存在', code=4004)
        services.remove_repayment(repayment)
        return api_response({'id': pk}, message='还款已撤销')
