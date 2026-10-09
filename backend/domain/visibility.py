# -*- coding: utf-8 -*-
"""可见性过滤 —— ★ 本项目最核心的安全层。

铁律：任何列表 / 聚合 / 导出 / 推送，都必须先过这里；
      渲染层永远不做权限判断，只渲染「已经被过滤过的数据」。
这样能保证「看到的合计」与「看到的明细」永远一致，且抓包也拿不到配偶隐私数据。
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 上下文


@dataclass
class ViewerCtx:
    """观看者上下文（由 token 解析，绝不接受前端传参）。"""

    viewer_id: str
    role: str = 'member'                 # owner | member
    permissions: dict = field(default_factory=dict)
    family_id: str = ''

    @property
    def is_owner(self) -> bool:
        return self.role == 'owner'

    def perm(self, key: str, default=None):
        return self.permissions.get(key, default)


# ---------------------------------------------------------------- 视图模型

MASK_TEXT = '🔐 私密消费'


@dataclass
class TxView:
    """出站交易视图。"""
    id: str = ''
    user_id: str = ''
    account_id: str = ''
    type: str = 'expense'
    amount_cents: int = 0
    category_id: str = ''
    merchant: str = ''
    description: str = ''
    is_private: bool = False
    transaction_date: str = ''
    source: str = 'manual'
    # 脱敏标记
    masked: bool = False            # 是否发生过脱敏
    amount_masked: bool = False     # 金额被隐藏
    merchant_masked: bool = False   # 商户被隐藏


def _get(obj, name, default=None):
    """兼容 model / dict / dataclass。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def to_transaction_view(tx, ctx: ViewerCtx):
    """单条交易 → 视图。返回 None 表示观看者无权看到（直接丢弃）。"""
    owner_id = str(_get(tx, 'user_id', '') or '')

    # 本人：全见
    if owner_id and owner_id == str(ctx.viewer_id):
        return _build(tx, masked=False)

    # 仅看自己账本的子账号：别人的一律不可见
    if not ctx.is_owner and ctx.perm('account_view') == 'own':
        return None

    is_private = bool(_get(tx, 'is_private', False))

    if is_private:
        # 未授权查看对方私密消费 → 完全不可见
        if not ctx.is_owner and not ctx.perm('show_private', False):
            return None
        # 授权了但只给总额：隐藏商户与备注
        return _build(tx, masked=True, merchant_masked=True,
                      merchant=MASK_TEXT, description='')

    # 标记了隐藏详情：仅见金额
    if bool(_get(tx, 'is_hidden', False)):
        return _build(tx, masked=True, merchant_masked=True,
                      merchant='', description='')

    return _build(tx, masked=False)


def filter_transactions(txs, ctx: ViewerCtx) -> list:
    """批量过滤。所有聚合计算的唯一入口。"""
    views = (to_transaction_view(tx, ctx) for tx in txs)
    return [v for v in views if v is not None]


def _build(tx, masked=False, merchant=None, description=None,
           merchant_masked=False, amount_masked=False) -> TxView:
    return TxView(
        id=str(_get(tx, 'id', '') or ''),
        user_id=str(_get(tx, 'user_id', '') or ''),
        account_id=str(_get(tx, 'account_id', '') or ''),
        type=_get(tx, 'type', 'expense') or 'expense',
        amount_cents=int(_get(tx, 'amount_cents', 0) or 0),
        category_id=_get(tx, 'category_id', '') or '',
        merchant=merchant if merchant is not None else (_get(tx, 'merchant', '') or ''),
        description=description if description is not None else (_get(tx, 'description', '') or ''),
        is_private=bool(_get(tx, 'is_private', False)),
        transaction_date=str(_get(tx, 'transaction_date', '') or ''),
        source=_get(tx, 'source', 'manual') or 'manual',
        masked=masked,
        merchant_masked=merchant_masked,
        amount_masked=amount_masked,
    )
