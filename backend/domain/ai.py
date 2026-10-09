# -*- coding: utf-8 -*-
"""大模型增强分析（可选能力，默认关闭）。

★ 配置优先级：界面保存的 AISettings（存库、即时生效）> backend/.env。
  两处都没有可用 Key 时，报告页的「智能分析」回落本地规则引擎，功能不受影响。

★ 分工：AI 只负责「表达与补充」，绝不负责「事实计算」。
  - 事实（金额、占比、环比、健康分）一律来自本地规则引擎 domain.insight.analyze；
    模型拿到的是已算好的数字，从源头杜绝编造金额。
  - 调用失败 / 超时 / 返回非法 JSON → 一律回落本地分析，并在 reason 里写明原因。
  - 结果按家庭 + 区间 + 模型缓存，避免同一份分析反复烧 token。

接入方式：兼容 OpenAI 的 /chat/completions 协议（DeepSeek、通义、Moonshot、本地 vLLM/Ollama 均可）。
"""
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

LEVELS = ('good', 'info', 'warn', 'danger')
MAX_INSIGHTS = 6


def get_config(family=None) -> dict:
    """取当前生效的 AI 配置：界面配置优先，其次 .env 默认值。"""
    base = {
        'enabled': bool(getattr(settings, 'AI_ENABLED', False)),
        'provider': 'deepseek',
        'base_url': getattr(settings, 'AI_BASE_URL', '') or '',
        'model': getattr(settings, 'AI_MODEL', '') or '',
        'api_key': getattr(settings, 'AI_API_KEY', '') or '',
        'timeout': int(getattr(settings, 'AI_TIMEOUT', 20) or 20),
        'max_tokens': int(getattr(settings, 'AI_MAX_TOKENS', 900) or 900),
        'cache_ttl': int(getattr(settings, 'AI_CACHE_TTL', 900) or 900),
        'source': 'env',
    }
    if family is None:
        return base
    from apps.ledger.models import AISettings  # 局部导入，避免模块级循环依赖
    row = AISettings.objects.filter(family=family).first()
    if row is None:
        return base
    base.update({
        'enabled': bool(row.enabled),
        'provider': row.provider or 'deepseek',
        'base_url': (row.base_url or '').strip(),
        'model': (row.model or '').strip(),
        'api_key': (row.api_key or '').strip(),
        'source': 'ui',
    })
    return base


def is_usable(cfg: dict) -> bool:
    """配置是否真的可用：开关打开 + Key + 接口地址 + 模型名齐备。"""
    return bool(cfg.get('enabled') and cfg.get('api_key')
                and cfg.get('base_url') and cfg.get('model'))


def ai_available(family=None) -> bool:
    return is_usable(get_config(family))


def model_name(family=None) -> str:
    return get_config(family)['model']


def _yuan(cents) -> float:
    return round(int(cents or 0) / 100.0, 2)


def build_facts(*, tx_type, days, range_text, summary, categories, prev_summary,
                by_member, top_txs, quality, local) -> dict:
    """把本地已算好的数据压成给模型的「事实包」。

    ★ 脱敏：不发送具体商户名等可识别信息，只给分类、金额、笔数这类统计口径。
    """
    income = int(summary.get('income_cents') or 0)
    expense = int(summary.get('expense_cents') or 0)
    prev_expense = int(prev_summary.get('expense_cents') or 0)
    mom = None
    if tx_type == 'expense' and prev_expense > 0 and expense > 0:
        mom = round((expense - prev_expense) / prev_expense * 100, 1)

    return {
        '统计区间': range_text,
        '天数': days,
        '分析口径': '支出' if tx_type == 'expense' else '收入',
        '收入_元': _yuan(income),
        '支出_元': _yuan(expense),
        '结余_元': _yuan(income - expense),
        '储蓄率_百分比': summary.get('saving_rate') or 0,
        '笔数': summary.get('count') or 0,
        '日均_元': _yuan(int(summary.get('total_cents') or 0) / max(days, 1)),
        '上期支出_元': _yuan(prev_expense),
        '支出环比_百分比': mom,
        '分类TOP': [
            {'分类': c.get('name'), '金额_元': _yuan(c.get('amount_cents')),
             '占比_百分比': c.get('percent') or 0, '笔数': c.get('count') or 0}
            for c in (categories or [])[:6]
        ],
        '成员分布': [
            {'成员': m.get('name'), '金额_元': _yuan(m.get('amount_cents')),
             '占比_百分比': m.get('percent') or 0}
            for m in (by_member or [])[:5]
        ],
        '大额单笔': [
            {'金额_元': _yuan(t.get('amount_cents')), '日期': str(t.get('transaction_date') or '')[:10]}
            for t in (top_txs or [])[:3]
        ],
        '记账完整度': {
            '未分类_元': _yuan(quality.get('unclassified_cents')),
            '未指定账户_元': _yuan(quality.get('no_account_cents')),
        },
        '本地规则结论': {
            '健康分': local.get('score'),
            '等级': local.get('score_label'),
            '要点': [{'标题': i.get('title'), '依据': i.get('detail')}
                     for i in (local.get('insights') or [])[:8]],
        },
    }


def _build_prompt(facts: dict) -> str:
    return (
        '你是家庭记账应用的财务顾问。下面是一个家庭在某统计周期内【已经算好的真实数据】（JSON）。\n'
        '请严格基于这些事实给出分析，遵循：\n'
        '1. 只能使用 facts 中出现的数字，禁止编造、推算未给出的金额或比例；\n'
        '2. 只输出一个 JSON 对象，不要 Markdown 代码块、不要任何多余文字，结构如下：\n'
        '   {"summary_text": "一句话总体评价，60 字以内",\n'
        '    "insights": [{"title": "标题，含关键数字，20 字以内",\n'
        '                  "detail": "判断依据，必须引用具体金额或占比",\n'
        '                  "suggestion": "一条可执行的下一步动作",\n'
        '                  "level": "good|info|warn|danger",\n'
        '                  "icon": "一个 emoji"}]}\n'
        '3. insights 输出 3~6 条，按严重程度从高到低排序；\n'
        '4. 语气务实、不说空话，建议必须具体到「做什么、做多少」；\n'
        '5. 全程中文。\n\n'
        'facts = ' + json.dumps(facts, ensure_ascii=False)
    )


def _call_chat(cfg: dict, prompt: str, timeout=None) -> str:
    url = (cfg.get('base_url') or '').rstrip('/') + '/chat/completions'
    payload = {
        'model': cfg.get('model'),
        'messages': [
            {'role': 'system', 'content': '你是严谨的家庭财务顾问，只依据给定事实回答，输出合法 JSON。'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.3,
        'max_tokens': int(cfg.get('max_tokens') or 900),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + (cfg.get('api_key') or ''),
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout or int(cfg.get('timeout') or 20)) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content']


def test_connection(cfg: dict):
    """连通性自检：给「测试连接」按钮用，返回 (ok, message)。"""
    if not (cfg.get('base_url') and cfg.get('model') and cfg.get('api_key')):
        return False, '接口地址、模型名、API Key 都不能为空'
    try:
        content = _call_chat(cfg, '只回复两个字：正常', timeout=15)
        return True, '连接成功：' + (content or '').strip()[:40]
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read().decode('utf-8')[:180]
        except Exception:  # noqa: BLE001
            pass
        return False, 'HTTP %s %s' % (exc.code, detail)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:180]


def _parse(text: str):
    """从模型输出里抠出 JSON，容忍 ```json 围栏与前后废话。"""
    if not text:
        return '', []
    body = text.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)```', body, re.S)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find('{'), body.rfind('}')
    if start < 0 or end <= start:
        return '', []
    obj = json.loads(body[start:end + 1])

    summary_text = str(obj.get('summary_text') or '').strip()[:120]
    insights = []
    raw = obj.get('insights')
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get('title') or '').strip()
            if not title:
                continue
            level = str(item.get('level') or 'info').strip().lower()
            if level not in LEVELS:
                level = 'info'
            insights.append({
                'code': 'ai',
                'level': level,
                'icon': (str(item.get('icon') or '').strip() or '💡')[:4],
                'title': title[:60],
                'detail': str(item.get('detail') or '').strip()[:300],
                'suggestion': str(item.get('suggestion') or '').strip()[:300],
            })
            if len(insights) >= MAX_INSIGHTS:
                break
    return summary_text, insights


def run_ai_insight(local_result: dict, facts: dict, cache_key: str, cfg: dict = None):
    """在规则引擎结果之上做 AI 增强。

    返回 (result, ai_meta)。任何异常都回落 local_result，调用方无需 try。
    score / score_label / range / prev_range 始终采用本地计算值，不交给模型。
    """
    cfg = cfg or get_config()
    meta = {
        'enabled': is_usable(cfg),
        'used': False,
        'model': cfg.get('model') or '',
        'reason': '',
    }
    if not meta['enabled']:
        meta['reason'] = '未配置大模型'
        return local_result, meta

    cached = cache.get(cache_key)
    if cached:
        merged = dict(local_result)
        merged.update(cached)
        meta['used'] = True
        meta['reason'] = '缓存'
        return merged, meta

    try:
        summary_text, insights = _parse(_call_chat(cfg, _build_prompt(facts)))
        if not insights:
            meta['reason'] = '模型未返回可用洞察'
            return local_result, meta
        ai_part = {'summary_text': summary_text or local_result.get('summary_text') or '',
                   'insights': insights}
        cache.set(cache_key, ai_part, int(cfg.get('cache_ttl') or 900))
        merged = dict(local_result)
        merged.update(ai_part)
        meta['used'] = True
        return merged, meta
    except Exception as exc:  # noqa: BLE001 - 兜底回落的边界必须足够宽
        logger.warning('AI 分析失败，回落本地规则引擎: %s', exc)
        meta['reason'] = ('AI 调用失败：%s' % exc)[:120]
        return local_result, meta
