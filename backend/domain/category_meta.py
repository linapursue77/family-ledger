# -*- coding: utf-8 -*-
"""分类元信息（名称 / 图标 / 颜色）的统一来源。

★ 为什么需要这个模块：
  写路径（记账、账单导入）是查数据库的，自定义分类能正常存进流水；
  但读路径（报告分类明细、首页占比、AI 洞察）以前只查代码里的静态
  CATEGORY_MAP，自定义分类查不到就退化成「裸 ID」（如 c1a2b3c4d5），
  用户看起来就是「新增的分类没拉到 / 显示成一串乱码」。

  这里把「静态预设」与「数据库 Category 表」合并，并做短期缓存，
  保证读写口径一致：自定义分类在报告里显示真实名称、图标、颜色。
"""
from django.core.cache import cache

from domain.categories import CATEGORY_MAP

CACHE_KEY = 'category:meta:v1'
CACHE_TTL = 300

_DEFAULT_ICON = '💰'
_DEFAULT_COLOR = '#8D6E63'


def _static_meta() -> dict:
    """代码里的系统预设分类（离线兜底，永远可用）。"""
    return {
        category_id: {
            'name': meta['name'],
            'icon': meta.get('icon') or _DEFAULT_ICON,
            'color': meta.get('color') or _DEFAULT_COLOR,
        }
        for category_id, meta in CATEGORY_MAP.items()
    }


def load_category_meta() -> dict:
    """返回 {category_id: {'name', 'icon', 'color'}}，静态预设 + 数据库自定义。

    ★ 数据库里已删除/不存在的分类不会污染结果：静态预设始终保底。
    """
    try:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached
    except Exception:  # 缓存不可用时不能影响主流程
        pass

    meta = _static_meta()
    try:
        # 延迟导入：domain 层可能在 App 注册表就绪前被引用
        from apps.ledger.models import Category

        for row in Category.objects.all().values('id', 'name', 'icon', 'color'):
            meta[row['id']] = {
                'name': row['name'] or row['id'],
                'icon': row['icon'] or _DEFAULT_ICON,
                'color': row['color'] or _DEFAULT_COLOR,
            }
    except Exception:
        return _static_meta()

    try:
        cache.set(CACHE_KEY, meta, CACHE_TTL)
    except Exception:
        pass
    return meta


def invalidate_category_meta() -> None:
    """分类被新增/修改后调用，让下一次读取重新拉库。"""
    try:
        cache.delete(CACHE_KEY)
    except Exception:
        pass
