const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

const DIRECTIONS = [
  { value: '', label: '全部' },
  { value: 'lend', label: '借出' },
  { value: 'borrow', label: '借入' },
]
const STATES = [
  { value: '', label: '全部' },
  { value: 'pending', label: '未还' },
  { value: 'partial', label: '部分还' },
  { value: 'settled', label: '已结清' },
  { value: 'overdue', label: '已逾期' },
]

function money(cents) {
  return yuan(cents).toFixed(2)
}

function today() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

Page({
  data: {
    loading: true,
    directions: DIRECTIONS,
    states: STATES,
    dirIndex: 0,
    stateIndex: 0,
    keyword: '',
    items: [],
    summary: null,
    summaryText: {},

    // 新增借款
    showAdd: false,
    saving: false,
    form: {
      direction: 'lend',
      party: '',
      amount: '',
      loanDate: today(),
      dueDate: '',
      note: '',
    },

    // 还款
    showRepay: false,
    current: null,
    repayAmount: '',
    repayDate: today(),
    repayNote: '',
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const params = {}
      if (DIRECTIONS[this.data.dirIndex].value) params.direction = DIRECTIONS[this.data.dirIndex].value
      if (STATES[this.data.stateIndex].value) params.status = STATES[this.data.stateIndex].value
      if (this.data.keyword.trim()) params.q = this.data.keyword.trim()

      const data = await api.loans(params)
      const items = (data.items || []).map((l) => ({
        ...l,
        amountText: money(l.amount_cents),
        repaidText: money(l.repaid_cents),
        remainingText: money(l.remaining_cents),
        loanDateText: l.loan_date || '',
        dueText: l.due_date ? `约定 ${l.due_date}` : '未约定还款日',
        overdueText: l.overdue ? ' · 已逾期' : '',
        progress: l.amount_cents > 0
          ? Math.min(100, Math.round((l.repaid_cents / l.amount_cents) * 100))
          : 0,
        payments: (l.repayments || []).map((r) => ({
          ...r,
          amountText: money(r.amount_cents),
          dateText: r.repay_date || '',
        })),
      }))
      const s = data.summary || {}
      this.setData({
        items,
        summary: s,
        summaryText: {
          lend: money(s.lend_cents || 0),
          borrow: money(s.borrow_cents || 0),
          net: money(s.net_cents || 0),
        },
      })
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onDir(e) {
    this.setData({ dirIndex: Number(e.detail.value) })
    this.load()
  },
  onState(e) {
    this.setData({ stateIndex: Number(e.detail.value) })
    this.load()
  },
  onKeyword(e) {
    this.setData({ keyword: e.detail.value })
  },
  onSearch() {
    this.load()
  },

  // ---- 新增借款
  openAdd() {
    this.setData({
      showAdd: true,
      form: { direction: 'lend', party: '', amount: '', loanDate: today(), dueDate: '', note: '' },
    })
  },
  closeAdd() {
    this.setData({ showAdd: false })
  },
  setDirection(direction) {
    this.setData({ 'form.direction': direction })
  },
  onLend() {
    this.setDirection('lend')
  },
  onBorrow() {
    this.setDirection('borrow')
  },
  onField(e) {
    this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value })
  },
  onDate(e) {
    this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value })
  },

  async onSaveLoan() {
    if (this.data.saving) return
    const f = this.data.form
    const party = (f.party || '').trim()
    if (!party) return wx.showToast({ title: '请填写对方', icon: 'none' })
    if (!Number(f.amount)) return wx.showToast({ title: '请填写金额', icon: 'none' })
    if (f.dueDate && f.loanDate && f.dueDate < f.loanDate) {
      return wx.showToast({ title: '还款日不能早于借款日', icon: 'none' })
    }

    this.setData({ saving: true })
    try {
      await api.createLoan({
        direction: f.direction,
        party,
        amount: Number(f.amount),
        loan_date: f.loanDate || undefined,
        due_date: f.dueDate || undefined,
        note: (f.note || '').trim(),
      })
      wx.showToast({ title: '已记录', icon: 'success' })
      this.setData({ showAdd: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  // ---- 还款
  openRepay(e) {
    const loan = this.data.items.find((i) => i.id === e.currentTarget.dataset.id)
    if (!loan) return
    this.setData({
      showRepay: true,
      current: loan,
      // 默认按剩余待还预填，少一圈输入
      repayAmount: String(yuan(loan.remaining_cents)),
      repayDate: today(),
      repayNote: '',
    })
  },
  closeRepay() {
    this.setData({ showRepay: false })
  },
  onRepayAmount(e) {
    this.setData({ repayAmount: e.detail.value })
  },
  onRepayDate(e) {
    this.setData({ repayDate: e.detail.value })
  },
  onRepayNote(e) {
    this.setData({ repayNote: e.detail.value })
  },
  async onSaveRepay() {
    const loan = this.data.current
    if (!loan) return
    if (!Number(this.data.repayAmount)) {
      return wx.showToast({ title: '请填写金额', icon: 'none' })
    }
    try {
      await api.createRepayment(loan.id, {
        amount: Number(this.data.repayAmount),
        repay_date: this.data.repayDate,
        note: (this.data.repayNote || '').trim(),
      })
      wx.showToast({ title: '已登记', icon: 'success' })
      this.setData({ showRepay: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '登记失败', icon: 'none' })
    }
  },

  async onDeletePayment(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '删除这笔还款',
      content: '删除后借款状态会重新计算。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.deleteRepayment(id)
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' })
        }
      },
    })
  },

  onDeleteLoan(e) {
    const loan = this.data.items.find((i) => i.id === e.currentTarget.dataset.id)
    if (!loan) return
    wx.showModal({
      title: `删除与「${loan.party}」的借款`,
      content: '该笔借款的全部还款记录会一并删除。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.deleteLoan(loan.id)
          wx.showToast({ title: '已删除', icon: 'success' })
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' })
        }
      },
    })
  },
})
