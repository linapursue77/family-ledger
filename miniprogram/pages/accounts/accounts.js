const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

// 账户介质：与后端 Account.CARD_CHOICES 一一对应
const CARD_TYPES = [
  { value: 'debit', label: '储蓄卡' },
  { value: 'credit', label: '信用卡' },
  { value: 'cash', label: '现金' },
  { value: 'wallet', label: '数字钱包' },
  { value: 'invest', label: '投资理财' },
]
// 可见性：与后端 Account.TYPE_CHOICES 一一对应
const VISIBILITY = [
  { value: 'joint', label: '共同账户' },
  { value: 'personal', label: '对方可见' },
  { value: 'private', label: '仅本人可见' },
]
const BOOKS = [
  { value: 'husband', label: '账本一' },
  { value: 'wife', label: '账本二' },
  { value: 'shared', label: '共同账本' },
]
const ICONS = ['💰', '🏦', '💳', '💵', '📱', '📈', '🏠', '🚗', '🎁', '✈️', '🍚', '🐱']

function money(cents) {
  return yuan(cents).toFixed(2)
}

function signed(cents) {
  const v = yuan(cents)
  return (v >= 0 ? '+' : '-') + Math.abs(v).toFixed(2)
}

function emptyForm() {
  return {
    name: '',
    icon: '💰',
    cardIndex: 0,
    visIndex: 1,
    bookIndex: 0,
    bankName: '',
    accountNo: '',
    isCountTotal: true,
    isInvest: false,
    // 与 H5 一致：表单里填的是「收益总额」，本金由 现值 − 收益 倒推后单独提交。
    // 存的是本金、显示的是收益，别把方向写反（反了每编辑一次收益就变号）。
    profit: '',
    balance: '',
  }
}

Page({
  data: {
    loading: true,
    groups: [],
    totalText: '0.00',
    statsText: '',

    // 底部操作面板
    showActions: false,
    current: null,

    // 新增 / 编辑
    showEdit: false,
    editing: null,
    form: emptyForm(),
    saving: false,
    icons: ICONS,
    cardTypes: CARD_TYPES,
    visibility: VISIBILITY,
    books: BOOKS,

    // 调整余额
    showAdjust: false,
    adjustBalance: '',
    adjustReason: '',

    // 盘点本金
    showPrincipal: false,
    principalValue: '',
    principalMode: 'set',
    principalReason: '',
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const [accRes, famRes] = await Promise.all([
        api.accounts().catch(() => null),
        api.familyMe().catch(() => null),
      ])
      const raw = (accRes && (accRes.items || accRes)) || []
      const labels = (famRes && famRes.book_labels) || {}
      this.buildGroups(raw, labels)
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  buildGroups(raw, labels) {
    const items = raw.map((a) => ({
      ...a,
      balanceText: money(a.balance_cents),
      principalText: money(a.principal_cents || 0),
      profitText: a.is_invest ? signed(a.profit_cents) : '',
      rateText: a.profit_rate == null ? '' : `${a.profit_rate.toFixed(2)}%`,
      cardLabel: (CARD_TYPES.find((c) => c.value === a.card_type) || {}).label || '',
      visLabel: (VISIBILITY.find((v) => v.value === a.type) || {}).label || '',
      bankText: a.bank_name || '',
    }))

    const groups = BOOKS.map((b) => {
      const inBook = items.filter((i) => i.book_type === b.value)
      return {
        key: b.value,
        label: labels[b.value] || b.label,
        items: inBook,
        totalText: money(
          inBook.reduce((sum, i) => sum + (i.is_count_total ? Number(i.balance_cents) : 0), 0),
        ),
      }
    })

    const counted = items.filter((i) => i.is_count_total)
    const investCount = items.filter((i) => i.is_invest).length
    this.setData({
      groups,
      totalText: money(counted.reduce((sum, i) => sum + Number(i.balance_cents), 0)),
      statsText: `共 ${items.length} 个账户 · ${investCount} 个纳入收益管理`,
    })
  },

  // ---- 账户操作面板
  onAccTap(e) {
    const acc = this.findBy(e.currentTarget.dataset.id)
    if (acc) this.setData({ showActions: true, current: acc })
  },
  findBy(id) {
    for (const g of this.data.groups) {
      const hit = g.items.find((i) => i.id === id)
      if (hit) return hit
    }
    return null
  },
  closeActions() {
    this.setData({ showActions: false })
  },

  // ---- 新增 / 编辑
  openAdd() {
    this.setData({ showActions: false, showEdit: true, editing: null, form: emptyForm() })
  },
  openEdit() {
    const a = this.data.current
    if (!a) return
    this.setData({
      showActions: false,
      showEdit: true,
      editing: a,
      form: {
        name: a.name || '',
        icon: a.icon || '💰',
        cardIndex: Math.max(0, CARD_TYPES.findIndex((c) => c.value === a.card_type)),
        visIndex: Math.max(0, VISIBILITY.findIndex((v) => v.value === a.type)),
        bookIndex: Math.max(0, BOOKS.findIndex((b) => b.value === a.book_type)),
        bankName: a.bank_name || '',
        accountNo: a.account_no || '',
        isCountTotal: a.is_count_total !== false,
        isInvest: !!a.is_invest,
        // 回填收益：收益 = 现值 − 本金（本金没录过就留空，保存时收益从 0 起算）
        profit:
          a.is_invest && Number(a.principal_cents) > 0
            ? String(yuan((Number(a.balance_cents) || 0) - Number(a.principal_cents)))
            : '',
        balance: '',
      },
    })
  },
  closeEdit() {
    this.setData({ showEdit: false, editing: null })
  },
  onInput(e) {
    this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value })
  },
  onIcon(e) {
    this.setData({ 'form.icon': e.currentTarget.dataset.icon })
  },
  onPick(e) {
    this.setData({ [`form.${e.currentTarget.dataset.field}`]: Number(e.detail.value) })
  },
  onSwitch(e) {
    this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value })
  },

  async onSave() {
    if (this.data.saving) return
    const f = this.data.form
    const name = (f.name || '').trim()
    if (!name) return wx.showToast({ title: '请填写名称', icon: 'none' })

    const payload = {
      name,
      icon: f.icon,
      card_type: CARD_TYPES[f.cardIndex].value,
      type: VISIBILITY[f.visIndex].value,
      book_type: BOOKS[f.bookIndex].value,
      bank_name: (f.bankName || '').trim(),
      account_no: (f.accountNo || '').trim(),
      is_count_total: !!f.isCountTotal,
      is_invest: !!f.isInvest,
    }

    // 收益校验放前面，避免先转圈再弹错误
    let principalVal = null
    if (f.isInvest) {
      const pf = f.profit === '' ? 0 : Number(f.profit)
      if (!Number.isFinite(pf)) return wx.showToast({ title: '收益金额不正确', icon: 'none' })
      // 现值：编辑时用账户当前余额，新建时用填的初始余额
      const balYuan = this.data.editing
        ? yuan(Number(this.data.editing.balance_cents) || 0)
        : Number(f.balance || 0)
      principalVal = balYuan - pf
      if (principalVal < 0) {
        return wx.showToast({ title: '收益不能大于当前金额', icon: 'none' })
      }
    }

    this.setData({ saving: true })
    try {
      if (this.data.editing) {
        await api.updateAccount(this.data.editing.id, payload)
        // 本金不在账户字段里，单独走盘点接口（mode=set 直接设为该值）
        if (principalVal !== null) {
          await api.setPrincipal(this.data.editing.id, {
            principal: principalVal,
            mode: 'set',
            reason: '账户编辑时更新本金',
          })
        }
        wx.showToast({ title: '已保存', icon: 'success' })
      } else {
        payload.balance = Number(f.balance || 0)
        // 新建投资账户：收益留空时本金 = 初始余额，收益从 0 起算
        if (principalVal !== null) payload.principal = principalVal
        await api.createAccount(payload)
        wx.showToast({ title: '已新增', icon: 'success' })
      }
      this.setData({ showEdit: false, editing: null })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  // ---- 调整余额：填实际余额，服务端直接落到该值并记日志
  openAdjust() {
    const a = this.data.current
    if (!a) return
    this.setData({
      showActions: false,
      showAdjust: true,
      adjustBalance: String(yuan(a.balance_cents)),
      adjustReason: '',
    })
  },
  closeAdjust() {
    this.setData({ showAdjust: false })
  },
  onAdjustBalance(e) {
    this.setData({ adjustBalance: e.detail.value })
  },
  onAdjustReason(e) {
    this.setData({ adjustReason: e.detail.value })
  },
  async onSaveAdjust() {
    const a = this.data.current
    if (!a) return
    const reason = (this.data.adjustReason || '').trim()
    if (!reason) return wx.showToast({ title: '请填写说明', icon: 'none' })
    try {
      await api.adjustAccount(a.id, {
        balance: Number(this.data.adjustBalance || 0),
        reason,
      })
      wx.showToast({ title: '已调整', icon: 'success' })
      this.setData({ showAdjust: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '调整失败', icon: 'none' })
    }
  },

  // ---- 盘点本金：set=按平台「累计投入」填；add=定投加仓
  openPrincipal() {
    const a = this.data.current
    if (!a) return
    this.setData({
      showActions: false,
      showPrincipal: true,
      principalValue: String(yuan(a.principal_cents || 0)),
      principalMode: 'set',
      principalReason: '',
    })
  },
  closePrincipal() {
    this.setData({ showPrincipal: false })
  },
  onMode(e) {
    this.setData({ principalMode: e.currentTarget.dataset.mode })
  },
  onPrincipalValue(e) {
    this.setData({ principalValue: e.detail.value })
  },
  onPrincipalReason(e) {
    this.setData({ principalReason: e.detail.value })
  },
  async onSavePrincipal() {
    const a = this.data.current
    if (!a) return
    try {
      await api.setPrincipal(a.id, {
        principal: Number(this.data.principalValue || 0),
        mode: this.data.principalMode,
        reason: (this.data.principalReason || '').trim(),
      })
      wx.showToast({ title: '已盘点', icon: 'success' })
      this.setData({ showPrincipal: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '盘点失败', icon: 'none' })
    }
  },

  // ---- 删除
  onDelete() {
    const a = this.data.current
    if (!a) return
    wx.showModal({
      title: `删除「${a.name}」`,
      content: '有余额或流水的账户需要先转移，删除后不可恢复。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.deleteAccount(a.id)
          this.setData({ showActions: false })
          wx.showToast({ title: '已删除', icon: 'success' })
          await this.load()
        } catch (e) {
          wx.showToast({ title: e.message || '删除失败', icon: 'none' })
        }
      },
    })
  },
})
