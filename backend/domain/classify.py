# -*- coding: utf-8 -*-
"""商户 → 分类匹配（规则引擎，第一级）。

设计要点：
1. 归一化：全角转半角、去空格、小写
2. 关键词按长度降序匹配，避免"京东"抢先命中"京东超市"
3. 用户自定义规则优先级最高（user_rules）
4. 未命中返回 'other'，交给 LLM 兜底（第二级）
"""
import unicodedata

from domain.categories import CATEGORY_MAP, is_valid

DEFAULT_CATEGORY = 'other'


def normalize(text: str) -> str:
    """归一化商户名：全角→半角、去空白、小写。"""
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', str(text))
    text = ''.join(text.split()).lower()
    return text


def build_keyword_index():
    """构建 [(keyword_norm, category_id)]，按关键词长度降序。"""
    pairs = []
    for category_id, meta in CATEGORY_MAP.items():
        for keyword in meta.get('keywords', []):
            pairs.append((normalize(keyword), category_id))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


_KEYWORD_INDEX = build_keyword_index()


def match_by_rules(merchant: str, user_rules: dict = None) -> str | None:
    """规则匹配。user_rules: {keyword_norm: category_id}，优先级最高。"""
    norm = normalize(merchant)
    if not norm:
        return None

    if user_rules:
        for keyword, category_id in user_rules.items():
            if normalize(keyword) and normalize(keyword) in norm and is_valid(category_id):
                return category_id

    for keyword, category_id in _KEYWORD_INDEX:
        if keyword and keyword in norm:
            return category_id
    return None


def classify(merchant: str, user_rules: dict = None,
             llm_fallback=None) -> tuple[str, str]:
    """两级分类。

    返回 (category_id, source)，source ∈ {'rule', 'user_rule', 'llm', 'default'}
    llm_fallback: 可选的可调用对象 fn(merchant) -> category_id | None
    """
    norm = normalize(merchant)
    if user_rules:
        for keyword, category_id in user_rules.items():
            if normalize(keyword) and normalize(keyword) in norm and is_valid(category_id):
                return category_id, 'user_rule'

    for keyword, category_id in _KEYWORD_INDEX:
        if keyword and keyword in norm:
            return category_id, 'rule'

    if llm_fallback:
        try:
            result = llm_fallback(merchant)
            if result and is_valid(result):
                return result, 'llm'
        except Exception:
            pass

    return DEFAULT_CATEGORY, 'default'
