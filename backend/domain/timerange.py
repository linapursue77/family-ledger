# -*- coding: utf-8 -*-
"""首页/报告的时间筛选（PRD 5.1）。"""
from datetime import date, datetime, timedelta

PRESETS = ['last_week', 'last_month', 'last_3months', 'last_half_year',
           'this_year', 'last_year', 'custom']

PRESET_LABELS = {
    'last_week': '近1周',
    'last_month': '近1月',
    'last_3months': '近3月',
    'last_half_year': '近半年',
    'this_year': '今年',
    'last_year': '近一年',
    'custom': '自定义',
}

DEFAULT_PRESET = 'last_week'


def _add_months(base: date, months: int) -> date:
    """按月加减，自动处理月末（如 3-31 减 1 月 → 2-28）。"""
    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    day = min(base.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def resolve(preset: str, today: date = None,
            start: date = None, end: date = None) -> tuple[datetime, datetime]:
    """返回 (start_datetime, end_datetime)，end 为当天 23:59:59。"""
    today = today or date.today()

    if preset == 'custom':
        if not start or not end:
            raise ValueError('自定义范围必须提供 start 与 end')
        if start > end:
            raise ValueError('开始日期不能晚于结束日期')
        if end > today:
            raise ValueError('结束日期不能晚于今天')
    elif preset == 'last_week':
        start, end = today - timedelta(days=6), today
    elif preset == 'last_month':
        start, end = today.replace(day=1), today
    elif preset == 'last_3months':
        start, end = _add_months(today, -3).replace(day=1), today
    elif preset == 'last_half_year':
        start, end = _add_months(today, -6).replace(day=1), today
    elif preset == 'this_year':
        start, end = date(today.year, 1, 1), today
    elif preset == 'last_year':
        start, end = _add_months(today, -12), today
    else:
        raise ValueError(f'不支持的时间预设: {preset}')

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    return start_dt, end_dt


def describe(preset: str, start: datetime, end: datetime) -> dict:
    """返回前端展示用的范围描述。"""
    return {
        'preset': preset,
        'label': PRESET_LABELS.get(preset, preset),
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
    }
