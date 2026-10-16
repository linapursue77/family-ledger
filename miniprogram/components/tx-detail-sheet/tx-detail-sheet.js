const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')

/**
 * 流水详情弹层：点首页账单条目弹出，展示一笔的完整信息，并可编辑 / 删除。
 *
 * 借贷流水（loan_in / loan_out）后端禁止改删，这里也跟着禁用按钮并给出说明。
 */
Component({
  properties: {
    visible: { type: Boolean, value: false },
    // 只传 id 时组件自己拉详情；传 tx 时直接展示（省一次请求）
    txId: { type: String, value: '' },
    tx: { type: Object, value: null },
  },

  data: {
    detail: null,
    loading: false,
    deleting: false,
    isLoan: false,
    canEdit: false,
  },

  observers: {
    'visible, txId, tx': function (visible, txId, tx) {
      if (visible) {
        if (tx && tx.id) this.setData({ detail: this._decorate(tx), loading: false })
        else if (txId) this._load(txId)
      }
    },
  },

  methods: {
    async _load(id) {
      this.setData({ loading: true, detail: null })
      try {
        const d = await api.txDetail(id)
        this.setData({ detail: this._decorate(d), loading: false })
      } catch (e) {
        this.setData({ loading: false })
        if (requireLogin(e)) return
        wx.showToast({ title: e.message || '加载失败', icon: 'none' })
      }
    },

    /** 把后端字段整理成模板能直接用的展示值 */
    _decorate(t) {
      const isLoan = t.type === 'loan_in' || t.type === 'loan_out'
      const isIn = t.type === 'income' || t.type === 'loan_in'
      const amount = yuan(Number(t.amount_cents) || 0)
      return {
        ...t,
        isLoan,
        isIn,
        // 借贷流水后端禁止改删
        canEdit: !isLoan,
        typeText: isLoan ? '借钱来往' : isIn ? '收入' : '支出',
        amountText: (isIn ? '+' : '-') + amount.toFixed(2),
        dateText: (t.transaction_date || '').replace('T', ' ').slice(0, 16),
        accountText: (t.account && t.account.name) || '未指定账户',
        categoryText: isLoan ? '借钱来往' : (t.category && t.category.name) || '未分类',
        categoryIcon: isLoan ? '🤝' : (t.category && t.category.icon) || '💸',
        merchantText: t.merchant || '—',
        descText: t.description || '—',
        // 私密消费被脱敏时后端会把商户替换为占位文案
        privateText: t.is_private ? '是' : '否',
      }
    },

    onClose() {
      this.triggerEvent('close')
    },

    noop() {},

    onEdit() {
      const d = this.data.detail
      if (!d) return
      this.triggerEvent('edit', { id: d.id })
    },

    onDelete() {
      const d = this.data.detail
      if (!d) return
      wx.showModal({
        title: '删除这笔记录',
        content: `${d.categoryText} ${d.amountText}（${d.dateText}）\n删除后账户余额会自动冲正，无法恢复。`,
        confirmText: '删除',
        confirmColor: '#d03b3b',
        success: (res) => {
          if (res.confirm) this._doDelete(d.id)
        },
      })
    },

    async _doDelete(id) {
      this.setData({ deleting: true })
      try {
        await api.removeTx(id)
        wx.showToast({ title: '已删除', icon: 'success' })
        this.triggerEvent('deleted', { id })
        this.triggerEvent('close')
      } catch (e) {
        if (requireLogin(e)) return
        wx.showToast({ title: e.message || '删除失败', icon: 'none' })
      } finally {
        this.setData({ deleting: false })
      }
    },
  },
})
