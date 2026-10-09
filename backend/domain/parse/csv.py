# -*- coding: utf-8 -*-
"""CSV 读取与通用工具。

微信/支付宝导出的账单都是「若干行说明头 + 一行表头 + 数据行」，
编码可能是 UTF-8(BOM) 或 GBK，列数随版本变化，因此不按下标硬取列，
一律按表头名模糊定位。
"""
import csv
import io
import re
from datetime import datetime

MAX_SCAN_ROWS = 40          # 说明头通常 ≤ 32 行（支付宝新版本更长）
DATE_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y/%m/%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y/%m/%d %H:%M',
    '%Y-%m-%d',
    '%Y/%m/%d',
    '%Y年%m月%d日 %H:%M:%S',
    '%Y年%m月%d日',
)


def detect_encoding(data: bytes) -> str:
    """编码探测：UTF-8(BOM) → UTF-8 → chardet → GBK 兜底。"""
    if data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    try:
        text = data.decode('utf-8')
        if '\ufffd' not in text:      # 无替换字符，说明确实是 UTF-8
            return 'utf-8'
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        guess = chardet.detect(data) or {}
        enc = guess.get('encoding')
        if enc and (guess.get('confidence') or 0) >= 0.6:
            try:
                data.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                pass
    except ImportError:
        pass
    return 'gbk'


def decode(data: bytes) -> tuple[str, str]:
    """返回 (文本, 编码名)。"""
    enc = detect_encoding(data)
    return data.decode(enc, errors='replace'), enc


def read_rows(text: str) -> list[list[str]]:
    """读取 CSV，丢弃全空行。"""
    return [row for row in csv.reader(io.StringIO(text))
            if any((cell or '').strip() for cell in row)]


def norm_header(cell: str) -> str:
    """表头归一化：'金额(元)' → '金额'，去掉 BOM/空白/括号内容。"""
    cell = (cell or '').replace('\ufeff', '').strip()
    cell = re.sub(r'[（(][^）)]*[）)]', '', cell)
    return re.sub(r'\s+', '', cell)


def find_header_row(rows: list[list[str]]) -> int:
    """定位表头行下标，找不到返回 -1。"""
    for idx, row in enumerate(rows[:MAX_SCAN_ROWS]):
        norm = {norm_header(c) for c in row}
        has_direction = any(k in norm for k in ('收/支', '收支类型', '收付款类型', '收支'))
        if has_direction and any('金额' in c for c in norm):
            return idx
    for idx, row in enumerate(rows[:MAX_SCAN_ROWS]):
        norm = {norm_header(c) for c in row}
        if any('金额' in c for c in norm) and any('时间' in c for c in norm):
            return idx
    return -1


def col_index(header: list[str], *candidates: str) -> int | None:
    """按候选列名定位下标：先全等，后包含。"""
    norm = [norm_header(c) for c in header]
    for cand in candidates:
        if cand in norm:
            return norm.index(cand)
    for cand in candidates:
        for idx, cell in enumerate(norm):
            if cand and cand in cell:
                return idx
    return None


def parse_datetime(value: str) -> datetime | None:
    """多格式时间解析。"""
    value = (value or '').strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def normalize_direction(value: str) -> str | None:
    """'支出'/'收入' → expense/income；'不计收支'/'/' → None（跳过）。"""
    text = (value or '').strip()
    if '支出' in text:
        return 'expense'
    if '收入' in text:
        return 'income'
    return None


def is_effective_status(status: str) -> bool:
    """过滤退款/关闭/失败记录（这些不应计入账本）。"""
    text = (status or '').strip()
    if not text:
        return True
    return not any(key in text for key in ('退款', '关闭', '失败', '撤销', '已取消'))
