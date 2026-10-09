# -*- coding: utf-8 -*-
"""账单智能分析（本地规则引擎）。

★ 纯本地计算，不依赖外部大模型：数据不出服务、零延迟、结果可复现。
  后续若要接入 LLM，只需把 analyze() 的入参（事实数据）交给模型润色文案，
  这里的规则结果仍可作为兜底与事实校验。

设计原则：
- 每条洞察都必须「有数有据」：detail 里带真实金额/占比，不说空话。
- 每条洞察都给可执行建议（suggestion），而不是只指出问题。
- 样本不足时不做过度解读，直接提示样本太少。
"""
from domain.money import safe_pct, yuan

EXPENSE = 'expense'
INCOME = 'income'

LEVEL_ORDER = {'danger': 0, 'warn': 1, 'info': 2, 'good': 3}


def _c(v) -> int:
    return int(v or 0)


def _y(cents) -> str:
    """分 → 元字符串，与聚合层保持同一格式化口径。"""
    return yuan(_c(cents))


def _score_label(score: int) -> str:
    if score >= 85:
        return '优秀'
    if score >= 70:
        return '良好'
    if score >= 55:
        return '一般'
    if score >= 40:
        return '需关注'
    return '警戒'


def _health_score(saving_rate, change_pct, noise_pct, top1_pct) -> int:
    """财务健康分（0~100）：储蓄率 40 + 环比控制 25 + 记账完整度 15 + 结构均衡 20。"""
    if saving_rate >= 30:
        s1 = 40
    elif saving_rate >= 20:
        s1 = 34
    elif saving_rate >= 10:
        s1 = 27
    elif saving_rate >= 0:
        s1 = 18
    else:
        s1 = 6

    if change_pct is None:
        s2 = 18
    elif change_pct <= -10:
        s2 = 25
    elif change_pct <= 0:
        s2 = 22
    elif change_pct <= 10:
        s2 = 18
    elif change_pct <= 25:
        s2 = 12
    else:
        s2 = 6

    if noise_pct <= 3:
        s3 = 15
    elif noise_pct <= 10:
        s3 = 11
    elif noise_pct <= 25:
        s3 = 6
    else:
        s3 = 2

    if top1_pct <= 35:
        s4 = 20
    elif top1_pct <= 50:
        s4 = 15
    elif top1_pct <= 70:
        s4 = 9
    else:
        s4 = 4

    return max(0, min(100, s1 + s2 + s3 + s4))


def analyze(*, tx_type=EXPENSE, days=1, summary=None, categories=None,
            prev_summary=None, prev_categories=None, by_member=None,
            top_txs=None, quality=None) -> dict:
    """输出洞察 + 健康分。

    summary / prev_summary 需带 *_cents 字段；categories 需带 count。
    quality: {'unclassified_cents': int, 'no_account_cents': int}
    """
    summary = summary or {}
    categories = categories or []
    prev_summary = prev_summary or {}
    prev_categories = prev_categories or []
    by_member = by_member or []
    top_txs = top_txs or []
    quality = quality or {}

    days = max(int(days or 1), 1)
    total = _c(summary.get('total_cents'))
    income = _c(summary.get('income_cents'))
    expense = _c(summary.get('expense_cents'))
    count = int(summary.get('count') or 0)
    saving_rate = summary.get('saving_rate') or 0
    avg_daily = total / days if total else 0

    if count < 3 or total <= 0:
        return {
            'score': None,
            'score_label': '数据不足',
            'summary_text': '本区间流水太少，暂时无法给出可靠判断。',
            'insights': [{
                'code': 'sample',
                'level': 'info',
                'icon': '📊',
                'title': '样本太少，先多记几笔',
                'detail': f'本区间只有 {count} 笔记录。',
                'suggestion': '累计 10 笔以上后，环比趋势与预算建议会明显更准。',
            }],
        }

    insights = []

    # -------------------------------------------------- 1. 储蓄率 / 结余
    if income > 0:
        if saving_rate >= 30:
            level, icon = 'good', '🎉'
            detail = f'收入 {_y(income)} 元，结余 {_y(income - expense)} 元，储蓄率 {saving_rate}%。'
            suggestion = '保持当前节奏；可考虑把结余部分转入稳健理财或提前还款。'
        elif saving_rate >= 10:
            level, icon = 'info', '👍'
            detail = f'收入 {_y(income)} 元，结余 {_y(income - expense)} 元，储蓄率 {saving_rate}%。'
            suggestion = '距离 30% 的理想线还有空间，优先压降占比最高的那类支出。'
        elif saving_rate >= 0:
            level, icon = 'warn', '⚠️'
            detail = f'收入 {_y(income)} 元，结余仅 {_y(income - expense)} 元，储蓄率 {saving_rate}%。'
            suggestion = '结余偏薄，建议先盯住 Top2 分类，各压降 10% 试试。'
        else:
            level, icon = 'danger', '🚨'
            detail = f'本期入不敷出：支出比收入多 {_y(expense - income)} 元。'
            suggestion = '先排查大额单笔与非必要订阅，必要时动用储蓄账户前先做预算上限。'
        insights.append({
            'code': 'saving_rate',
            'level': level,
            'icon': icon,
            'title': f'储蓄率 {saving_rate}%',
            'detail': detail,
            'suggestion': suggestion,
        })

    # -------------------------------------------------- 2. 环比变化
    prev_expense = _c(prev_summary.get('expense_cents'))
    change_pct = None
    if tx_type == EXPENSE and prev_expense > 0 and expense > 0:
        change_pct = round((expense - prev_expense) / prev_expense * 100, 1)
        diff = abs(expense - prev_expense)
        if change_pct >= 25:
            insights.append({
                'code': 'mom_up',
                'level': 'warn',
                'icon': '📈',
                'title': f'支出环比上涨 {change_pct}%',
                'detail': f'上一周期支出 {_y(prev_expense)} 元，本期 {_y(expense)} 元，多花 {_y(diff)} 元。',
                'suggestion': '对照下方分类明细，找出增长最快的那一类重点控制。',
            })
        elif change_pct <= -15:
            insights.append({
                'code': 'mom_down',
                'level': 'good',
                'icon': '📉',
                'title': f'支出环比下降 {abs(change_pct)}%',
                'detail': f'上一周期支出 {_y(prev_expense)} 元，本期 {_y(expense)} 元，省下 {_y(diff)} 元。',
                'suggestion': '把省下的金额固定转入储蓄，避免下个周期反弹。',
            })
        else:
            insights.append({
                'code': 'mom_flat',
                'level': 'info',
                'icon': '➡️',
                'title': f'支出环比{("上升" if change_pct >= 0 else "下降")} {abs(change_pct)}%',
                'detail': f'上一周期支出 {_y(prev_expense)} 元，本期 {_y(expense)} 元。',
                'suggestion': '支出节奏稳定，继续保持即可。',
            })

    # -------------------------------------------------- 3. 分类集中度
    top1_pct = 0
    if categories:
        top = categories[0]
        top1_pct = top.get('percent') or 0
        if top1_pct >= 45:
            insights.append({
                'code': 'concentration',
                'level': 'info' if top1_pct < 65 else 'warn',
                'icon': '🎯',
                'title': f'{top.get("name")}占比 {top1_pct}%',
                'detail': f'该分类本期 {_y(top.get("amount_cents"))} 元、{top.get("count", 0)} 笔，是最大开销。',
                'suggestion': f'给「{top.get("name")}」设一个上限（建议按本期 x 0.9 = '
                              f'{_y(int(_c(top.get("amount_cents")) * 0.9))} 元），超支时及时预警。',
            })

    # -------------------------------------------------- 4. 分类环比飙升
    if tx_type == EXPENSE and prev_categories:
        prev_map = {c.get('category_id'): c for c in prev_categories}
        surges = []
        for cur in categories[:6]:
            prev = prev_map.get(cur.get('category_id'))
            prev_amt = _c((prev or {}).get('amount_cents'))
            cur_amt = _c(cur.get('amount_cents'))
            if prev_amt <= 0:
                # 上期完全没有、本期出现的新增大额分类
                if cur_amt >= total * 0.08:
                    surges.append((cur.get('name'), None, cur_amt))
                continue
            growth = (cur_amt - prev_amt) / prev_amt * 100
            if growth >= 50 and (cur_amt - prev_amt) >= total * 0.05:
                surges.append((cur.get('name'), round(growth, 1), cur_amt))
        if surges:
            name, growth, amount = surges[0]
            if growth is None:
                detail = f'「{name}」上期无支出，本期新增 {_y(amount)} 元。'
                title = f'新增大额分类：{name}'
            else:
                detail = f'「{name}」本期 {_y(amount)} 元，较上期增长 {growth}%。'
                title = f'{name}增长 {growth}%'
            insights.append({
                'code': 'category_surge',
                'level': 'warn',
                'icon': '🔥',
                'title': title,
                'detail': detail,
                'suggestion': '确认是一次性支出还是趋势性上涨；若是趋势，尽快给它设预算。',
            })

    # -------------------------------------------------- 5. 高频小额
    if tx_type == EXPENSE and categories:
        small = [c for c in categories
                 if (c.get('count') or 0) >= 8 and _c(c.get('amount_cents')) > 0
                 and _c(c.get('amount_cents')) / max(c.get('count') or 1, 1) < avg_daily * 0.6]
        if small:
            s = max(small, key=lambda c: c.get('count') or 0)
            per = _c(s.get('amount_cents')) / max(s.get('count') or 1, 1)
            insights.append({
                'code': 'small_frequent',
                'level': 'info',
                'icon': '☕',
                'title': f'{s.get("name")}高频小额：{s.get("count")} 笔',
                'detail': f'共 {_y(s.get("amount_cents"))} 元，单笔平均 {_y(int(per))} 元。',
                'suggestion': '小额最容易被忽略，建议设「每周次数上限」，比设金额上限更容易执行。',
            })

    # -------------------------------------------------- 6. 大额单笔
    if tx_type == EXPENSE and top_txs and avg_daily > 0:
        big = [t for t in top_txs if _c(t.get('amount_cents')) >= avg_daily * 3]
        if big:
            b = big[0]
            insights.append({
                'code': 'big_tx',
                'level': 'info',
                'icon': '💸',
                'title': f'单笔大额：{_y(b.get("amount_cents"))} 元',
                'detail': f'{b.get("merchant") or b.get("name") or "一笔支出"}'
                          f'（{str(b.get("transaction_date") or "")[:10]}），'
                          f'相当于 {round(_c(b.get("amount_cents")) / avg_daily, 1)} 天的平均支出。',
                'suggestion': '大额支出建议提前报备家庭预算，避免月末才发现超支。',
            })

    # -------------------------------------------------- 7. 记账质量
    unclassified = _c(quality.get('unclassified_cents'))
    no_account = _c(quality.get('no_account_cents'))
    noise = unclassified + no_account
    noise_pct = safe_pct(noise, total)
    if noise_pct >= 10:
        parts = []
        if unclassified:
            parts.append(f'未分类 {_y(unclassified)} 元')
        if no_account:
            parts.append(f'未指定账户 {_y(no_account)} 元')
        insights.append({
            'code': 'data_quality',
            'level': 'warn' if noise_pct >= 25 else 'info',
            'icon': '🧹',
            'title': f'记账完整度偏低（{noise_pct}%）',
            'detail': '、'.join(parts) + '，这部分金额无法参与分类与账户分析。',
            'suggestion': '补上分类和账户后，报告里的占比与建议会更准确。',
        })

    # -------------------------------------------------- 8. 成员分布
    if len(by_member) >= 2:
        m = by_member[0]
        if (m.get('percent') or 0) >= 70:
            insights.append({
                'code': 'member_skew',
                'level': 'info',
                'icon': '👥',
                'title': f'{m.get("name")}承担了 {m.get("percent")}%',
                'detail': f'本期该成员 {_y(m.get("amount_cents"))} 元，分布明显集中。',
                'suggestion': '可以约定共同支出（如日用、餐饮）轮流记账，便于家庭预算分摊。',
            })

    # -------------------------------------------------- 9. 预算建议（收尾必给）
    if tx_type == EXPENSE and avg_daily > 0:
        monthly = int(avg_daily * 30)
        insights.append({
            'code': 'budget',
            'level': 'info',
            'icon': '🎯',
            'title': f'下月预算建议 {_y(monthly)} 元',
            'detail': f'按本期日均 {_y(int(avg_daily))} 元外推 30 天得出。',
            'suggestion': (f'其中「{categories[0].get("name")}」建议不超过 '
                           f'{_y(int(_c(categories[0].get("amount_cents")) * 0.9))} 元。')
            if categories else '先给占比最高的分类设上限，再逐步细化。',
        })

    insights.sort(key=lambda x: LEVEL_ORDER.get(x.get('level'), 9))
    score = _health_score(saving_rate, change_pct, noise_pct, top1_pct)
    warn_count = sum(1 for i in insights if i['level'] in ('warn', 'danger'))

    if warn_count == 0:
        summary_text = f'本期健康分 {score} 分（{_score_label(score)}），没有明显异常，保持当前节奏即可。'
    else:
        summary_text = (f'本期健康分 {score} 分（{_score_label(score)}），'
                        f'发现 {warn_count} 项需要关注的问题，优先处理排在最前面的。')

    return {
        'score': score,
        'score_label': _score_label(score),
        'summary_text': summary_text,
        'insights': insights,
    }
