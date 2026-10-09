# -*- coding: utf-8 -*-
"""分类体系：与 PRD 6.3 一致，是数据库种子数据的唯一来源。"""

EXPENSE_CATEGORIES = [
    {'id': 'food', 'name': '餐饮', 'icon': '🍜', 'color': '#E24B4A',
     'keywords': ['饿了么', '美团', '麦当劳', '肯德基', '瑞幸', '星巴克', '海底捞', '外卖', '午餐', '晚餐']},
    {'id': 'clothing', 'name': '服饰', 'icon': '👗', 'color': '#D4537E',
     'keywords': ['淘宝', '天猫', '唯品会', '京东', 'Nike', 'Adidas', '优衣库', '衣服', '裙子']},
    {'id': 'home', 'name': '居家', 'icon': '🏠', 'color': '#1D9E75',
     'keywords': ['超市', '菜市场', '京东超市', '天猫超市', '大润发', '永辉', '沃尔玛', '美团买菜']},
    {'id': 'transport', 'name': '出行', 'icon': '🚗', 'color': '#378ADD',
     'keywords': ['滴滴', '高德', '地铁', '公交', '停车', '加油', '打车', '高铁', '机票']},
    {'id': 'beauty', 'name': '美妆', 'icon': '💄', 'color': '#993556',
     'keywords': ['小红书', '丝芙兰', '屈臣氏', '化妆品', '护肤']},
    {'id': 'digital', 'name': '数码', 'icon': '📱', 'color': '#5C6BC0',
     'keywords': ['华为', '苹果', '小米', 'OPPO', 'vivo', '数码']},
    {'id': 'entertainment', 'name': '娱乐', 'icon': '🎮', 'color': '#7F77DD',
     'keywords': ['爱奇艺', '优酷', '腾讯视频', '网易云', 'QQ音乐', '游戏', '电影']},
    {'id': 'education', 'name': '教育', 'icon': '📚', 'color': '#F5A623',
     'keywords': ['学而思', '新东方', '猿辅导', '作业帮', '培训', '学费']},
    {'id': 'medical', 'name': '医疗', 'icon': '💊', 'color': '#26A69A',
     'keywords': ['药店', '医院', '挂号', '门诊']},
    {'id': 'gift', 'name': '礼物', 'icon': '🎁', 'color': '#EC407A', 'keywords': []},
    {'id': 'investment', 'name': '投资', 'icon': '📈', 'color': '#78909C',
     'keywords': ['基金', '理财', '股票']},
    {'id': 'other', 'name': '其他', 'icon': '💰', 'color': '#8D6E63', 'keywords': []},
]

INCOME_CATEGORIES = [
    {'id': 'salary', 'name': '工资', 'icon': '💼', 'color': '#1D9E75', 'keywords': ['工资', '薪水']},
    {'id': 'bonus', 'name': '奖金', 'icon': '🎁', 'color': '#F5A623', 'keywords': ['奖金', '年终奖']},
    {'id': 'freelance', 'name': '副业', 'icon': '💻', 'color': '#7F77DD', 'keywords': ['兼职', '外快']},
    {'id': 'investment_income', 'name': '投资收益', 'icon': '📈', 'color': '#26A69A',
     'keywords': ['收益', '股息', '利息', '余额宝', '零钱通', '理财通', '货币基金']},
    {'id': 'other_income', 'name': '其他收入', 'icon': '💰', 'color': '#8D6E63',
     'keywords': ['礼金', '退款']},
]

# 便捷索引
EXPENSE_IDS = {c['id'] for c in EXPENSE_CATEGORIES}
INCOME_IDS = {c['id'] for c in INCOME_CATEGORIES}
CATEGORY_MAP = {c['id']: c for c in EXPENSE_CATEGORIES + INCOME_CATEGORIES}


def all_categories():
    """返回 [(kind, category_dict)]，供种子数据使用。"""
    return ([('expense', c) for c in EXPENSE_CATEGORIES]
            + [('income', c) for c in INCOME_CATEGORIES])


def is_valid(category_id: str) -> bool:
    """校验分类 ID 合法性（LLM 返回结果的兜底校验）。"""
    return category_id in CATEGORY_MAP
