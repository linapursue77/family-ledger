# -*- coding: utf-8 -*-
"""支付宝账单解析（PRD 4.3.1）。

表头示例（不同版本列数不同）：
交易号,商家订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,交易对方,
商品名称,金额（元）,收/支,交易状态,服务费（元）,成功退款（元）,备注,资金状态

规则：
- 时间优先取「付款时间」，为空则取「交易创建时间」
- 收/支 = 支出/收入，'不计收支' 跳过
- 交易状态含 关闭/退款/失败 → 跳过
"""
from domain.dedup import dedup_hash
from domain.money import to_cents
from domain.parse.csv import (
    col_index,
    is_effective_status,
    normalize_direction,
    parse_datetime,
)

PLATFORM = 'alipay'
MAX_ROWS = 50000


def parse_alipay(rows: list[list[str]], header: list[str]) -> tuple[list[dict], list[dict]]:
    """返回 (可导入记录, 被跳过的记录)。"""
    idx_paid = col_index(header, '付款时间')
    idx_created = col_index(header, '交易创建时间')
    idx_date = idx_paid if idx_paid is not None else idx_created
    idx_merchant = col_index(header, '交易对方', '对方')
    idx_goods = col_index(header, '商品名称', '商品')
    idx_direction = col_index(header, '收/支', '收支类型', '收付款类型', '收支')
    idx_amount = col_index(header, '金额')
    idx_status = col_index(header, '交易状态', '当前状态')
    idx_note = col_index(header, '备注')
    idx_fund = col_index(header, '资金状态')

    if idx_date is None or idx_amount is None or idx_direction is None:
        raise ValueError('支付宝账单缺少必要列（时间/收-支/金额）')

    records: list[dict] = []
    skipped: list[dict] = []

    for row in rows[:MAX_ROWS]:
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ''

        direction = normalize_direction(cell(idx_direction))
        if not direction:
            skipped.append({'reason': '不计收支', 'raw': _brief(row)})
            continue

        status = cell(idx_status)
        if not is_effective_status(status):
            skipped.append({'reason': f'状态：{status or "空"}', 'raw': _brief(row)})
            continue

        tx_date = parse_datetime(cell(idx_date)) or parse_datetime(cell(idx_created))
        if tx_date is None:
            skipped.append({'reason': '时间格式无法解析', 'raw': _brief(row)})
            continue

        try:
            amount_cents = abs(to_cents(cell(idx_amount)))
        except ValueError:
            skipped.append({'reason': '金额无法解析', 'raw': _brief(row)})
            continue
        if amount_cents <= 0:
            skipped.append({'reason': '金额为 0', 'raw': _brief(row)})
            continue

        merchant = cell(idx_merchant) or cell(idx_goods) or '支付宝'
        goods = cell(idx_goods)
        note = cell(idx_note)
        description = '/'.join(part for part in (goods, note) if part)[:255]

        records.append({
            'type': direction,
            'amount_cents': amount_cents,
            'merchant': merchant[:100],
            'description': description,
            'transaction_date': tx_date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': status,
            'payment_method': cell(idx_fund) or '支付宝',
            'dedup_hash': dedup_hash(tx_date, amount_cents, merchant),
        })

    return records, skipped


def _brief(row: list[str]) -> str:
    return ' | '.join((c or '').strip() for c in row[:6])[:200]
