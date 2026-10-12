# -*- coding: utf-8 -*-
"""账单导入冒烟测试。

用法（先启动后端）：
    python manage.py runserver 8001 --noreload
    python scripts/smoke_import.py [base_url]

覆盖：微信(UTF-8 BOM) / 支付宝(GBK) 解析 → 去重打标 → 自动分类 → 确认入库 → 重复上传识别
"""
import sys

import requests

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8001'
API = f'{BASE}/api/v1'

PHONE = '13800138000'
PASSWORD = 'test123456'

WECHAT_CSV = """微信支付账单明细
微信昵称：[小林]
起始日期：2026-09-01 终止日期：2026-09-30
导出类型：全部
导出时间：2026-10-01 10:00:00

共 6 笔记录

----------------------微信支付账单明细列表--------------------
交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注
2026-09-02 08:30:00,商户消费,瑞幸咖啡,拿铁,支出,¥35.50,招商银行(1234),支付成功,42000001,1001,
2026-09-03 12:10:00,商户消费,美团外卖,午餐,支出,¥48.00,零钱,支付成功,42000002,1002,工作餐
2026-09-05 19:20:00,商户消费,优衣库,衬衫,支出,¥299.00,招商银行(1234),支付成功,42000003,1003,
2026-09-08 09:00:00,转账,小陈,生活费,支出,¥2000.00,零钱,支付成功,42000004,1004,家庭开销
2026-09-10 10:00:00,工资,某某公司,9月工资,收入,¥15000.00,招商银行(1234),已存入零钱,42000005,1005,
2026-09-12 15:00:00,商户消费,京东商城,退货,支出,¥88.00,零钱,已全额退款,42000006,1006,退款不计
"""

ALIPAY_CSV = """支付宝交易明细
账号：[laogong@example.com]
起始日期：2026-09-01 终止日期：2026-09-30
---------------------------------
交易号,商家订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,交易对方,商品名称,金额（元）,收/支,交易状态,服务费（元）,成功退款（元）,备注,资金状态
202609150001,M001,2026-09-15 12:00:00,2026-09-15 12:00:05,2026-09-15 12:00:05,支付宝网站,即时到账,沃尔玛,日用品,199.80,支出,交易成功,0.00,0.00,,已支出
202609160002,M002,2026-09-16 18:30:00,2026-09-16 18:30:10,2026-09-16 18:30:10,支付宝网站,即时到账,中石化加油卡,加油,300.00,支出,交易成功,0.00,0.00,,已支出
202609180003,M003,2026-09-18 09:00:00,2026-09-18 09:00:02,2026-09-18 09:00:02,支付宝网站,即时到账,余额宝,收益,12.35,收入,交易成功,0.00,0.00,,已收入
202609200004,M004,2026-09-20 10:00:00,2026-09-20 10:00:01,2026-09-20 10:00:01,支付宝网站,即时到账,某商户,测试,50.00,支出,交易关闭,0.00,0.00,,已支出
"""


def call(method, path, token=None, **kwargs):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    resp = requests.request(method, f'{API}{path}', headers=headers, timeout=30, **kwargs)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {'raw': resp.text[:300]}


def as_list(payload):
    """兼容 list / 分页信封({'items'|'results'}) 两种返回。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get('items') or payload.get('results') or []
    return []


def upload(token, filename, content: bytes, platform):
    return call('POST', '/ledger/imports/', token,
                files={'file': (filename, content, 'text/csv')},
                data={'platform': platform})


def main():
    print('=' * 70)
    print('钱来钱往记账 · 账单导入冒烟')
    print('=' * 70)

    _, body = call('POST', '/auth/login/', json={'phone': PHONE, 'password': PASSWORD})
    token = body['data']['token']['access']
    print(f'[登录] code={body.get("code")}')

    # 账户
    _, body = call('GET', '/accounts/', token)
    accounts = as_list(body.get('data'))
    if accounts:
        account_id = accounts[0]['id']
    else:
        _, body = call('POST', '/accounts/', token, json={
            'name': '支付宝', 'type': 'personal', 'book_type': 'husband',
            'balance': '10000.00', 'bank_name': '支付宝'})
        account_id = body['data']['id']
    print(f'[账户] {account_id}')

    # ---- 1. 微信账单（UTF-8 BOM）
    code, body = upload(token, 'wechat.csv',
                        b'\xef\xbb\xbf' + WECHAT_CSV.encode('utf-8'), 'wechat')
    data = body.get('data') or {}
    stats = data.get('stats') or {}
    print(f'[{code}] 微信解析: 编码={data.get("encoding")} 平台={data.get("task", {}).get("platform")}')
    print(f'        统计={stats}')
    print(f'        跳过(退款/不计收支)={[s["reason"] for s in (data.get("skipped") or [])]}')
    for row in (data.get('rows') or [])[:4]:
        print(f'        {row["date"]} {row["type"]} {row["amount_cents"]}分 '
              f'{row["merchant"]} → {row["category"]}({row["category_source"]}) '
              f'status={row["status"]}')
    task_id = (data.get('task') or {}).get('id')

    # ---- 2. 确认导入
    code, body = call('POST', f'/ledger/imports/{task_id}/confirm/', token,
                      json={'account_id': account_id})
    data = body.get('data') or {}
    print(f'[{code}] 确认导入: {body.get("message")} 新增={data.get("created")} '
          f'收入={data.get("income")} 支出={data.get("expense")} 余额变动={data.get("balance_delta")}')

    # ---- 3. 重复上传同一文件 → 应全部识别为重复
    code, body = upload(token, 'wechat.csv',
                        b'\xef\xbb\xbf' + WECHAT_CSV.encode('utf-8'), 'wechat')
    stats = (body.get('data') or {}).get('stats') or {}
    print(f'[{code}] 重复上传: {stats} '
          f'→ {"✅ 去重生效" if stats.get("new") == 0 and stats.get("duplicate") else "❌ 未识别重复"}')
    dup_task = (body.get('data') or {}).get('task', {}).get('id')

    # ---- 4. 支付宝账单（GBK）
    code, body = upload(token, 'alipay.csv', ALIPAY_CSV.encode('gbk'), None)
    data = body.get('data') or {}
    stats = data.get('stats') or {}
    print(f'[{code}] 支付宝解析(自动识别): 编码={data.get("encoding")} '
          f'平台={data.get("task", {}).get("platform")}')
    print(f'        统计={stats}')
    for row in (data.get('rows') or [])[:4]:
        print(f'        {row["date"]} {row["type"]} {row["amount_cents"]}分 '
              f'{row["merchant"]} → {row["category"]}({row["category_source"]})')
    task_id = (data.get('task') or {}).get('id')

    code, body = call('POST', f'/ledger/imports/{task_id}/confirm/', token,
                      json={'account_id': account_id})
    data = body.get('data') or {}
    print(f'[{code}] 确认导入: {body.get("message")} 新增={data.get("created")}')

    # ---- 5. 重复确认应被拒绝
    code, body = call('POST', f'/ledger/imports/{task_id}/confirm/', token,
                      json={'account_id': account_id})
    print(f'[{code}] 重复确认: code={body.get("code")} msg={body.get("message")} '
          f'→ {"✅ 幂等拦截" if body.get("code") != 0 else "❌ 重复写入"}')

    # ---- 6. 流水核对
    _, body = call('GET', '/ledger/transactions/?date_from=2026-09-01', token)
    items = (body.get('data') or {}).get('items') or []
    print(f'[核对] 9月流水 {len(items)} 条，来源分布='
          f'{{"wechat": {sum(1 for t in items if t["source"] == "wechat")}, '
          f'"alipay": {sum(1 for t in items if t["source"] == "alipay")}}}')

    # 清理未导入的重复任务
    call('DELETE', f'/ledger/imports/{dup_task}/', token)
    print('=' * 70)
    print('导入冒烟完成。')
    print('=' * 70)


if __name__ == '__main__':
    main()
