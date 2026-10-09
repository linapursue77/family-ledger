# -*- coding: utf-8 -*-
"""导入去重：同一时间(精确到分钟) + 同一金额 + 同一商户 → 视为重复。"""
import hashlib
from datetime import datetime


def dedup_hash(transaction_date, amount_cents: int, merchant: str) -> str:
    """生成去重指纹。transaction_date 可为 datetime 或 ISO 字符串。"""
    if isinstance(transaction_date, datetime):
        minute_key = transaction_date.strftime('%Y-%m-%d %H:%M')
    else:
        minute_key = str(transaction_date)[:16]
    raw = f'{minute_key}|{int(amount_cents)}|{(merchant or "").strip()}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def mark_statuses(rows: list[dict], existing_hashes: set) -> list[dict]:
    """就地给每条记录打状态，保持原始顺序（预览需按文件顺序展示）。

    status ∈ {'new', 'duplicate', 'internal_duplicate'}：
    - internal_duplicate：同一文件内出现多次
    - duplicate：库中已存在同指纹
    - new：可导入
    """
    existing = set(existing_hashes or ())
    seen: set[str] = set()
    for row in rows:
        digest = row.get('dedup_hash') or ''
        if digest in seen:
            row['status'] = 'internal_duplicate'
        elif digest in existing:
            row['status'] = 'duplicate'
        else:
            row['status'] = 'new'
            existing.add(digest)
        seen.add(digest)
    return rows


def split_by_dedup(rows: list[dict], existing_hashes: set) -> dict:
    """把解析后的记录分成 新增 / 重复 / 文件内重复 三档。

    rows: [{'dedup_hash': str, ...}]
    """
    seen: set[str] = set()
    new, duplicate, internal_dup = [], [], []
    for row in rows:
        digest = row.get('dedup_hash') or ''
        if digest in seen:
            internal_dup.append(row)
            continue
        seen.add(digest)
        if digest in existing_hashes:
            duplicate.append(row)
        else:
            new.append(row)
    return {'new': new, 'duplicate': duplicate, 'internal_duplicate': internal_dup}
