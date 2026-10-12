# -*- coding: utf-8 -*-
"""账本接口：分类、记账、账单导入、首页聚合。"""
import csv
import dataclasses
import hashlib
import io
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

from django.db import connection, transaction
from django.db.models import Max, Sum
from django.http import HttpResponse
from django.utils import timezone
from django_q.tasks import async_task
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.accounts.services import visible_accounts
from apps.core.response import BusinessError, api_response
from apps.families.permissions import IsFamilyMember
from apps.families.services import (
    build_viewer_ctx,
    get_thresholds,
    member_nicknames,
    require_member,
)
from apps.ledger.models import AISettings, Category, ImportTask, Transaction
from apps.loans.services import summarize as loan_summary
from apps.ledger.serializers import (
    CategoryCreateSerializer,
    CategorySerializer,
    TransactionCreateSerializer,
)
from apps.ledger.services import (
    ASYNC_THRESHOLD_BYTES,
    MAX_UPLOAD_BYTES,
    apply_balance,
    build_preview,
    commit_import,
    parse_bytes,
)
from domain.ai import build_facts, get_config, is_usable, run_ai_insight, test_connection
from domain.aggregate import (
    EXPENSE,
    INCOME,
    LOAN_TYPES,
    build_overview,
    group_by_account,
    group_by_category,
    group_by_member,
    period_trend,
    sum_amount,
)
from domain.classify import classify
from domain.dedup import dedup_hash
from domain.insight import analyze
from domain.money import safe_pct, to_cents, yuan
from domain.privacy import check_quota, split_private_amount
from domain.threshold import describe as describe_threshold
from domain.timerange import DEFAULT_PRESET, PRESET_LABELS, describe, resolve
from domain.visibility import filter_transactions, to_transaction_view

logger = logging.getLogger(__name__)


def _parse_bound(value, end_of_day: bool = False) -> datetime:
    """日期入参解析：支持 YYYY-MM-DD（纯日期按当天首/末时刻）与完整时间戳。

    ★ 纯日期 + date_to 必须取当天 23:59:59，否则会漏掉当天的流水，
      导致「分类明细合计」与首页分类金额对不上。
    """
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        day = datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        raise BusinessError('日期格式应为 YYYY-MM-DD', code=4001)
    return datetime.combine(day, datetime.max.time() if end_of_day else datetime.min.time())


class CategoryViewSet(mixins.CreateModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """分类：系统预设 + 自定义。

    只放开「查」与「增」——系统预设分类一旦被改删，历史报表的分类口径会整体漂移。
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def get_queryset(self):
        queryset = Category.objects.all()
        kind = self.request.query_params.get('kind')
        if kind:
            queryset = queryset.filter(kind=kind)
        return queryset

    def create(self, request, *args, **kwargs):
        """新增自定义分类。

        ★ 已知限制：Category 表没有 family 外键，自定义分类对所有家庭可见。
          小范围内测可接受；要做多租户隔离需给 Category 加 family 字段，
          并同步调整 services.py 里两处 valid_categories 校验。
        """
        serializer = CategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        kind = data['kind']
        # 排到同类最后，不打乱系统预设的既有顺序
        max_sort = Category.objects.filter(kind=kind).aggregate(m=Max('sort'))['m'] or 0
        category = Category.objects.create(
            id=f'c{uuid4().hex[:10]}',
            kind=kind,
            name=data['name'],
            icon=(data.get('icon') or '').strip() or '💰',
            color=(data.get('color') or '').strip() or '#8D6E63',
            keywords=[],
            is_system=False,
            sort=max_sort + 1,
        )
        return api_response(
            CategorySerializer(category).data,
            message='已新增分类',
            http_status=status.HTTP_201_CREATED,
        )


class TransactionViewSet(viewsets.ModelViewSet):
    """记账与流水查询。"""

    permission_classes = [IsAuthenticated, IsFamilyMember]
    serializer_class = TransactionCreateSerializer

    # -------------------------------------------------- 查询
    def get_queryset(self):
        member = require_member(self.request.user)
        queryset = (Transaction.objects
                    .filter(family=member.family)
                    .select_related('category', 'account'))

        params = self.request.query_params
        tx_type = params.get('type')
        if tx_type:
            queryset = queryset.filter(type=tx_type)
        category_id = params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        member_id = params.get('member_id')
        if member_id:
            queryset = queryset.filter(user_id=member_id)
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        if date_from:
            queryset = queryset.filter(transaction_date__gte=_parse_bound(date_from))
        if date_to:
            queryset = queryset.filter(
                transaction_date__lte=_parse_bound(date_to, end_of_day=True))
        return queryset

    def list(self, request, *args, **kwargs):
        """★ 列表出口统一过滤：本人全见，配偶按权限/隐私规则脱敏。"""
        member = require_member(request.user)
        ctx = build_viewer_ctx(member)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        views = filter_transactions(page, ctx)
        return self.get_paginated_response([dataclasses.asdict(v) for v in views])

    def retrieve(self, request, *args, **kwargs):
        member = require_member(request.user)
        ctx = build_viewer_ctx(member)
        instance = self.get_object()
        from domain.visibility import to_transaction_view
        view = to_transaction_view(instance, ctx)
        if view is None:
            raise BusinessError('无权查看该记录', code=4003)
        return api_response(dataclasses.asdict(view))

    # -------------------------------------------------- 修改
    # update / partial_update 在下方 destroy 之前定义：
    # 修改必须冲正余额，不能走 ModelViewSet 默认实现，也不能简单拦截。

    # -------------------------------------------------- 记账
    def create(self, request, *args, **kwargs):
        member = require_member(request.user)
        family = member.family
        user = request.user

        # ★ 授权生效点：主账号关掉「允许记账」后，子账号不能再写账（读不受影响）
        if not member.effective_permissions.get('allow_record', True):
            raise BusinessError('主账号尚未授权你记账，请联系 TA 在家庭管理里开启', code=4003)

        ser = TransactionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        amount_cents = to_cents(data['amount'])
        tx_type = data['type']
        merchant = data.get('merchant') or ''
        is_private = bool(data.get('is_private')) and tx_type == 'expense'

        account = None
        account_id = data.get('account')
        if account_id:
            # 不能把账记到对方「仅本人可见」的账户上
            account = visible_accounts(family, user).filter(id=account_id).first()
            if account is None:
                raise BusinessError('账户不存在或无权记账到该账户')

        # 分类：未指定则用规则引擎自动匹配
        category_id = data.get('category')
        category_source = 'manual'
        if not category_id:
            category_id, category_source = classify(merchant)
        category = Category.objects.filter(id=category_id).first()

        tx_date = data.get('transaction_date') or timezone.now()

        # 隐私额度校验（仅支出）
        privacy_hint = None
        auto_public = False
        if is_private:
            used = self._month_private_used(user, tx_date)
            quota = check_quota(amount_cents, used, user.privacy_limit_cents)
            privacy_hint = quota
            if not quota['allow_private']:
                is_private = False
            elif quota['will_auto_public']:
                # 超出额度的部分自动公开：拆成两笔
                private_part, public_part = split_private_amount(
                    amount_cents, used, user.privacy_limit_cents)
                if public_part > 0 and private_part > 0:
                    self._write_tx(family, user, account, tx_type, public_part, category,
                                   merchant, data, tx_date, is_private=False, auto_public=True)
                    amount_cents = private_part
                elif public_part > 0:
                    # 额度已用满，整笔计入共同支出
                    is_private = False
                    auto_public = True

        thresholds = get_thresholds(family)
        threshold_hint = describe_threshold(amount_cents, thresholds) if tx_type == 'expense' else None

        with transaction.atomic():
            tx = self._write_tx(family, user, account, tx_type, amount_cents, category,
                                merchant, data, tx_date, is_private=is_private,
                                is_hidden=bool(data.get('is_hidden')),
                                auto_public=auto_public)

        return api_response({
            'transaction': dataclasses.asdict(to_transaction_view(tx, build_viewer_ctx(member))),
            'category_source': category_source,
            'privacy': privacy_hint,
            'threshold': threshold_hint,
        }, message='已保存', http_status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """PATCH/PUT /ledger/transactions/{id}/ —— 修改一笔流水。

        ★ 金额、类型、账户都可能变，所以必须先把旧流水对余额的影响冲正、再按新值重新应用，
          两步放在同一个事务里，避免改金额导致账户余额凭空多/少一笔。
        """
        return self._update_tx(request, partial=kwargs.pop('partial', False))

    def partial_update(self, request, *args, **kwargs):
        return self._update_tx(request, partial=True)

    def _update_tx(self, request, partial):
        member = require_member(request.user)
        tx = self.get_object()

        if tx.type in LOAN_TYPES:
            raise BusinessError('这是借钱来往生成的记录，请到「借钱来往」里修改', code=4003)
        if str(tx.user_id) != str(request.user.id):
            raise BusinessError('只能修改自己记录的账单', code=4003)

        # 该序列化器只用于校验入参，写库由下面的事务统一处理
        ser = TransactionCreateSerializer(data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # 账户：换账户时同样要校验落在自己可见的账户上
        account = tx.account
        if 'account' in data:
            account_id = data.get('account')
            if account_id:
                account = visible_accounts(member.family, request.user).filter(id=account_id).first()
                if account is None:
                    raise BusinessError('账户不存在或无权记账到该账户')
            else:
                account = None

        if 'category' in data:
            category_id = data.get('category')
            # 前端传空串表示「交给规则引擎重新判定」
            tx.category = Category.objects.filter(id=category_id).first() if category_id else None

        tx_type = data.get('type', tx.type)
        amount_cents = to_cents(data['amount']) if 'amount' in data else tx.amount_cents
        merchant = data.get('merchant', tx.merchant) if 'merchant' in data else tx.merchant

        if 'transaction_date' in data:
            tx.transaction_date = data.get('transaction_date') or tx.transaction_date
        if 'description' in data:
            tx.description = data.get('description') or ''
        if 'is_private' in data:
            tx.is_private = bool(data.get('is_private')) and tx_type == 'expense'

        with transaction.atomic():
            # 先冲正旧值（用旧的账户/类型/金额），再按新值应用
            self._apply_balance(tx.account, tx.type, tx.amount_cents, reverse=True)
            tx.account = account
            tx.type = tx_type
            tx.amount_cents = amount_cents
            tx.merchant = merchant
            tx.dedup_hash = dedup_hash(tx.transaction_date, amount_cents, merchant)
            tx.save()
            self._apply_balance(account, tx_type, amount_cents)

        return api_response({
            'transaction': dataclasses.asdict(to_transaction_view(tx, build_viewer_ctx(member))),
        }, message='已更新')

    def destroy(self, request, *args, **kwargs):
        """删除即反向冲正账户余额（不做物理删除更好，MVP 先冲正后删除）。"""
        tx = self.get_object()
        if tx.type in LOAN_TYPES:
            raise BusinessError('这是借钱来往生成的记录，请到「借钱来往」里删除或撤销还款', code=4003)
        if str(tx.user_id) != str(request.user.id):
            raise BusinessError('只能删除自己记录的账单', code=4003)
        with transaction.atomic():
            self._apply_balance(tx.account, tx.type, tx.amount_cents, reverse=True)
            tx.delete()
        return api_response(None, message='已删除')

    # -------------------------------------------------- 导出
    @action(detail=False, methods=['get'], url_path='export')
    def export_csv(self, request):
        """GET /ledger/transactions/export/?preset=last_month&type=expense

        ★ 导出必须和列表走同一个 filter_transactions：屏幕上看不到的私密消费，
          导出文件里也不能出现（商户与备注在视图层已被替换）。
        """
        member = require_member(request.user)
        family = member.family
        ctx = build_viewer_ctx(member)

        preset = (request.query_params.get('preset') or 'all').strip()
        if preset == 'all':
            txs = Transaction.objects.filter(family=family)
        else:
            try:
                start, end = resolve(
                    preset,
                    start=OverviewView._parse_date(request.query_params.get('start')),
                    end=OverviewView._parse_date(request.query_params.get('end')),
                )
            except ValueError as exc:
                raise BusinessError(str(exc), code=4001)
            txs = Transaction.objects.filter(
                family=family, transaction_date__range=(start, end))

        txs = txs.select_related('category', 'account').order_by('-transaction_date')
        views = filter_transactions(list(txs), ctx)

        tx_type = (request.query_params.get('type') or '').strip()
        if tx_type in (INCOME, EXPENSE):
            views = [v for v in views if v.type == tx_type]

        acc_names = {str(a.id): a.name for a in visible_accounts(family, request.user)}
        cat_names = {str(c.id): c.name for c in Category.objects.all()}
        nicknames = member_nicknames(family)
        type_text = {'expense': '支出', 'income': '收入', 'transfer': '转账',
                     'loan_in': '借入/回款', 'loan_out': '借出/还款'}

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['日期', '类型', '金额(元)', '分类', '账户',
                         '商户/平台', '备注', '记账人', '私密', '来源'])
        for v in views:
            writer.writerow([
                str(v.transaction_date)[:16],
                type_text.get(v.type, v.type),
                '%.2f' % (v.amount_cents / 100),
                cat_names.get(v.category_id, ''),
                acc_names.get(str(v.account_id), '—'),
                v.merchant or '',
                v.description or '',
                nicknames.get(str(v.user_id), '') or '已移除成员',
                '是' if v.is_private else '',
                '账单导入' if v.source == 'import' else '手动记账',
            ])

        label = '全部' if preset == 'all' else PRESET_LABELS.get(preset, preset)
        fname = '家庭账单_%s_%s.csv' % (label, timezone.localdate().strftime('%Y%m%d'))
        resp = HttpResponse('\ufeff' + buf.getvalue(), content_type='text/csv; charset=utf-8')
        # 中文文件名走 RFC 5987，同时给个 ASCII 兜底
        resp['Content-Disposition'] = "attachment; filename=\"ledger_%s.csv\"; filename*=UTF-8''%s" % (
            timezone.localdate().strftime('%Y%m%d'), quote(fname))
        return resp

    # -------------------------------------------------- 内部
    @staticmethod
    def _month_private_used(user, tx_date) -> int:
        """当月已用私密额度（分）。"""
        start = tx_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = (Transaction.objects
                 .filter(user=user, is_private=True, type='expense',
                         transaction_date__gte=start)
                 .aggregate(total=Sum('amount_cents')))
        return total['total'] or 0

    @staticmethod
    def _write_tx(family, user, account, tx_type, amount_cents, category, merchant,
                  data, tx_date, is_private=False, is_hidden=False, auto_public=False):
        """写入流水并同步账户余额（单事务内调用）。"""
        tx = Transaction.objects.create(
            family=family,
            user=user,
            account=account,
            type=tx_type,
            amount_cents=amount_cents,
            category=category,
            merchant=merchant,
            description=data.get('description') or '',
            source=data.get('source') or 'manual',
            is_private=is_private,
            is_hidden=is_hidden,
            auto_public=auto_public,
            transaction_date=tx_date,
            dedup_hash=dedup_hash(tx_date, amount_cents, merchant),
        )
        TransactionViewSet._apply_balance(account, tx_type, amount_cents)
        return tx

    @staticmethod
    def _apply_balance(account, tx_type, amount_cents, reverse=False):
        """支出减、收入加、转账不动。reverse=True 表示冲正。"""
        # 借贷流水的余额由借钱来往模块自己维护，这里绝不能重复冲正
        if account is None or tx_type == 'transfer' or tx_type in LOAN_TYPES:
            return
        sign = 1 if tx_type == 'income' else -1
        if reverse:
            sign = -sign
        if connection.vendor == 'mysql':
            locked = Account.objects.select_for_update().get(pk=account.pk)
        else:
            locked = account
        locked.balance_cents = locked.balance_cents + sign * int(amount_cents)
        locked.save(update_fields=['balance_cents', 'updated_at'])


class MerchantHistoryView(APIView):
    """GET /ledger/merchants/history/?category_id=&limit=5 —— 备注历史。

    记账时同一个分类下经常重复输入同样的备注（常去的店、固定开销名目），
    这里按分类回传该家庭最近用过的备注，去重后取前 N 条，供前端做快捷选择。

    ★ 私密消费的备注不会外泄：只取本人记的流水，不跨成员汇总。
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        category_id = (request.query_params.get('category_id') or '').strip()
        if not category_id:
            return api_response([])

        try:
            limit = int(request.query_params.get('limit') or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        rows = (Transaction.objects
                .filter(family=member.family, category_id=category_id, user=request.user)
                .exclude(merchant='')
                .exclude(merchant__isnull=True)
                .order_by('-transaction_date', '-created_at')
                .values_list('merchant', flat=True))

        # ★ 只保留最近一次使用的顺序，同时去掉重复项
        seen, history = set(), []
        for name in rows.iterator():
            text = (name or '').strip()
            if text and text not in seen:
                seen.add(text)
                history.append(text)
            if len(history) >= limit:
                break

        return api_response(history)


class OverviewView(APIView):
    """首页聚合：资产 / 收支 / 分类占比 / 成员占比 / 趋势。

    ★ 所有数字都基于「已过滤」的流水计算，保证合计与明细口径一致。
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        family = member.family
        ctx = build_viewer_ctx(member)

        preset = request.query_params.get('preset') or DEFAULT_PRESET
        try:
            start, end = resolve(
                preset,
                start=self._parse_date(request.query_params.get('start')),
                end=self._parse_date(request.query_params.get('end')),
            )
        except ValueError as exc:
            raise BusinessError(str(exc), code=4001)

        txs = (Transaction.objects
               .filter(family=family, transaction_date__range=(start, end))
               .select_related('category'))
        views = filter_transactions(txs, ctx)

        # 账户元信息同样按可见性过滤：他人「仅本人可见」的账户不出现在概览里
        accounts = visible_accounts(family, request.user).filter(is_count_total=True)
        account_payload = [
            {'id': a.id, 'name': a.name, 'book_type': a.book_type,
             'balance_cents': a.balance_cents,
             'last_balance_cents': a.last_balance_cents}
            for a in accounts
        ]

        overview = build_overview(
            views,
            account_payload,
            member_nicknames(family),
            describe(preset, start, end),
        )
        overview['accounts'] = [
            {**item, 'balance': yuan(item['balance_cents'])} for item in account_payload
        ]
        overview['thresholds'] = get_thresholds(family)
        # 净资产口径与账户页保持一致：账户余额 + 借出未收（应收）− 借入未还（应付）
        loans = loan_summary(family)
        base = int(overview.get('total_assets_cents') or 0)
        receivable, payable = int(loans['lend_cents']), int(loans['borrow_cents'])
        overview['account_assets_cents'] = base
        overview['account_assets'] = yuan(base)
        overview['receivable_cents'] = receivable
        overview['receivable'] = yuan(receivable)
        overview['payable_cents'] = payable
        overview['payable'] = yuan(payable)
        overview['loans'] = loans
        net = base + receivable - payable
        overview['total_assets_cents'] = net
        overview['total_assets'] = yuan(net)
        return api_response(overview)

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            raise BusinessError('日期格式应为 YYYY-MM-DD', code=4001)


class ReportView(APIView):
    """报告页聚合：收入 / 支出分开统计，并支持按账户维度查看。

    GET /ledger/report/?preset=last_month&type=expense&account_id=
    - preset: 同首页时间预设（last_week / last_month / last_3months / ... / custom）
    - type:   expense | income，决定「分类明细 / 成员分布 / 趋势高亮」的口径
    - account_id: 空 = 全部账户；指定后所有统计只算这一个账户

    ★ 与首页完全同源：先过 visibility 过滤再聚合，
      保证报告里的合计、分类、账户分布三者的金额永远对得上。
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        family = member.family
        ctx = build_viewer_ctx(member)

        preset = request.query_params.get('preset') or 'last_month'
        tx_type = request.query_params.get('type') or EXPENSE
        if tx_type not in (INCOME, EXPENSE):
            raise BusinessError('type 只能是 income 或 expense', code=4001)
        account_id = (request.query_params.get('account_id') or '').strip()

        try:
            start, end = resolve(
                preset,
                start=OverviewView._parse_date(request.query_params.get('start')),
                end=OverviewView._parse_date(request.query_params.get('end')),
            )
        except ValueError as exc:
            raise BusinessError(str(exc), code=4001)

        txs = (Transaction.objects
               .filter(family=family, transaction_date__range=(start, end))
               .select_related('category'))
        views = filter_transactions(txs, ctx)

        accounts = visible_accounts(family, request.user).filter(is_count_total=True)
        accounts_meta = [
            {'id': a.id, 'name': a.name, 'icon': a.icon, 'book_type': a.book_type}
            for a in accounts
        ]

        scope = None
        if account_id:
            scope = next((m for m in accounts_meta if str(m['id']) == account_id), None)
            if scope is None:
                raise BusinessError('账户不存在或不属于当前家庭', code=4004)
            views = [v for v in views if str(v.account_id) == account_id]

        total_income = sum_amount(views, INCOME)
        total_expense = sum_amount(views, EXPENSE)
        total = total_expense if tx_type == EXPENSE else total_income
        count = sum(1 for v in views if v.type == tx_type)
        days = max((end.date() - start.date()).days + 1, 1)

        # 分类明细补上「笔数」（聚合层的 group_by_category 只有金额）
        count_by_cat = {}
        for v in views:
            if v.type == tx_type:
                key = v.category_id or 'other'
                count_by_cat[key] = count_by_cat.get(key, 0) + 1
        categories = group_by_category(views, tx_type)
        for item in categories:
            item['count'] = count_by_cat.get(item['category_id'], 0)

        # 成员分布补上所属账本：前端据此用与首页同一套账本配色
        book_map = {str(m.user_id): m.book_type for m in family.members.all()}
        by_member = group_by_member(views, tx_type, member_nicknames(family))
        for item in by_member:
            item['book_type'] = book_map.get(item['user_id'], '')

        return api_response({
            'range': describe(preset, start, end),
            'type': tx_type,
            'scope': scope,
            'summary': {
                'income_cents': total_income,
                'income': yuan(total_income),
                'expense_cents': total_expense,
                'expense': yuan(total_expense),
                'balance_cents': total_income - total_expense,
                'balance': yuan(total_income - total_expense),
                'saving_rate': safe_pct(total_income - total_expense, total_income),
                'expense_of_income': safe_pct(total_expense, total_income),
                'total_cents': total,
                'total': yuan(total),
                'count': count,
                'days': days,
                'avg_daily': yuan(int(round(total / days))),
            },
            'categories': categories,
            'by_account': group_by_account(views, accounts_meta, tx_type),
            'by_member': by_member,
            'trend': period_trend(views, start, end),
        })


def _collect_report_views(family, ctx, start, end, account_id: str = ''):
    """★ 报告取数唯一出口：先过 visibility 过滤，再按账户收窄。

    与 ReportView 同源，保证分析里的金额和报告里的金额永远对得上。
    """
    txs = (Transaction.objects
           .filter(family=family, transaction_date__range=(start, end))
           .select_related('category'))
    views = filter_transactions(txs, ctx)
    if account_id:
        views = [v for v in views if str(v.account_id) == account_id]
    return views


class ReportInsightView(APIView):
    """报告智能分析：本地规则引擎输出洞察与改进建议。

    GET /ledger/report/insight/?preset=last_month&type=expense&account_id=

    ★ 不调用外部大模型：账单数据不出服务、零延迟、结果可复现。
      环比基准 = 紧邻当前区间之前、等长的上一个区间。
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]

    def get(self, request):
        member = require_member(request.user)
        family = member.family
        ctx = build_viewer_ctx(member)

        preset = request.query_params.get('preset') or 'last_month'
        tx_type = request.query_params.get('type') or EXPENSE
        if tx_type not in (INCOME, EXPENSE):
            raise BusinessError('type 只能是 income 或 expense', code=4001)
        account_id = (request.query_params.get('account_id') or '').strip()

        try:
            start, end = resolve(
                preset,
                start=OverviewView._parse_date(request.query_params.get('start')),
                end=OverviewView._parse_date(request.query_params.get('end')),
            )
        except ValueError as exc:
            raise BusinessError(str(exc), code=4001)

        accounts = visible_accounts(family, request.user).filter(is_count_total=True)
        if account_id and not any(str(a.id) == account_id for a in accounts):
            raise BusinessError('账户不存在或不属于当前家庭', code=4004)

        views = _collect_report_views(family, ctx, start, end, account_id)

        days = max((end.date() - start.date()).days + 1, 1)
        prev_end = start - timedelta(seconds=1)
        prev_start = start - timedelta(days=days)
        prev_views = _collect_report_views(family, ctx, prev_start, prev_end, account_id)

        def summarize(items, s, e):
            inc = sum_amount(items, INCOME)
            exp = sum_amount(items, EXPENSE)
            span = max((e.date() - s.date()).days + 1, 1)
            total = exp if tx_type == EXPENSE else inc
            return {
                'income_cents': inc,
                'expense_cents': exp,
                'total_cents': total,
                'count': sum(1 for v in items if v.type == tx_type),
                'days': span,
                'saving_rate': safe_pct(inc - exp, inc),
            }

        summary = summarize(views, start, end)
        prev_summary = summarize(prev_views, prev_start, prev_end)

        categories = group_by_category(views, tx_type)
        count_by_cat = {}
        for v in views:
            if v.type == tx_type:
                key = v.category_id or 'other'
                count_by_cat[key] = count_by_cat.get(key, 0) + 1
        for item in categories:
            item['count'] = count_by_cat.get(item['category_id'], 0)
        prev_categories = group_by_category(prev_views, tx_type)

        by_member = group_by_member(views, tx_type, member_nicknames(family))
        book_map = {str(m.user_id): m.book_type for m in family.members.all()}
        for item in by_member:
            item['book_type'] = book_map.get(item['user_id'], '')

        target = [v for v in views if v.type == tx_type]
        top_txs = [
            {
                'merchant': v.merchant,
                'amount_cents': int(v.amount_cents),
                'transaction_date': str(v.transaction_date),
            }
            for v in sorted(target, key=lambda v: int(v.amount_cents), reverse=True)[:5]
        ]

        quality = {
            'unclassified_cents': sum(int(v.amount_cents) for v in target
                                      if not v.category_id or v.category_id == 'other'),
            'no_account_cents': sum(int(v.amount_cents) for v in target if not v.account_id),
        }

        result = analyze(
            tx_type=tx_type,
            days=summary['days'],
            summary=summary,
            categories=categories,
            prev_summary=prev_summary,
            prev_categories=prev_categories,
            by_member=by_member,
            top_txs=top_txs,
            quality=quality,
        )
        result['range'] = describe(preset, start, end)
        result['prev_range'] = {
            'start': prev_start.strftime('%Y-%m-%d'),
            'end': prev_end.strftime('%Y-%m-%d'),
        }

        # ★ AI 分析（可选能力）：前端带 ai=1 且后端已配置 Key 才走模型，
        #   未配置 / 调用失败一律回落本地规则引擎，接口结构保持不变。
        cfg = get_config(family)
        want_ai = str(request.query_params.get('ai') or '') in ('1', 'true')
        ai_meta = {
            'enabled': is_usable(cfg),
            'used': False,
            'model': cfg.get('model') or '',
            'reason': '',
        }
        if want_ai and ai_meta['enabled']:
            rng = result['range']
            facts = build_facts(
                tx_type=tx_type,
                days=summary['days'],
                range_text=f"{rng.get('label') or ''} {rng.get('start')} ~ {rng.get('end')}",
                summary=summary,
                categories=categories,
                prev_summary=prev_summary,
                by_member=by_member,
                top_txs=top_txs,
                quality=quality,
                local=result,
            )
            # 配置指纹进 key：换了 Key / 模型后旧缓存自动失效，不会看到过期结论
            cfg_tag = hashlib.sha1(
                ('%s|%s|%s' % (cfg['source'], cfg['model'], cfg['api_key'][-6:])).encode('utf-8')
            ).hexdigest()[:8]
            cache_key = ('insight:ai:%s:%s:%s:%s:%s%s'
                         % (family.id, cfg_tag, tx_type, account_id,
                            start.strftime('%Y%m%d'), end.strftime('%Y%m%d')))
            result, ai_meta = run_ai_insight(result, facts, cache_key, cfg)
        elif want_ai:
            ai_meta['reason'] = '未配置大模型'
        result['ai'] = ai_meta
        return api_response(result)


class AIConfigView(APIView):
    """AI 分析配置（家庭级）：界面填写 → 存库 → 即时生效，不用改 .env、不用重启。

    GET /ledger/ai/config/   读取当前生效配置（Key 只回掩码，绝不回传明文）
    PUT /ledger/ai/config/   保存配置
    """
    permission_classes = [IsAuthenticated, IsFamilyMember]

    @staticmethod
    def _mask(key: str) -> str:
        if not key:
            return ''
        return key[:3] + '•' * 8 + key[-4:] if len(key) > 10 else '•' * 6

    def get(self, request):
        member = require_member(request.user)
        cfg = get_config(member.family)
        return api_response({
            'enabled': bool(cfg['enabled']),
            'usable': is_usable(cfg),
            'provider': cfg['provider'],
            'base_url': cfg['base_url'],
            'model': cfg['model'],
            'has_key': bool(cfg['api_key']),
            'key_mask': self._mask(cfg['api_key']),
            'source': cfg['source'],
        })

    def put(self, request):
        member = require_member(request.user)
        data = request.data or {}
        row, _ = AISettings.objects.get_or_create(family=member.family)
        # ★ 增量更新：只改请求里带了的字段，
        #   这样界面上「只切开关」时不会把已存的接口地址 / 模型名清空
        if 'enabled' in data:
            row.enabled = bool(data.get('enabled'))
        if 'provider' in data:
            row.provider = (str(data.get('provider') or 'deepseek').strip() or 'deepseek')[:32]
        if 'base_url' in data:
            row.base_url = str(data.get('base_url') or '').strip().rstrip('/')[:200]
        if 'model' in data:
            row.model = str(data.get('model') or '').strip()[:80]
        new_key = str(data.get('api_key') or '').strip()
        if new_key:
            row.api_key = new_key[:300]
        elif data.get('clear_key'):
            row.api_key = ''
        if row.enabled and not row.api_key:
            raise BusinessError('启用 AI 分析需要先填写 API Key', code=4001)
        if row.enabled and not (row.base_url and row.model):
            raise BusinessError('启用 AI 分析需要填写接口地址与模型名', code=4001)
        row.save()
        cfg = get_config(member.family)
        return api_response({
            'enabled': bool(cfg['enabled']),
            'usable': is_usable(cfg),
            'provider': cfg['provider'],
            'base_url': cfg['base_url'],
            'model': cfg['model'],
            'has_key': bool(cfg['api_key']),
            'key_mask': self._mask(cfg['api_key']),
            'source': cfg['source'],
        }, message='已保存，立即生效')


class AIConfigTestView(APIView):
    """POST /ledger/ai/config/test/ —— 用表单里的值（或已存配置）试跑一次，验证连通性。"""
    permission_classes = [IsAuthenticated, IsFamilyMember]

    def post(self, request):
        member = require_member(request.user)
        data = request.data or {}
        cfg = get_config(member.family)
        for field in ('base_url', 'model', 'api_key'):
            if str(data.get(field) or '').strip():
                cfg[field] = str(data[field]).strip()
        ok, message = test_connection(cfg)
        return api_response({'ok': ok, 'message': message})


class ImportTaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """账单导入（PRD 4.3）：上传 → 解析去重 → 预览 → 确认入库。

    - POST   /ledger/imports/            上传 CSV（multipart: file, platform）
    - GET    /ledger/imports/{id}/       预览（新增 / 重复 / 待确认）
    - POST   /ledger/imports/{id}/confirm/  确认导入（幂等：已 done 的任务拒绝）
    - DELETE /ledger/imports/{id}/       放弃本次导入
    """

    permission_classes = [IsAuthenticated, IsFamilyMember]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        member = require_member(self.request.user)
        return ImportTask.objects.filter(family=member.family)

    # -------------------------------------------------- 上传解析
    def create(self, request, *args, **kwargs):
        member = require_member(request.user)
        file_obj = request.FILES.get('file')
        if file_obj is None:
            raise BusinessError('请选择账单文件', code=4001)

        platform = request.data.get('platform') or None
        data = file_obj.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise BusinessError(
                f'文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 上限', code=4001)

        # 大文件投递 Django-Q 后台解析；队列不可用时降级为同步解析
        if len(data) > ASYNC_THRESHOLD_BYTES:
            task = ImportTask.objects.create(
                family=member.family, user=request.user,
                platform=platform or 'wechat', status=ImportTask.STATUS_PENDING)
            try:
                async_task('apps.ledger.tasks.parse_import_task', task.id, data, platform)
                return api_response(
                    {'task': self._task_brief(task), 'async': True},
                    message='文件较大，已转入后台解析，请稍后查看预览',
                    http_status=status.HTTP_202_ACCEPTED)
            except Exception:
                logger.exception('任务队列不可用，降级为同步解析 task=%s', task.id)
                task.delete()

        try:
            parsed = parse_bytes(data, platform)
        except ValueError as exc:
            raise BusinessError(f'解析失败：{exc}', code=4001)

        preview = build_preview(parsed['records'], member.family)
        task = ImportTask.objects.create(
            family=member.family,
            user=request.user,
            platform=parsed['platform'],
            status=ImportTask.STATUS_PREVIEW,
            total_count=preview['stats']['total'],
            new_count=preview['stats']['new'],
            duplicate_count=(preview['stats']['duplicate']
                             + preview['stats']['internal_duplicate']),
            failed_count=len(parsed['skipped']),
            preview=preview['rows'],
        )
        logger.info('账单解析 task=%s platform=%s encoding=%s total=%s new=%s',
                    task.id, parsed['platform'], parsed['encoding'],
                    preview['stats']['total'], preview['stats']['new'])

        return api_response({
            'task': self._task_brief(task),
            'stats': preview['stats'],
            'rows': preview['rows'],
            'skipped': parsed['skipped'][:20],
            'encoding': parsed['encoding'],
        }, message='解析完成，请确认后导入', http_status=status.HTTP_201_CREATED)

    # -------------------------------------------------- 预览
    def retrieve(self, request, *args, **kwargs):
        task = self.get_object()
        rows = task.preview or []
        return api_response({
            'task': self._task_brief(task),
            'stats': {
                'total': len(rows),
                'new': sum(1 for r in rows if r.get('status') == 'new'),
                'duplicate': sum(1 for r in rows if r.get('status') == 'duplicate'),
                'internal_duplicate': sum(1 for r in rows
                                          if r.get('status') == 'internal_duplicate'),
                'uncategorized': sum(1 for r in rows if r.get('need_confirm')),
            },
            'rows': rows,
        })

    # -------------------------------------------------- 确认入库
    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, *args, **kwargs):
        task = self.get_object()
        if task.status == ImportTask.STATUS_DONE:
            raise BusinessError('该任务已导入，请勿重复提交', code=4005)
        if not task.preview:
            raise BusinessError('没有可导入的预览数据', code=4001)

        member = require_member(request.user)
        account = None
        account_id = request.data.get('account_id')
        if account_id:
            account = visible_accounts(member.family, request.user).filter(id=account_id).first()
            if account is None:
                raise BusinessError('账户不存在或无权导入到该账户', code=4001)

        indexes = request.data.get('indexes')
        if indexes is not None and not isinstance(indexes, list):
            raise BusinessError('indexes 应为下标数组', code=4001)

        result = commit_import(task, account, request.user,
                               indexes=indexes,
                               overrides=request.data.get('overrides') or {})
        task.status = ImportTask.STATUS_DONE
        task.new_count = result['created']
        task.save(update_fields=['status', 'new_count'])

        return api_response({
            **result,
            'income': yuan(result['income_cents']),
            'expense': yuan(result['expense_cents']),
            'balance_delta': yuan(result['delta_cents']),
            'account_id': account.id if account else None,
        }, message=f"已导入 {result['created']} 笔")

    @staticmethod
    def _task_brief(task: ImportTask) -> dict:
        return {
            'id': task.id,
            'platform': task.platform,
            'status': task.status,
            'total_count': task.total_count,
            'new_count': task.new_count,
            'duplicate_count': task.duplicate_count,
            'failed_count': task.failed_count,
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }
