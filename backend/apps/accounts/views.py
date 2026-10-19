# -*- coding: utf-8 -*-
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import (
    Account, AccountSnapshot, BalanceAdjustLog, PrincipalAdjustLog,
)
from apps.accounts.serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    BalanceAdjustSerializer,
    PrincipalAdjustSerializer,
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
    Account.BOOK_HUSBAND: '账本一',
    Account.BOOK_WIFE: '账本二',
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
        'is_invest': bool(account.is_invest),
        'principal_cents': int(account.principal_cents or 0),
        'principal': yuan(account.principal_cents or 0),
        'profit_cents': account.profit_cents,
        'profit': yuan(account.profit_cents),
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

    def get_serializer_context(self):
        # is_mine 依赖请求用户，漏传 context 会一律判成 False
        ctx = super().get_serializer_context()
        ctx.setdefault('request', self.request)
        return ctx

    def create(self, request, *args, **kwargs):
        member = require_member(request.user)
        ser = AccountCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        account = ser.save(family=member.family, user=request.user)
        return api_response(AccountSerializer(account, context={'request': request}).data,
                            message='账户已创建',
                            http_status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """仅允许改名称与图标（PRD 4.1.4：类型不可变更），且仅限账户归属人。"""
        account = self.get_object()
        assert_own_account(account, request.user, '修改')
        ser = AccountCreateSerializer(account, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return api_response(AccountSerializer(account, context={'request': request}).data,
                            message='账户已更新')

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
                defaults={'balance_cents': new_cents,
                          'principal_cents': locked.principal_cents},
            )
        return api_response(AccountSerializer(account, context={'request': request}).data,
                            message='余额已调整')

    @action(detail=True, methods=['post'], url_path='principal')
    def set_principal(self, request, pk=None):
        """设置/追加本金（资产盘点、加仓、减仓）。

        收益 = 现值 − 本金，所以本金是收益口径的地基：
        · set：直接把本金设为该值（盘点时按券商/平台显示的「累计投入」填）
        · add：在现有本金上追加（每月定投加仓时用，避免自己算总额）
        """
        account = self.get_object()
        assert_own_account(account, request.user, '调整本金')
        ser = PrincipalAdjustSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from domain.money import to_cents
        amount = to_cents(ser.validated_data['principal'])
        mode = ser.validated_data.get('mode') or 'set'
        if amount < 0:
            raise BusinessError('本金不能为负数')

        with transaction.atomic():
            if connection.vendor == 'mysql':
                locked = Account.objects.select_for_update().get(pk=account.pk)
            else:
                locked = account
            before = int(locked.principal_cents or 0)
            after = amount if mode == 'set' else before + amount
            after = max(after, 0)
            locked.is_invest = True
            locked.principal_cents = after
            locked.save(update_fields=['is_invest', 'principal_cents', 'updated_at'])
            PrincipalAdjustLog.objects.create(
                account=locked,
                operator=request.user,
                before_cents=before,
                after_cents=after,
                reason=ser.validated_data.get('reason') or '',
            )
            AccountSnapshot.objects.update_or_create(
                account=locked,
                ym=timezone.localdate().strftime('%Y-%m'),
                defaults={'balance_cents': locked.balance_cents,
                          'principal_cents': after},
            )
        return api_response(AccountSerializer(account, context={'request': request}).data,
                            message='本金已追加' if mode == 'add' else '本金已更新')

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

    @action(detail=False, methods=['get'], url_path='returns')
    def returns(self, request):
        """投资收益管理：一年内收益变化 + 今年收益对家庭总资产的影响。

        收益 = 现值(balance) − 本金(principal)，只统计「纳入收益管理」的账户。
        历史月份取自 AccountSnapshot，缺本金记录的月份收益记为 None（不猜数）。
        ?book=husband 只看某个账本的收益；不传则全部账本。净资产始终按家庭全量算。
        """
        member = require_member(request.user)
        accounts = list(visible_accounts(member.family, request.user).select_related('user'))
        counted = [a for a in accounts if a.is_count_total]
        invests_all = [a for a in accounts if a.is_invest]
        labels = book_labels(member.family)

        book = (request.query_params.get('book') or '').strip()
        if book and book not in dict(Account.BOOK_CHOICES):
            raise BusinessError('账本不存在')
        invests = [a for a in invests_all if a.book_type == book] if book else invests_all

        # 可切换的账本：只列有投资账户的，顺带给出各自收益
        book_tabs = []
        for book_type, _display in Account.BOOK_CHOICES:
            same = [a for a in invests_all if a.book_type == book_type]
            if not same:
                continue
            book_tabs.append({
                'book_type': book_type,
                'label': labels.get(book_type, ''),
                'count': len(same),
                'profit_cents': sum(a.profit_cents for a in same),
                'profit': yuan(sum(a.profit_cents for a in same)),
                'value_cents': sum(int(a.balance_cents) for a in same),
                'value': yuan(sum(int(a.balance_cents) for a in same)),
            })

        today = timezone.localdate()
        cur_ym = today.strftime('%Y-%m')
        months = _recent_months(today.year, today.month, 12)
        begin_ym = f'{today.year - 1:04d}-12'
        window = sorted(set(months) | {begin_ym})

        ids = [a.id for a in invests]
        rows = (AccountSnapshot.objects
                .filter(account_id__in=ids, ym__in=window)
                .values('ym')
                .annotate(bal=Sum('balance_cents'), pri=Sum('principal_cents')))
        agg = {r['ym']: (int(r['bal'] or 0), int(r['pri'] or 0)) for r in rows}

        def _point(ym):
            """返回该月的 (现值, 本金)；缺数据或缺本金记录则返回 None。"""
            if ym == cur_ym:
                return (sum(int(a.balance_cents) for a in invests),
                        sum(int(a.principal_cents or 0) for a in invests))
            if ym not in agg:
                return None
            bal, pri = agg[ym]
            # 迁移前的老快照没有本金，此时收益不可计算，宁可留空也不显示假收益
            if pri == 0 and bal != 0:
                return None
            return (bal, pri)

        points = {ym: _point(ym) for ym in window}

        # 年初基准：优先去年 12 月；否则退到「早于当前月」的最近一个有记录的月份。
        # 都没有（今年才启用收益管理）→ 年初收益按 0 计，累计收益即今年收益。
        begin_used = begin_ym if points.get(begin_ym) else ''
        if not begin_used:
            for ym in months[:-1]:
                if points.get(ym):
                    begin_used = ym
                    break

        principal_now = sum(int(a.principal_cents or 0) for a in invests)
        value_now = sum(int(a.balance_cents) for a in invests)
        profit_now = value_now - principal_now

        begin_point = points.get(begin_used) if begin_used else None
        begin_profit = 0 if begin_point is None else begin_point[0] - begin_point[1]
        begin_value = None if begin_point is None else begin_point[0]
        year_profit = profit_now - begin_profit

        trend = []
        prev_profit = None
        for ym in months:
            point = _point(ym)
            if point is None:
                prev_profit = None
                trend.append({
                    'ym': ym,
                    'value_cents': None, 'principal_cents': None, 'profit_cents': None,
                    'month_profit_cents': None,
                    'value': None, 'principal': None, 'profit': None, 'month_profit': None,
                })
                continue
            profit = point[0] - point[1]
            month_profit = None if prev_profit is None else profit - prev_profit
            trend.append({
                'ym': ym,
                'value_cents': point[0], 'principal_cents': point[1],
                'profit_cents': profit, 'month_profit_cents': month_profit,
                'value': yuan(point[0]), 'principal': yuan(point[1]),
                'profit': yuan(profit),
                'month_profit': None if month_profit is None else yuan(month_profit),
            })
            prev_profit = profit

        # 每个账户年初的累计收益：用于拆分「今年哪个账户在赚钱」
        per_account = {}
        if ids:
            for r in (AccountSnapshot.objects
                      .filter(account_id__in=ids, ym__in=window)
                      .values('account_id', 'ym', 'balance_cents', 'principal_cents')):
                bal, pri = int(r['balance_cents'] or 0), int(r['principal_cents'] or 0)
                if pri == 0 and bal != 0:      # 老快照缺本金，该月不参与计算
                    continue
                per_account.setdefault(str(r['account_id']), {})[r['ym']] = bal - pri

        def _account_begin(acc_id) -> int:
            """与总览同一套基准口径，避免账户明细和汇总对不上。"""
            series = per_account.get(acc_id) or {}
            if begin_used and begin_used in series:
                return series[begin_used]
            for ym in months[:-1]:
                if ym in series:
                    return series[ym]
            return 0

        items = []
        for a in sorted(invests, key=lambda x: -x.profit_cents):
            begin = _account_begin(a.id)
            acc_year = a.profit_cents - begin
            items.append({
                'id': a.id,
                'name': a.name,
                'icon': a.icon,
                'card_type': a.card_type,
                'card_type_display': a.get_card_type_display(),
                'book_type': a.book_type,
                'book_label': labels.get(a.book_type, ''),
                'bank_name': a.bank_name,
                'value_cents': int(a.balance_cents),
                'value': yuan(a.balance_cents),
                'principal_cents': int(a.principal_cents or 0),
                'principal': yuan(a.principal_cents or 0),
                'profit_cents': a.profit_cents,
                'profit': yuan(a.profit_cents),
                'profit_rate': (round(a.profit_cents / int(a.principal_cents or 0) * 100, 2)
                                if int(a.principal_cents or 0) > 0 else None),
                'year_profit_cents': acc_year,
                'year_profit': yuan(acc_year),
            })

        total_cents = sum(int(a.balance_cents) for a in counted)
        loans = loan_summary(member.family)
        net_cents = total_cents + int(loans['lend_cents']) - int(loans['borrow_cents'])

        def _pct(numerator):
            if not net_cents:
                return None
            return round(numerator / net_cents * 100, 2)

        return api_response({
            'has_invest': bool(invests_all),
            'book': book,
            'books': book_tabs,
            'account_count': len(invests),
            'principal_cents': principal_now,
            'principal': yuan(principal_now),
            'value_cents': value_now,
            'value': yuan(value_now),
            'profit_cents': profit_now,
            'profit': yuan(profit_now),
            'profit_rate': (round(profit_now / principal_now * 100, 2)
                            if principal_now > 0 else None),
            # 今年收益：年初基准 → 现在，正值=今年赚的，负值=今年亏的
            'begin_ym': begin_used,
            'begin_value_cents': begin_value,
            'begin_value': None if begin_value is None else yuan(begin_value),
            'begin_profit_cents': begin_profit,
            'begin_profit': None if begin_profit is None else yuan(begin_profit),
            'year_profit_cents': year_profit,
            'year_profit': yuan(year_profit),
            'year_profit_rate': (round(year_profit / begin_value * 100, 2)
                                 if begin_value else None),
            # 收益对家庭总资产的影响
            'net_assets_cents': net_cents,
            'net_assets': yuan(net_cents),
            'account_assets_cents': total_cents,
            'account_assets': yuan(total_cents),
            'profit_of_assets_pct': _pct(profit_now),
            'year_profit_of_assets_pct': _pct(year_profit),
            'assets_ex_profit_cents': net_cents - profit_now,
            'assets_ex_profit': yuan(net_cents - profit_now),
            'accounts': items,
            'trend': trend,
        })
