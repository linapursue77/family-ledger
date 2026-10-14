# -*- coding: utf-8 -*-
"""聚合计算：首页概览、分类占比、成员占比、趋势。

★ 入参必须是已经过 domain.visibility 过滤的 TxView 列表，
  保证「合计」与「明细」口径一致。
"""
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta

from domain.categories import CATEGORY_MAP
from domain.money import safe_pct, yuan

EXPENSE = 'expense'
INCOME = 'income'
TRANSFER = 'transfer'
# 借贷流水类型：出现在流水列表里，但不参与任何收支统计与分类聚合
LOAN_IN = 'loan_in'
LOAN_OUT = 'loan_out'
LOAN_TYPES = (LOAN_IN, LOAN_OUT)


def _parse_date(value) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or '')[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


def sum_amount(txs, tx_type: str) -> int:
    """按类型求和（返回分）。"""
    return sum(int(t.amount_cents) for t in txs if t.type == tx_type)


def group_by_category(txs, tx_type: str = EXPENSE, category_meta: dict = None) -> list[dict]:
    """按分类汇总，降序。

    category_meta: 可选的 {category_id: {'name','icon','color'}}，
                   不传则自动从 load_category_meta() 取（静态预设 + 数据库自定义）。
    """
    buckets = defaultdict(int)
    for t in txs:
        if t.type != tx_type:
            continue
        buckets[t.category_id or 'other'] += int(t.amount_cents)

    if not buckets:
        return []

    if category_meta is None:
        # 延迟导入：避免 domain 层在 App 未就绪时触发 ORM 加载
        from domain.category_meta import load_category_meta

        category_meta = load_category_meta()

    total = sum(buckets.values())
    rows = []
    for category_id, amount in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True):
        # ★ 自定义分类优先走数据库元信息，取不到再退回静态预设，
        #   否则新增分类在报告里会显示成裸 ID（c1a2b3c4d5）
        meta = category_meta.get(category_id) or CATEGORY_MAP.get(category_id, {})
        rows.append({
            'category_id': category_id,
            'name': meta.get('name', category_id),
            'icon': meta.get('icon', '💰'),
            'color': meta.get('color', '#8D6E63'),
            'amount_cents': amount,
            'amount': yuan(amount),
            'percent': safe_pct(amount, total),
        })
    return rows


def group_by_member(txs, tx_type: str, members: dict) -> list[dict]:
    """按成员汇总。members: {user_id: nickname}"""
    buckets = defaultdict(int)
    for t in txs:
        if t.type != tx_type:
            continue
        buckets[str(t.user_id)] += int(t.amount_cents)

    total = sum(buckets.values())
    rows = []
    for user_id, amount in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True):
        rows.append({
            'user_id': user_id,
            'name': members.get(user_id, '未知成员'),
            'amount_cents': amount,
            'amount': yuan(amount),
            'percent': safe_pct(amount, total),
        })
    return rows


def monthly_trend(txs, months: int = 6, today: datetime = None) -> list[dict]:
    """近 N 月收支趋势。"""
    today = today or datetime.now()
    buckets = OrderedDict()
    cursor = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keys = []
    for _ in range(months):
        keys.append(cursor.strftime('%Y-%m'))
        buckets[cursor.strftime('%Y-%m')] = {'income': 0, 'expense': 0}
        # 往前推一个月
        year = cursor.year + (cursor.month - 2) // 12
        month = (cursor.month - 2) % 12 + 1
        cursor = cursor.replace(year=year, month=month)
    keys.reverse()

    for t in txs:
        dt = _parse_date(t.transaction_date)
        key = dt.strftime('%Y-%m')
        if key not in buckets:
            continue
        if t.type == INCOME:
            buckets[key]['income'] += int(t.amount_cents)
        elif t.type == EXPENSE:
            buckets[key]['expense'] += int(t.amount_cents)

    return [
        {
            'month': key,
            'income': yuan(buckets[key]['income']),
            'expense': yuan(buckets[key]['expense']),
            'balance': yuan(buckets[key]['income'] - buckets[key]['expense']),
        }
        for key in keys
    ]


def group_by_account(txs, accounts_meta: list, tx_type: str = None) -> list[dict]:
    """按账户汇总收支。

    accounts_meta: [{'id', 'name', 'icon', 'book_type'}]
    tx_type: 'expense' | 'income' | None（None 时 amount 取净额 = 收入 - 支出）

    ★ 账户行以传入的 meta 为准：本月没流水的账户也会出现（金额 0），
      避免前端「账户分布」因为某账户没花过钱就整行消失、行高跳动。
    """
    income_b, expense_b, count_b = defaultdict(int), defaultdict(int), defaultdict(int)
    has_unknown = False
    for t in txs:
        # 借贷流水只改变账户余额，不计入收支分布，也不占用「笔数」
        if t.type in LOAN_TYPES:
            continue
        aid = str(t.account_id or '')
        if not aid:
            # 记账时未选账户的老数据：单独归到「未指定账户」。
            # ★ 不能 continue —— 否则这部分金额会从账户分布里凭空消失，
            #   导致「账户分布合计」小于「支出合计」，报告对不上账。
            has_unknown = True
        count_b[aid] += 1
        if t.type == INCOME:
            income_b[aid] += int(t.amount_cents)
        elif t.type == EXPENSE:
            expense_b[aid] += int(t.amount_cents)

    rows = []
    for meta in accounts_meta:
        aid = str(meta.get('id', ''))
        inc, exp = income_b.get(aid, 0), expense_b.get(aid, 0)
        if tx_type == INCOME:
            amount = inc
        elif tx_type == EXPENSE:
            amount = exp
        else:
            amount = inc - exp
        rows.append({
            'account_id': aid,
            'name': meta.get('name', '账户'),
            'icon': meta.get('icon', '💰'),
            'book_type': meta.get('book_type', 'husband'),
            'income_cents': inc,
            'income': yuan(inc),
            'expense_cents': exp,
            'expense': yuan(exp),
            'net_cents': inc - exp,
            'net': yuan(inc - exp),
            'amount_cents': amount,
            'amount': yuan(amount),
            'count': count_b.get(aid, 0),
        })

    if has_unknown:
        inc, exp = income_b.get('', 0), expense_b.get('', 0)
        if tx_type == INCOME:
            amount = inc
        elif tx_type == EXPENSE:
            amount = exp
        else:
            amount = inc - exp
        rows.append({
            'account_id': '',
            'name': '未指定账户',
            'icon': '❓',
            'book_type': 'shared',
            'income_cents': inc,
            'income': yuan(inc),
            'expense_cents': exp,
            'expense': yuan(exp),
            'net_cents': inc - exp,
            'net': yuan(inc - exp),
            'amount_cents': amount,
            'amount': yuan(amount),
            'count': count_b.get('', 0),
        })

    total_abs = sum(abs(r['amount_cents']) for r in rows)
    for row in rows:
        row['percent'] = safe_pct(abs(row['amount_cents']), total_abs)
    rows.sort(key=lambda r: abs(r['amount_cents']), reverse=True)
    return rows


def _next_month(cursor):
    """日期/时间 → 下个月 1 号。"""
    year = cursor.year + cursor.month // 12
    month = cursor.month % 12 + 1
    return cursor.replace(year=year, month=month, day=1)


def period_trend(txs, start: datetime, end: datetime) -> list[dict]:
    """报告趋势：跨度 ≤ 45 天按日，更长按月。

    ★ 桶按 start~end 全量铺满，没有流水的日子/月份也补 0，
      折线不会因为中间缺数据而错位。
    """
    by_day = (end.date() - start.date()).days <= 45
    buckets = OrderedDict()

    if by_day:
        cursor = start.date()
        while cursor <= end.date():
            buckets[cursor.strftime('%m-%d')] = {'income': 0, 'expense': 0}
            cursor += timedelta(days=1)
    else:
        cursor = start.date().replace(day=1)
        while cursor <= end.date():
            buckets[cursor.strftime('%Y-%m')] = {'income': 0, 'expense': 0}
            cursor = _next_month(cursor)

    for t in txs:
        dt = _parse_date(t.transaction_date)
        key = dt.strftime('%m-%d') if by_day else dt.strftime('%Y-%m')
        if key not in buckets:
            continue
        if t.type == INCOME:
            buckets[key]['income'] += int(t.amount_cents)
        elif t.type == EXPENSE:
            buckets[key]['expense'] += int(t.amount_cents)

    return [
        {
            'label': key,
            'month': key,
            'income': yuan(item['income']),
            'expense': yuan(item['expense']),
            'balance': yuan(item['income'] - item['expense']),
        }
        for key, item in buckets.items()
    ]


def build_overview(txs, accounts, members: dict, range_desc: dict) -> dict:
    """首页/报告总览。"""
    total_income = sum_amount(txs, INCOME)
    total_expense = sum_amount(txs, EXPENSE)
    balance = total_income - total_expense

    total_assets = sum(int(a.get('balance_cents', 0)) for a in accounts)
    last_assets = sum(int(a.get('last_balance_cents', 0) or 0) for a in accounts)

    return {
        'range': range_desc,
        'total_assets_cents': total_assets,
        'total_assets': yuan(total_assets),
        'asset_change_cents': total_assets - last_assets,
        'asset_change': yuan(total_assets - last_assets),
        'income_cents': total_income,
        'income': yuan(total_income),
        'expense_cents': total_expense,
        'expense': yuan(total_expense),
        'balance_cents': balance,
        'balance': yuan(balance),
        'saving_rate': safe_pct(balance, total_income),
        'expense_categories': group_by_category(txs, EXPENSE),
        'income_categories': group_by_category(txs, INCOME),
        'expense_by_member': group_by_member(txs, EXPENSE, members),
        'income_by_member': group_by_member(txs, INCOME, members),
        'trend': monthly_trend(txs),
    }
