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
    // 只含我名下账户（后端 is_mine），记账只能落到自己的账户
    myAccounts: [],
    bookType: '',
    bookLabels: {},
    myBook: 'husband',
    // 账本 chips：我的账本 + 共同账本（编辑老账单时会补上原账本）
    existingBooks: [],
    visibleAccounts: [],
    // 账户 chips：可见账户，编辑老账单时兜底保留原账户
    accountChoices: [],
    accountId: '',

    // 金额 · 备注 · 隐私
    amount: '',
    merchant: '',
    merchantHistory: [],
    isPrivate: false,

    // 日期（默认今天，可改到过去）
    txDate: ymd(new Date()),
    // 日期框里显示的 YYYY/MM/DD（对齐 H5 dateDisplay）
    dateDisplay: ymd(new Date()).split('-').join('/'),
    // 相对描述（今天/昨天/M月D日），供其它文案复用
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

  /**
   * 可记账的账户：只保留「我名下」的账户。
   * 后端回 is_mine 布尔值（不暴露 user_id），记账只能落到自己的账户上。
   */
  _myAccounts(accounts) {
    return (accounts || []).filter((a) => a.is_mine !== false)
  },

  /**
   * 可选的账本：只出现「我的账本 + 共同账本」。
   * 对方专属账本整本不进选择，避免在自己账号体系下误选到对方的账本。
   */
  _bookChoices(myAccounts, currentBook) {
    const used = new Set(myAccounts.map((a) => a.book_type))
    const myBook = this.data.myBook
    const list = BOOK_ORDER.filter((b) => {
      if (b !== 'shared' && b !== myBook) return false
      return used.has(b)
    })
    // 编辑老账单时若它落在已不可选的账本，补进来，否则 chips 里没有选中项
    if (currentBook && list.indexOf(currentBook) === -1) list.push(currentBook)
    return list
  },

  /** 账户 chips：编辑态下原账户可能不在我名下，兜底保留，避免保存时被清空 */
  _accountChoices(accounts, visibleAccounts, accountId) {
    const list = visibleAccounts.slice()
    if (accountId && !list.some((a) => a.id === accountId)) {
      const origin = (accounts || []).find((a) => a.id === accountId)
      if (origin) list.push(origin)
    }
    return list
  },

  async loadAccounts() {
    await this.ensureMe()
    try {
      const d = await api.accounts()
      const accounts = d.items || d || []
      const myAccounts = this._myAccounts(accounts)
      // 账本默认跟随登录身份：优先我自己的账本，自己名下没账户再退到共同账本
      let bookType = this.data.bookType
      const choices = this._bookChoices(myAccounts, bookType)
      if (!bookType || choices.indexOf(bookType) === -1) {
        const preferred = [this.data.myBook, 'shared']
        bookType = preferred.find((b) => myAccounts.some((a) => a.book_type === b)) || choices[0] || ''
      }
      const visibleAccounts = bookType
        ? myAccounts.filter((a) => a.book_type === bookType)
        : myAccounts
      // 默认选中该账本第一个账户，避免漏选导致流水没有归属账户
      const pool = visibleAccounts.length ? visibleAccounts : myAccounts
      const accountId =
        this.data.accountId && pool.some((a) => a.id === this.data.accountId)
          ? this.data.accountId
          : (pool[0] && pool[0].id) || ''
      this.setData({
        accounts,
        myAccounts,
        existingBooks: this._bookChoices(myAccounts, bookType).map((b) => ({
          type: b,
          name: this.bookName(b),
          mine: b === this.data.myBook,
        })),
        bookType,
        visibleAccounts,
        accountChoices: this._accountChoices(accounts, visibleAccounts, accountId),
        accountId,
      })
    } catch (e) {
      /* 账户拉不到不影响先填其它字段，保存时会提示 */
    }
  },

  onBook(e) {
    const type = e.currentTarget.dataset.type
    const visibleAccounts = this.data.myAccounts.filter((a) => a.book_type === type)
    this.setData({
      bookType: type,
      visibleAccounts,
      accountChoices: visibleAccounts,
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
  /**
   * 日期标签与 H5 Add.vue 的 shortDate 完全一致：
   *   今天 → 「今天」；昨天 → 「昨天」；更早 → 「M月D日」
   */
  _refreshDateLabels() {
    const now = new Date()
    const today = ymd(now)
    // 用日期差而不是字符串比较，跨月（如 11-01 的昨天是 10-31）也能认对
    const yesterday = ymd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))
    const d = this.data.txDate
    let shortDate = d
    if (d === today) {
      shortDate = '今天'
    } else if (d === yesterday) {
      shortDate = '昨天'
    } else {
      const p = d.split('-')
      shortDate = `${Number(p[1])}月${Number(p[2])}日`
    }
    // 日期框里显示完整日期（YYYY/MM/DD），与 H5 的 dateDisplay 一致
    this.setData({ shortDate, dateDisplay: d.split('-').join('/') })
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
        // 老账单可能落在对方账本 / 对方账户：账本与账户都要补进 chips，
        // 否则界面上看不到选中项，一保存就把归属改掉了
        const visibleAccounts = this.data.myAccounts.filter(
          (a) => a.book_type === acc.book_type
        )
        this.setData({
          bookType: acc.book_type,
          visibleAccounts,
          existingBooks: this._bookChoices(this.data.myAccounts, acc.book_type).map((b) => ({
            type: b,
            name: this.bookName(b),
            mine: b === this.data.myBook,
          })),
          accountChoices: this._accountChoices(this.data.accounts, visibleAccounts, acc.id),
          accountId: acc.id,
        })
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
