const api = require('../../utils/api')
const { requireLogin } = require('../../utils/request')
const { yuan } = require('../../utils/money')

const TYPES = [
  { key: 'expense', label: '支出' },
  { key: 'income', label: '收入' },
]
const FREQ = [
  { key: 'daily', label: '每天' },
  { key: 'weekly', label: '每周' },
  { key: 'monthly', label: '每月' },
]
const WEEK = [
  { v: 0, label: '周一' },
  { v: 1, label: '周二' },
  { v: 2, label: '周三' },
  { v: 3, label: '周四' },
  { v: 4, label: '周五' },
  { v: 5, label: '周六' },
  { v: 6, label: '周日' },
]

function money(cents) {
  return yuan(cents || 0).toFixed(2)
}

function today() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

Page({
  data: {
    TYPES,
    FREQ,
    WEEK,

    loading: true,
    items: [],

    // 表单弹窗
    showForm: false,
    saving: false,
    editingId: '',
    form: {
      name: '',
      type: 'expense',
      amount: '',
      account: '',
      category: '',
      merchant: '',
      frequency: 'monthly',
      interval: 1,
      weekday: 0,
      day_of_month: 1,
      start_date: '',
      end_date: '',
      is_private: false,
    },
    needWeekday: false,
    needMonthDay: true,
    accounts: [],
    accountIndex: 0,
    accountLabel: '不指定',
    categories: [],
    categoryIndex: 0,
    categoryLabel: '自动匹配',
  },

  onShow() {
    this.load()
  },

  /** 关闭后弹回详情页（小程序选中的「我的」入口对应 mine） */
  onClose() {
    wx.navigateBack({ delta: 1, fail: () => wx.switchTab({ url: '/pages/mine/mine' }) })
  },

  // ---------- 加载
  async loadMeta() {
    try {
      const [a, c] = await Promise.all([
        api.accounts(),
        api.categories(this.data.form.type),
      ])
      const accs = a.items || a || []
      const cats = c.items || c || []
      // 注入"不指定"占位
      const accList = [{ id: '', name: '不指定', icon: '' }, ...accs]
      const catList = [{ id: '', name: '自动匹配', icon: '' }, ...cats]
      const accId = this.data.form.account || ''
      const catId = this.data.form.category || ''
      this.setData({
        accounts: accList,
        categories: catList,
        accountIndex: Math.max(
          0,
          accList.findIndex((x) => x.id === accId),
        ),
        categoryIndex: Math.max(
          0,
          catList.findIndex((x) => x.id === catId),
        ),
        accountLabel: (accList.find((x) => x.id === accId) || accList[0]).name,
        categoryLabel: (catList.find((x) => x.id === catId) || catList[0]).name,
      })
    } catch (e) {
      this.setData({ accounts: [], categories: [] })
    }
  },

  async load() {
    this.setData({ loading: true })
    try {
      const list = await api.recurringList()
      const items = (list || []).map((r) => ({
        ...r,
        amountText: money(r.amount_cents),
      }))
      this.setData({ items })
    } catch (e) {
      if (requireLogin(e)) {
        wx.navigateBack({ delta: 1 })
        return
      }
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  // ---------- 表单
  async openCreate() {
    this.setData({
      showForm: true,
      saving: false,
      editingId: '',
      form: {
        name: '',
        type: 'expense',
        amount: '',
        account: '',
        category: '',
        merchant: '',
        frequency: 'monthly',
        interval: 1,
        weekday: 0,
        day_of_month: 1,
        start_date: today(),
        end_date: '',
        is_private: false,
      },
    })
    this.refreshFreqFlags()
    // 先拉账户/分类，再按 H5 口径把账户默认选中第一个
    await this.loadMeta()
    const list = this.data.accounts || []
    const first = list.find((a) => a.id)
    if (first) {
      this.setData({
        'form.account': first.id,
        accountIndex: list.indexOf(first),
        accountLabel: first.name,
      })
    }
  },

  async openEdit(e) {
    const id = e.currentTarget.dataset.id
    const r = this.data.items.find((x) => x.id === id)
    if (!r) return
    this.setData({
      showForm: true,
      saving: false,
      editingId: id,
      form: {
        name: r.name || '',
        type: r.type,
        amount: String(r.amount),
        account: r.account_id || '',
        category: r.category_id || '',
        merchant: r.merchant || '',
        frequency: r.frequency,
        interval: r.interval || 1,
        weekday: r.weekday == null ? 0 : r.weekday,
        day_of_month: r.day_of_month || 1,
        start_date: r.start_date,
        end_date: r.end_date || '',
        is_private: !!r.is_private,
      },
    })
    this.refreshFreqFlags()
    await this.loadMeta()
  },

  closeForm() {
    this.setData({ showForm: false })
  },

  refreshFreqFlags() {
    const f = this.data.form.frequency
    this.setData({
      needWeekday: f === 'weekly',
      needMonthDay: f === 'monthly',
    })
  },

  onTypeChange(e) {
    this.setData({ 'form.type': e.currentTarget.dataset.key, 'form.category': '' })
    this.refreshFreqFlags()
    this.loadMeta() // 收入/支出对应不同分类，重新拉取
  },

  onFreqChange(e) {
    this.setData({ 'form.frequency': e.currentTarget.dataset.key })
    this.refreshFreqFlags()
  },

  onWeekdayChange(e) {
    this.setData({ 'form.weekday': Number(e.currentTarget.dataset.v) })
  },

  onField(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`form.${field}`]: e.detail.value })
  },

  onDate(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`form.${field}`]: e.detail.value })
  },

  onAccount(e) {
    const idx = Number(e.detail.value)
    const acc = this.data.accounts[idx]
    if (!acc) return
    this.setData({
      accountIndex: idx,
      accountLabel: acc.name,
      'form.account': acc.id,
    })
  },

  onCategory(e) {
    const idx = Number(e.detail.value)
    const cat = this.data.categories[idx]
    if (!cat) return
    this.setData({
      categoryIndex: idx,
      categoryLabel: cat.name,
      'form.category': cat.id,
    })
  },

  onPrivateChange(e) {
    this.setData({ 'form.is_private': !!e.detail.value })
  },

  async onSubmit() {
    if (this.data.saving) return
    const f = this.data.form
    if (!f.name.trim()) {
      wx.showToast({ title: '请填写规则名称', icon: 'none' })
      return
    }
    const amt = Number(f.amount)
    if (!amt || amt <= 0) {
      wx.showToast({ title: '请输入金额', icon: 'none' })
      return
    }
    const data = {
      name: f.name.trim(),
      type: f.type,
      amount: f.amount,
      account: f.account || null,
      category: f.category || null,
      merchant: f.merchant || '',
      frequency: f.frequency,
      interval: Number(f.interval) || 1,
      start_date: f.start_date,
      end_date: f.end_date || null,
      is_private: !!(f.is_private && f.type === 'expense'),
    }
    if (f.frequency === 'weekly') data.weekday = Number(f.weekday)
    if (f.frequency === 'monthly') data.day_of_month = Number(f.day_of_month)

    this.setData({ saving: true })
    try {
      if (this.data.editingId) {
        await api.recurringUpdate(this.data.editingId, data)
        wx.showToast({ title: '已更新规则', icon: 'success' })
      } else {
        await api.recurringCreate(data)
        wx.showToast({ title: '已创建规则', icon: 'success' })
      }
      this.setData({ showForm: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  // ---------- 列表操作
  async onToggle(e) {
    const id = e.currentTarget.dataset.id
    const r = this.data.items.find((x) => x.id === id)
    if (!r) return
    try {
      await api.recurringUpdate(id, { is_active: !r.is_active })
      await this.load()
    } catch (err) {
      wx.showToast({ title: err.message || '操作失败', icon: 'none' })
    }
  },

  async onRunNow(e) {
    const id = e.currentTarget.dataset.id
    try {
      const res = await api.recurringRun(id)
      wx.showToast({ title: (res && res.message) || '已记一笔', icon: 'success' })
      await this.load()
    } catch (err) {
      wx.showToast({ title: err.message || '执行失败', icon: 'none' })
    }
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '删除规则',
      content: '删除后该定时规则不再生成流水，已有流水不受影响。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.recurringRemove(id)
          wx.showToast({ title: '已删除规则', icon: 'success' })
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' })
        }
      },
    })
  },
})