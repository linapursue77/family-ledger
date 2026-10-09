const api = require('../../utils/api')

Page({
  data: {
    types: [
      { key: 'expense', label: '支出' },
      { key: 'income', label: '收入' },
    ],
    activeType: 'expense',
    categories: [],
    accounts: [],
    accountIndex: -1,
    amount: '',
    categoryId: '',
    merchant: '',
    description: '',
    isPrivate: false,
    saving: false,
  },

  onShow() {
    this.loadCategories()
    this.loadAccounts()
  },

  async loadCategories() {
    try {
      const d = await api.categories(this.data.activeType)
      this.setData({ categories: d.items || d || [] })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },

  async loadAccounts() {
    try {
      const d = await api.accounts()
      this.setData({ accounts: d.items || d || [] })
    } catch (e) {
      /* 忽略 */
    }
  },

  onType(e) {
    this.setData({ activeType: e.currentTarget.dataset.key, categoryId: '' })
    this.loadCategories()
  },
  onAmount(e) {
    this.setData({ amount: e.detail.value })
  },
  onCategory(e) {
    this.setData({ categoryId: e.currentTarget.dataset.id })
  },
  onMerchant(e) {
    this.setData({ merchant: e.detail.value })
  },
  onDesc(e) {
    this.setData({ description: e.detail.value })
  },
  onPrivate(e) {
    this.setData({ isPrivate: e.detail.value })
  },
  onAccount(e) {
    this.setData({ accountIndex: Number(e.detail.value) })
  },

  async onSave() {
    const amount = Number(this.data.amount)
    if (!amount || amount <= 0) {
      wx.showToast({ title: '请输入金额', icon: 'none' })
      return
    }
    if (!this.data.categoryId) {
      wx.showToast({ title: '请选择分类', icon: 'none' })
      return
    }
    const account =
      this.data.accountIndex >= 0 ? this.data.accounts[this.data.accountIndex].id : null
    this.setData({ saving: true })
    try {
      const res = await api.createTx({
        type: this.data.activeType,
        amount: String(amount),
        account,
        category: this.data.categoryId,
        merchant: this.data.merchant,
        description: this.data.description,
        is_private: this.data.isPrivate,
      })
      const t = res.threshold || {}
      const p = res.privacy || {}
      let msg = '已记账'
      if (t.action === 'notify') msg = '已记账，将通知对方'
      else if (t.action === 'approval') msg = '已记账，需对方审批'
      else if (t.action === 'joint') msg = '已记账，需共同决策'
      if (p && p.will_auto_public) msg = '已记账，超出隐私额度已计入共同支出'
      wx.showToast({ title: msg, icon: 'none' })
      this.setData({ amount: '', merchant: '', description: '', categoryId: '' })
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },
})