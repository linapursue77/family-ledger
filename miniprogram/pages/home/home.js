const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

const PRESETS = [
  { key: 'last_week', label: '近1周' },
  { key: 'last_month', label: '近1月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
  { key: 'last_year', label: '近一年' },
]

Page({
  data: {
    presets: PRESETS,
    activePreset: 'last_week',
    activePresetLabel: '近1周',
    showOptions: false,
    loading: true,
    ov: null,
    // 收支切换
    activeTab: 'expense',
    // 弹窗
    showAccounts: false,
    showCategory: false,
    activeCategory: null,
    categoryTxs: [],
    // 饼图（CSS conic-gradient）
    pieStyle: '',
    // 资产卡
    assetChange: '',
  },

  onShow() {
    this.loadAll()
  },

  async loadAll() {
    this.setData({ loading: true })
    try {
      const ov = await api.overview({ preset: this.data.activePreset })
      const label = (PRESETS.find((p) => p.key === this.data.activePreset) || {}).label || ''
      this.setData({ ov, activePresetLabel: label })
      this.buildPie(ov)
      this.setAssetChange(ov)
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  buildPie(ov) {
    const cats =
      this.data.activeTab === 'expense' ? ov.expense_categories : ov.income_categories
    if (!cats || !cats.length) {
      this.setData({ pieStyle: '' })
      return
    }
    let acc = 0
    const stops = cats
      .map((c) => {
        const from = acc
        acc += c.percent
        return `${c.color} ${from}% ${acc}%`
      })
      .join(',')
    this.setData({ pieStyle: `background: conic-gradient(${stops})` })
  },

  setAssetChange(ov) {
    const v = Number(ov.asset_change || 0)
    const sign = v >= 0 ? '+' : ''
    this.setData({ assetChange: `比上月 ${sign}¥${yuan(Math.abs(v)).toFixed(2)}` })
  },

  // ---- 时间控件
  toggleOptions() {
    this.setData({ showOptions: !this.data.showOptions })
  },
  onPreset(e) {
    const key = e.currentTarget.dataset.key
    const label = (PRESETS.find((p) => p.key === key) || {}).label || ''
    this.setData({ activePreset: key, activePresetLabel: label, showOptions: false })
    this.loadAll()
  },

  // ---- 收支切换
  onTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab })
    if (this.data.ov) this.buildPie(this.data.ov)
  },

  // ---- 账户弹窗
  openAccounts() {
    this.setData({ showAccounts: true })
    this.loadAccounts()
  },
  closeAccounts() {
    this.setData({ showAccounts: false })
  },
  async loadAccounts() {
    try {
      const d = await api.accounts()
      this.setData({ accounts: d.items || d || [] })
    } catch (e) {
      /* ignore */
    }
  },

  // ---- 分类明细弹窗
  async openCategory(e) {
    const cat = e.currentTarget.dataset.cat
    this.setData({ showCategory: true, activeCategory: cat, categoryTxs: [] })
    try {
      const data = await api.transactions({ category: cat.category_id, page_size: 20 })
      const items = data.items || data || []
      this.setData({
        categoryTxs: items.map((t) => ({
          ...t,
          amountText: (t.type === 'income' ? '+' : '-') + yuan(t.amount_cents).toFixed(2),
          dateText: (t.transaction_date || '').slice(0, 10),
        })),
      })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },
  closeCategory() {
    this.setData({ showCategory: false })
  },

  goAdd() {
    wx.switchTab({ url: '/pages/add/add' })
  },
})