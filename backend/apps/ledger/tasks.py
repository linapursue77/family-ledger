# -*- coding: utf-8 -*-
"""django-q 异步/定时任务入口（函数签名保持无参，供 Schedule 调用）。"""
import logging

from apps.ledger.recurring import run_due_rules

logger = logging.getLogger(__name__)


def run_recurring_rules():
    """每日执行一次：扫描到期规则并生成流水。"""
    stats = run_due_rules()
    logger.info('周期记账任务完成：%s', stats)
    return stats
