# -*- coding: utf-8 -*-
"""MVP 主链路冒烟测试。

用法（先启动后端）：
    python manage.py runserver 8001 --noreload
    python scripts/smoke.py [base_url]

覆盖：注册 → 登录 → 建账户 → 记账(收入/支出/大额/私密) → 首页聚合 → 列表脱敏
"""
import json
import sys

import requests

# Windows 控制台默认 GBK，显式切 UTF-8，否则 emoji 输出会崩
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8001'
API = f'{BASE}/api/v1'

PHONE = '13800138000'
PASSWORD = 'test123456'


def call(method, path, token=None, **kwargs):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    resp = requests.request(method, f'{API}{path}', headers=headers, timeout=15, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = {'raw': resp.text[:200]}
    return resp.status_code, body


def show(title, status, body):
    data = body.get('data') if isinstance(body, dict) else None
    brief = json.dumps(data, ensure_ascii=False)[:220] if data is not None else body
    print(f'[{status}] {title}: {brief}')
    return body


def main():
    print('=' * 70)
    print('家庭财务通 · MVP 主链路冒烟')
    print('=' * 70)

    # 0. 健康检查
    code, body = call('GET', '/core/health/')
    show('健康检查', code, body)

    # 1. 注册（已存在则直接登录）
    code, body = call('POST', '/auth/register/', json={
        'phone': PHONE, 'password': PASSWORD, 'nickname': '老公', 'book_type': 'husband',
    })
    if body.get('code') == 0:
        show('注册', code, body)
        token = body['data']['token']['access']
    else:
        show('注册(已存在，转登录)', code, body)
        code, body = call('POST', '/auth/login/', json={'phone': PHONE, 'password': PASSWORD})
        show('登录', code, body)
        token = body['data']['token']['access']

    # 2. 当前用户上下文
    code, body = call('GET', '/auth/me/', token)
    show('当前用户', code, body)

    # 3. 分类列表
    code, body = call('GET', '/ledger/categories/?kind=expense', token)
    if body.get('code') == 0:
        categories = (body.get('data') or {}).get('items') or []
        print(f'[{code}] 支出分类: {len(categories)} 个，'
              f'示例={[c["name"] for c in categories[:5]]}')
    else:
        show('支出分类(失败)', code, body)

    # 4. 建账户
    account_id = None
    code, body = call('POST', '/accounts/', token, json={
        'name': '支付宝', 'icon': '💰', 'type': 'personal',
        'book_type': 'husband', 'balance': '10000.00', 'bank_name': '支付宝',
    })
    show('新建账户', code, body)
    if body.get('code') == 0:
        account_id = body['data']['id']
    else:
        code, body = call('GET', '/accounts/', token)
        items = body.get('data') or []
        account_id = items[0]['id'] if items else None
        print(f'[{code}] 复用已有账户: {account_id}')

    # 5. 记一笔收入
    code, body = call('POST', '/ledger/transactions/', token, json={
        'type': 'income', 'amount': '15000.00', 'account': account_id,
        'category': 'salary', 'merchant': '公司', 'description': '9月工资',
    })
    show('记账-收入', code, body)

    # 6. 记一笔支出（不传分类 → 规则引擎自动识别"瑞幸咖啡" → 餐饮）
    code, body = call('POST', '/ledger/transactions/', token, json={
        'type': 'expense', 'amount': '35.50', 'account': account_id,
        'merchant': '瑞幸咖啡', 'description': '奶茶',
    })
    data = body.get('data') or {}
    tx = data.get('transaction') or {}
    print(f'[{code}] 记账-支出(自动分类): category={tx.get("category_id")} '
          f'source={data.get("category_source")} threshold={data.get("threshold")}')

    # 7. 大额支出（触发阈值：1500 元 → 事后知会）
    code, body = call('POST', '/ledger/transactions/', token, json={
        'type': 'expense', 'amount': '1500.00', 'account': account_id,
        'category': 'food', 'merchant': '海底捞', 'description': '家庭聚餐',
    })
    data = body.get('data') or {}
    print(f'[{code}] 记账-大额: threshold={(data.get("threshold") or {})}')

    # 8. 私密消费（199 元，额度 500 内）
    code, body = call('POST', '/ledger/transactions/', token, json={
        'type': 'expense', 'amount': '199.00', 'account': account_id,
        'category': 'clothing', 'merchant': '唯品会', 'is_private': True,
        'description': '私密',
    })
    data = body.get('data') or {}
    print(f'[{code}] 记账-私密: is_private={(data.get("transaction") or {}).get("is_private")} '
          f'privacy={data.get("privacy")}')

    # 9. 首页聚合
    code, body = call('GET', '/ledger/overview/?preset=this_year', token)
    if body.get('code') == 0:
        ov = body['data']
        print(f'[{code}] 首页聚合: 资产={ov["total_assets"]} 收入={ov["income"]} '
              f'支出={ov["expense"]} 结余={ov["balance"]} 储蓄率={ov["saving_rate"]}%')
        print(f'        支出TOP: {[(c["name"], c["amount"]) for c in ov["expense_categories"][:3]]}')
        print(f'        趋势月数: {len(ov["trend"])}')
    else:
        show('首页聚合', code, body)

    # 10. 流水列表（本人视角，私密可见）
    code, body = call('GET', '/ledger/transactions/', token)
    payload = body.get('data') or {}
    items = payload.get('items') or []
    print(f'[{code}] 流水列表: {len(items)} 条，分页={payload.get("pagination")}')
    if items:
        print(f'        首条: 商户={items[0]["merchant"]} 金额={items[0]["amount_cents"]}分 '
              f'分类={items[0]["category_id"]} 私密={items[0]["is_private"]} '
              f'脱敏={items[0]["masked"]}')

    # 11. ★ 配偶视角验证：私密消费必须不可见
    code, body = call('POST', '/auth/login/', json={'phone': '13800138001',
                                                    'password': 'test123456'})
    if body.get('code') == 0:
        spouse_token = body['data']['token']['access']
        _, mine = call('GET', '/ledger/transactions/', token)
        _, other = call('GET', '/ledger/transactions/', spouse_token)
        mine_items = (mine.get('data') or {}).get('items') or []
        other_items = (other.get('data') or {}).get('items') or []
        mine_private = sum(1 for t in mine_items if t['is_private'])
        other_private = sum(1 for t in other_items if t['is_private'])
        print(f'[{code}] 隐私脱敏: 本人可见 {len(mine_items)} 条(含私密 {mine_private}) / '
              f'配偶可见 {len(other_items)} 条(含私密 {other_private})')
        ok = len(other_items) < len(mine_items) and other_private == 0
        print(f'        结论: {"✅ 脱敏生效" if ok else "❌ 私密数据泄露！"}')
    else:
        print('[跳过] 配偶账号不存在，先执行: python manage.py seed_demo_family')

    print('=' * 70)
    print('冒烟完成。若以上均返回 200/201 且 code=0，则 MVP 主链路打通。')
    print('=' * 70)


if __name__ == '__main__':
    main()
