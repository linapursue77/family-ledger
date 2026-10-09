# -*- coding: utf-8 -*-
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Account, AccountSnapshot, BalanceAdjustLog
from apps.accounts.serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    BalanceAdjustSerializer,
)
from apps.accounts.services import assert_own_account, visible_accounts
from apps.loans.services import summarize as loan_summary
from apps.core.response import BusinessError, api_response
from apps.families.permissions import IsFamilyMember
from apps.families.services import require_member
from domain.money import yuan


def _recent_months(year: int, month: int, count: int):
    """返回截至 year-month 的近 count 个月，升序，格式 YYYY-MM。"""
    months = []
    for offset in range(count - 1, -1, -1):
        m = month - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f'{y:04d}-{m:02d}')
    return months


# 账本默认名称：与 Account.BOOK_CHOICES 的 label 不同，前端分组标题用这套更贴近口语
BOOK_DEFAULT_LABEL = {
    Account.BOOK_SHARED: '共同账户',
    Account.BOOK_HUSBAND: '老公账户',
    Account.BOOK_WIFE: '老婆账户',
}


def book_labels(family) -> dict:
    """账本名称：家庭自定义优先，缺省回落默认名。"""
    stored = family.book_labels or {}
    return {code: (stored.get(code) or BOOK_DEFAULT_LABEL.get(code, label))
            for code, label in Account.BOOK_CHOICES}


def _account_item(account: Account, labels: dict = None) -> dict:
    labels = labels or BOOK_DEFAULT_LABEL
    change = int(account.balance_cents) - int(account.last_balance_cents or 0)
    return {
        'id': account.id,
        'name': account.name,
        'icon': account.icon,
        'type': account.type,
        'type_display': account.get_type_display(),
        # 可见性：private 仅本人可见，其余视为对方可见（与编辑弹窗一一对应）
        'visibility': 'self' if account.type == Account.TYPE_PRIVATE else 'shared',
        'card_type': account.card_type,
        'card_type_display': account.get_card_type_display(),
        'book_type': account.book_type,
        'book_display': account.get_book_type_display(),
        'book_label': labels.get(account.book_type, ''),
        'bank_name': account.bank_name,
        'account_no': account.account_no,
        'balance_cents': int(account.balance_cents),
        'balance': yuan(account.balance_cents),
        'change_cents': change,
        'change': yuan(change),
    }


class AccountViewSet(viewsets.ModelViewSet):
    """账户管理（PRD 4.1）。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]
    serializer_class = AccountSerializer

    def get_queryset(self):
        member = require_member(self.request.user)
        # 他人「仅本人可见」的账户不进列表，也不进任何聚合
        queryset = visible_accounts(member.family, self.request.user).select_related('user')
        book_type = self.request.query_params.get('book_type')
        if book_type:
            queryset = queryset.filter(book_type=book_type)
        return queryset

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return AccountCreateSerializer
        return AccountSerializer

    def create(self, request, *args, **kwargs):
        member = require_member(request.user)
        ser = AccountCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        account = ser.save(family=member.family, user=request.user)
        return api_response(AccountSerializer(account).data, message='账户已创建',
                            http_status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """仅允许改名称与图标（PRD 4.1.4：类型不可变更），且仅限账户归属人。"""
        account = self.get_object()
        assert_own_account(account, request.user, '修改')
        ser = AccountCreateSerializer(account, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return api_response(AccountSerializer(account).data, message='账户已更新')

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        assert_own_account(account, request.user, '删除')
        if account.balance_cents != 0:
            raise BusinessError('请先转移或清空余额后再删除账户')
        account.delete()
        return api_response(None, message='账户已删除')

    @action(detail=True, methods=['post'], url_path='adjust')
    def adjust_balance(self, request, pk=None):
        """手动调整余额，必须填写说明（PRD 4.1.4）。"""
        account = self.get_object()
        assert_own_account(account, request.user, '调整余额')
        ser = BalanceAdjustSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from domain.money import to_cents
        new_cents = to_cents(ser.validated_data['balance'])

        with transaction.atomic():
            if connection.vendor == 'mysql':
                locked = Account.objects.select_for_update().get(pk=account.pk)
            else:
                locked = account
            before = locked.balance_cents
            locked.balance_cents = new_cents
            locked.save(update_fields=['balance_cents', 'updated_at'])
            BalanceAdjustLog.objects.create(
                account=locked,
                operator=request.user,
                before_cents=before,
                after_cents=new_cents,
                reason=ser.validated_data['reason'],
            )
            AccountSnapshot.objects.update_or_create(
                account=locked,
                ym=timezone.localdate().strftime('%Y-%m'),
                defaults={'balance_cents': new_cents},
            )
        return api_response(AccountSerializer(account).data, message='余额已调整')

    @action(detail=False, methods=['get'], url_path='netvalue')
    def netvalue(self, request):
        """家庭总资产明细与净值曲线：首页「家庭总资产」下钻。"""
        member = require_member(request.user)
        # 与账户列表同一套可见性：他人 private 账户不计入家庭净资产
        accounts = list(visible_accounts(member.family, request.user).select_related('user'))
        counted = [a for a in accounts if a.is_count_total]

        total_cents = sum(int(a.balance_cents) for a in counted)
        last_cents = sum(int(a.last_balance_cents or 0) for a in counted)

        labels = book_labels(member.family)
        groups = []
        for code, _label in Account.BOOK_CHOICES:
            items = [a for a in counted if a.book_type == code]
            sub_cents = sum(int(a.balance_cents) for a in items)
            groups.append({
                'book_type': code,
                'label': labels.get(code, ''),
                'total_cents': sub_cents,
                'total': yuan(sub_cents),
                'accounts': [_account_item(a, labels) for a in items],
            })

        today = timezone.localdate()
        months = _recent_months(today.year, today.month, 12)
        rows = (AccountSnapshot.objects
                .filter(account_id__in=[a.id for a in counted], ym__in=months)
                .values('ym').annotate(total=Sum('balance_cents')))
        by_ym = {row['ym']: int(row['total'] or 0) for row in rows}

        cur_ym = months[-1]
        prev_ym = months[-2] if len(months) > 1 else None
        trend = []
        for ym in months:
            if ym == cur_ym:
                value: object = total_cents
            elif ym == prev_ym and ym not in by_ym:
                value = last_cents
            else:
                value = by_ym.get(ym)
            trend.append({
                'ym': ym,
                'assets_cents': value,
                'assets': None if value is None else yuan(value),
            })

        # 净资产口径：账户余额 + 借出未收（应收资产）− 借入未还（负债）
        loans = loan_summary(member.family)
        receivable = int(loans['lend_cents'])
        payable = int(loans['borrow_cents'])
        net_cents = total_cents + receivable - payable

        return api_response({
            'total_assets_cents': net_cents,
            'total_assets': yuan(net_cents),
            'account_assets_cents': total_cents,
            'account_assets': yuan(total_cents),
            'receivable_cents': receivable,
            'receivable': yuan(receivable),
            'payable_cents': payable,
            'payable': yuan(payable),
            'loans': loans,
            'last_assets_cents': last_cents,
            'asset_change_cents': total_cents - last_cents,
            'asset_change': yuan(total_cents - last_cents),
            'account_count': len(counted),
            'groups': groups,
            'excluded_accounts': [_account_item(a, labels)
                                  for a in accounts if not a.is_count_total],
            'book_labels': labels,
            'trend': trend,
        })

    @action(detail=False, methods=['post'], url_path='book-label')
    def rename_book(self, request):
        """修改账本名称（账户管理页分组标题，家庭级共享配置）。"""
        member = require_member(request.user)
        book_type = str(request.data.get('book_type') or '').strip()
        label = str(request.data.get('label') or '').strip()

        if book_type not in {code for code, _ in Account.BOOK_CHOICES}:
            raise BusinessError('账本不存在', code=4004)
        if not label:
            raise BusinessError('账本名称不能为空')
        if len(label) > 20:
            raise BusinessError('账本名称最多 20 个字')

        family = member.family
        labels = dict(family.book_labels or {})
        labels[book_type] = label
        family.book_labels = labels
        family.save(update_fields=['book_labels'])
        return api_response(book_labels(family), message='账本名称已保存')
