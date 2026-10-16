const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')

// 账本固定三本；名称优先用家庭自定义的 book_labels
const DEFAULT_BOOK = { shared: '共同账本', husband: '账本一', wife: '账本二' }
const BOOK_ORDER = ['husband', 'wife', 'shared']
// 自绘日历：周一做为一周首日
const WEEK = ['一', '二', '三', '四', '五', '六', '日']
const CAT_ICONS = ['💰', '🍜', '🛒', '🚗', '🏠', '💊', '🎁', '📚', '✈️', '🐱', '💪', '🎮', '💄', '👶', '🧾', '☕']

function pad(n) {
  return String(n).padStart(2, '0')
}
function ymd(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function parseDate(s) {
  return new Date(`${s}T00:00:00`)
}

Page({
  data: {
    types: [
      { key: 'expense', label: '支出' },
      { key: 'income', label: '收入' },
      { key: 'transfer', label: '借还' },
    ],
    activeType: 'expense',
    categories: [],
    categoryId: '',

    // 账户与账本
    accounts: [],
    bookType: '',
    bookLabels: {},
    myBook: 'husband',
    existingBooks: [],
    visibleAccounts: [],
    accountId: '',

    // 金额 · 备注 · 隐私
    amount: '',
    merchant: '',
    merchantHistory: [],
    isPrivate: false,

    // 日期（默认今天，可改到过去）
    txDate: ymd(new Date()),
    shortDate: '今天',
    showDatePanel: false,
    viewYM: ymd(new Date()).slice(0, 7),
    viewTitle: '',
    week: WEEK,
    calendarDays: [],
    nextDisabled: true,

    // 新增分类弹层
    showAddCat: false,
    catIcons: CAT_ICONS,
    newCatIcon: '💰',
    newCatName: '',
    catSaving: false,

    saving: false,
    // 编辑模式：从首页账单点进来时由 globalData.editTxId 带过来
    editingId: '',
    isEdit: false,
  },

  onLoad(query) {
    // 兼容 wx.reLaunch 直接带 id 的情况；tabBar 页的常规入口走 globalData
    if (query && query.id) {
      this._pendingEditId = query.id
    }
    this.setData({ viewTitle: this._viewTitle(this.data.viewYM) })
    this._buildCalendar(this.data.viewYM)
    this._refreshDateLabels()
  },

  onShow() {
    const app = getApp()
    const pending = this._pendingEditId || (app.globalData && app.globalData.editTxId)
    if (pending) {
      this._pendingEditId = ''
      if (app.globalData) app.globalData.editTxId = ''
      this.loadEditing(String(pending))
      return
    }
    // 普通进入就是记新账：清空上一次的残留
    this._initFresh()
  },

  _initFresh() {
    this.setData({
      isEdit: false,
      editingId: '',
      activeType: 'expense',
      amount: '',
      merchant: '',
      merchantHistory: [],
      isPrivate: false,
      categoryId: '',
      showDatePanel: false,
      txDate: ymd(new Date()),
      viewYM: ymd(new Date()).slice(0, 7),
    })
    this.setData({ viewTitle: this._viewTitle(this.data.viewYM), nextDisabled: false })
    this._buildCalendar(this.data.viewYM)
    this._refreshDateLabels()
    this.loadCategories()
    this.loadAccounts()
  },

  // ---------- 登录身份与账本 ----------
  /** 刷新后 mem 为空，先补齐才能按登录身份选账本 */
  async ensureMe() {
    if (this._meLoaded) return
    try {
      const d = await api.me()
      this._meLoaded = true
      const labels = (d && d.family && d.family.book_labels) || {}
      this.setData({
        bookLabels: labels,
        myBook: (d && d.member && d.member.book_type) || 'husband',
      })
    } catch (e) {
      /* 拿不到就退化为默认账本名 */
    }
  },

  bookName(type) {
    return this.data.bookLabels[type] || DEFAULT_BOOK[type] || type
  },

  async loadAccounts() {
    await this.ensureMe()
    try {
      const d = await api.accounts()
      const accounts = d.items || d || []
      // 只保留真实存在过账户的账本：系统固定三本账，没建账户的不该出现在选择里
      const used = new Set(accounts.map((a) => a.book_type))
      const existingBooks = BOOK_ORDER.filter((b) => used.has(b)).map((b) => ({
        type: b,
        name: this.bookName(b),
        mine: b === this.data.myBook,
      }))
      // 账本默认跟随登录身份：优先我自己的账本，自己名下没账户再退到共同账本
      let bookType = this.data.bookType
      if (!bookType) {
        const preferred = [this.data.myBook, 'shared', ...BOOK_ORDER]
        bookType =
          preferred.find((b) => accounts.some((a) => a.book_type === b)) ||
          (accounts[0] && accounts[0].book_type) ||
          ''
      }
      if (!accounts.some((a) => a.book_type === bookType)) bookType = (accounts[0] && accounts[0].book_type) || ''
      const visibleAccounts = bookType ? accounts.filter((a) => a.book_type === bookType) : accounts
      // 默认选中该账本第一个账户，避免漏选导致流水没有归属账户
      const pool = visibleAccounts.length ? visibleAccounts : accounts
      const accountId =
        this.data.accountId && pool.some((a) => a.id === this.data.accountId)
          ? this.data.accountId
          : (pool[0] && pool[0].id) || ''
      this.setData({ accounts, existingBooks, bookType, visibleAccounts, accountId })
    } catch (e) {
      /* 账户拉不到不影响先填其它字段，保存时会提示 */
    }
  },

  onBook(e) {
    const type = e.currentTarget.dataset.type
    const visibleAccounts = this.data.accounts.filter((a) => a.book_type === type)
    this.setData({
      bookType: type,
      visibleAccounts,
      accountId: (visibleAccounts[0] && visibleAccounts[0].id) || '',
    })
  },

  onAccountPick(e) {
    this.setData({ accountId: e.currentTarget.dataset.id })
  },

  togglePrivate() {
    this.setData({ isPrivate: !this.data.isPrivate })
  },

  // ---------- 分类 ----------
  async loadCategories() {
    try {
      // 借还也归到支出分类下（与后端保存时的口径一致）
      const kind = this.data.activeType === 'income' ? 'income' : 'expense'
      const d = await api.categories(kind)
      this.setData({ categories: d.items || d || [] })
    } catch (e) {
      wx.showToast({ title: e.message || '分类加载失败', icon: 'none' })
    }
    await this.loadMerchantHistory()
  },

  onType(e) {
    const key = e.currentTarget.dataset.key
    if (key === this.data.activeType) return
    this.setData({ activeType: key, categoryId: '', merchantHistory: [] })
    this.loadCategories()
  },

  onCategory(e) {
    const id = e.currentTarget.dataset.id
    if (id === this.data.categoryId) return
    this.setData({ categoryId: id })
    this.loadMerchantHistory()
  },

  /** 备注历史：同一分类下最近用过的备注，点一下直接填入 */
  async loadMerchantHistory() {
    if (!this.data.categoryId) {
      this.setData({ merchantHistory: [] })
      return
    }
    try {
      const list = await api.merchantHistory({ category_id: this.data.categoryId })
      this.setData({ merchantHistory: Array.isArray(list) ? list : [] })
    } catch (e) {
      this.setData({ merchantHistory: [] })
    }
  },

  pickMerchant(e) {
    this.setData({ merchant: e.currentTarget.dataset.val })
  },

  // ---------- 新增分类 ----------
  openAddCat() {
    this.setData({ showAddCat: true, newCatIcon: '💰', newCatName: '' })
  },
  closeAddCat() {
    this.setData({ showAddCat: false })
  },
  noop() {},
  pickCatIcon(e) {
    this.setData({ newCatIcon: e.currentTarget.dataset.icon })
  },
  onCatName(e) {
    this.setData({ newCatName: e.detail.value })
  },
  async submitCat() {
    const name = (this.data.newCatName || '').trim()
    if (!name) {
      wx.showToast({ title: '请填写分类名称', icon: 'none' })
      return
    }
    const kind = this.data.activeType === 'income' ? 'income' : 'expense'
    this.setData({ catSaving: true })
    try {
      const c = await api.createCategory({ name, kind, icon: this.data.newCatIcon })
      this.setData({ showAddCat: false })
      await this.loadCategories()
      // 新建完直接选中，省一步
      if (c && c.id) {
        this.setData({ categoryId: c.id })
        this.loadMerchantHistory()
      }
      wx.showToast({ title: `已新增分类「${(c && c.name) || name}」`, icon: 'none' })
    } catch (e) {
      wx.showToast({ title: e.message || '新增失败', icon: 'none' })
    } finally {
      this.setData({ catSaving: false })
    }
  },

  // ---------- 金额 · 备注 ----------
  onAmount(e) {
    this.setData({ amount: e.detail.value })
  },
  onMerchant(e) {
    this.setData({ merchant: e.detail.value })
  },

  // ---------- 日期 ----------
  _viewTitle(vm) {
    const [y, m] = vm.split('-')
    return `${y}年${Number(m)}月`
  },
  _refreshDateLabels() {
    const today = ymd(new Date())
    const d = this.data.txDate
    let shortDate = '今天'
    if (d !== today) {
      const p = d.split('-')
      shortDate = `${Number(p[1])}月${Number(p[2])}日`
    }
    this.setData({ shortDate })
  },
  _buildCalendar(vm) {
    const [y, m] = vm.split('-').map(Number)
    const first = new Date(y, m - 1, 1)
    const total = new Date(y, m, 0).getDate()
    const lead = (first.getDay() + 6) % 7
    const today = ymd(new Date())
    const cells = []
    for (let i = lead; i > 0; i--) {
      const d = new Date(y, m - 1, 1 - i)
      cells.push({ key: `p${ymd(d)}`, date: ymd(d), day: d.getDate(), muted: true })
    }
    for (let n = 1; n <= total; n++) {
      const d = new Date(y, m - 1, n)
      cells.push({ key: ymd(d), date: ymd(d), day: n, muted: false })
    }
    let tail = 1
    while (cells.length % 7 !== 0 || cells.length < 42) {
      const d = new Date(y, m - 1, total + tail++)
      cells.push({ key: `n${ymd(d)}`, date: ymd(d), day: d.getDate(), muted: true })
    }
    cells.forEach((c) => {
      c.off = c.date > today
      c.isToday = c.date === today
    })
    // 当月之后没有可记的日子，「下一月」直接禁用
    const thisMonth = ymd(new Date()).slice(0, 7)
    this.setData({
      calendarDays: cells,
      viewYM: vm,
      viewTitle: this._viewTitle(vm),
      nextDisabled: vm >= thisMonth,
    })
  },
  toggleDatePanel() {
    if (this.data.showDatePanel) {
      this.setData({ showDatePanel: false })
      return
    }
    const vm = this.data.txDate.slice(0, 7)
    this._buildCalendar(vm)
    this.setData({ showDatePanel: true })
  },
  closeDatePanel() {
    this.setData({ showDatePanel: false })
  },
  prevMonth() {
    const [y, m] = this.data.viewYM.split('-').map(Number)
    const d = new Date(y, m - 2, 1)
    this._buildCalendar(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`)
  },
  nextMonth() {
    if (this.data.nextDisabled) return
    const [y, m] = this.data.viewYM.split('-').map(Number)
    const d = new Date(y, m, 1)
    this._buildCalendar(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`)
  },
  pickDate(e) {
    const date = e.currentTarget.dataset.date
    if (date > ymd(new Date())) return
    this.setData({ txDate: date, showDatePanel: false })
    this._refreshDateLabels()
  },
  pickToday() {
    const today = ymd(new Date())
    this._buildCalendar(today.slice(0, 7))
    this.setData({ txDate: today, showDatePanel: false })
    this._refreshDateLabels()
  },

  /** 选今天就用当前时刻；选过去某天则保留当天 + 当前时分秒，排序更自然 */
  _txDateTime() {
    const now = new Date()
    const hm = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
    return `${this.data.txDate}T${hm}`
  },

  // ---------- 编辑模式 ----------
  async loadEditing(id) {
    await this.ensureMe()
    try {
      const t = await api.txDetail(id)
      if (!t) return
      this.setData({
        isEdit: true,
        editingId: id,
        activeType: t.type || 'expense',
        amount: String(yuan(t.amount_cents == null ? 0 : t.amount_cents)),
        merchant: t.merchant || '',
        isPrivate: !!t.is_private,
        txDate: (t.transaction_date || '').slice(0, 10) || ymd(new Date()),
        showDatePanel: false,
      })
      this._refreshDateLabels()
      const vm = this.data.txDate.slice(0, 7)
      this._buildCalendar(vm)
      await this.loadCategories()
      this.setData({ categoryId: t.category_id || '' })
      await this.loadMerchantHistory()
      // 账户：先等账户列表就位，再定位到该账户所属的账本
      await this.loadAccounts()
      const acc = this.data.accounts.find((a) => a.id === t.account_id)
      if (acc) {
        const visibleAccounts = this.data.accounts.filter((a) => a.book_type === acc.book_type)
        this.setData({ bookType: acc.book_type, visibleAccounts, accountId: acc.id })
      }
    } catch (e) {
      wx.showToast({ title: e.message || '加载账单失败', icon: 'none' })
      this._initFresh()
    }
  },

  // ---------- 保存 ----------
  async onSave() {
    if (this.data.saving) return
    const amt = Number(this.data.amount)
    if (!amt || amt <= 0) {
      wx.showToast({ title: '请输入金额', icon: 'none' })
      return
    }
    if (!this.data.categoryId) {
      wx.showToast({ title: '请选择分类', icon: 'none' })
      return
    }
    if (!this.data.accountId) {
      wx.showToast({ title: '请选择账户', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    try {
      const payload = {
        type: this.data.activeType,
        amount: String(amt),
        account: this.data.accountId || null,
        category: this.data.categoryId,
        merchant: this.data.merchant,
        transaction_date: this._txDateTime(),
        is_private: this.data.isPrivate && this.data.activeType === 'expense',
      }
      if (this.data.isEdit) {
        // 后端会先冲正旧流水对余额的影响、再按新值重新应用
        await api.updateTx(this.data.editingId, payload)
        wx.showToast({ title: '已保存修改', icon: 'none' })
        setTimeout(() => wx.switchTab({ url: '/pages/home/home' }), 600)
        return
      }
      const res = await api.createTx(payload)
      const t = (res && res.threshold) || {}
      let msg = '已记账'
      if (t.action === 'notify') msg = '已记账，将通知对方'
      else if (t.action === 'approval') msg = '已记账，需对方审批'
      else if (t.action === 'joint') msg = '已记账，需共同决策'
      if (res && res.privacy && res.privacy.will_auto_public) {
        msg = '已记账，超出隐私额度已计入共同支出'
      }
      // 保存成功直接回首页，与 H5 一致
      wx.showToast({ title: msg, icon: 'none' })
      setTimeout(() => wx.switchTab({ url: '/pages/home/home' }), 600)
    } catch (e) {
      if (requireLogin(e)) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        wx.navigateTo({ url: '/pages/login/login' })
        return
      }
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  onCancel() {
    wx.switchTab({ url: '/pages/home/home' })
  },
})
