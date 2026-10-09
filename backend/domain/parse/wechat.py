# -*- coding: utf-8 -*-
"""微信账单解析（PRD 4.3.1）。

表头示例：
交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注

规则：
- 收/支 = 支出/收入，'/' 或 '不计收支' 直接跳过
- 金额形如 '¥35.50'，去符号后转分
- 当前状态含 退款/关闭/失败 → 跳过
"""
from domain.dedup import dedup_hash
from domain.money import to_cents
from domain.parse.csv import (
    col_index,
    is_effective_status,
    normalize_direction,
    parse_datetime,
)

PLATFORM = 'wechat'
MAX_ROWS = 50000


def parse_wechat(rows: list[list[str]], header: list[str]) -> tuple[list[dict], list[dict]]:
    """返回 (可导入记录, 被跳过的记录)。"""
    idx_date = col_index(header, '交易时间')
    idx_merchant = col_index(header, '交易对方')
    idx_goods = col_index(header, '商品')
    idx_direction = col_index(header, '收/支', '收支类型', '收付款类型', '收支')
    idx_amount = col_index(header, '金额')
    idx_status = col_index(header, '当前状态', '交易状态')
    idx_note = col_index(header, '备注')
    idx_pay = col_index(header, '支付方式')

    if idx_date is None or idx_amount is None or idx_direction is None:
        raise ValueError('微信账单缺少必要列（交易时间/收-支/金额）')

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

        tx_date = parse_datetime(cell(idx_date))
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

        merchant = cell(idx_merchant) or cell(idx_goods) or '微信支付'
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
            'payment_method': cell(idx_pay),
            'dedup_hash': dedup_hash(tx_date, amount_cents, merchant),
        })

    return records, skipped


def _brief(row: list[str]) -> str:
    return ' | '.join((c or '').strip() for c in row[:6])[:200]
