const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')
const { appPayload, toAppMessage, toTimeline } = require('../../utils/share')

const PRESETS = [
  { key: 'last_week', label: '近1周' },
  { key: 'last_month', label: '近1月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
  { key: 'custom', label: '自定义' },
]

// 删除按钮宽度（px）：.bill-del = 120rpx ≈ 60px（750rpx 屏宽下）
const SWIPE_W = 60

const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六']

function ymd(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 与 H5 Home.vue 的 money() 同口径：千分位 + 两位小数 */
function money(v) {
  const n = Number(v)
  if (isNaN(n)) return '0.00'
  const neg = n < 0
  const [i, d] = Math.abs(n).toFixed(2).split('.')
  return (neg ? '-' : '') + i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + d
}

function dayText(key) {
  const parts = (key || '').split('-')
  return parts.length === 3 ? `${Number(parts[1])}月${Number(parts[2])}日` : key
}

function dayLabel(key) {
  const d = new Date(key + 'T00:00:00')
  if (isNaN(d)) return ''
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((today - d) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  return '星期' + WEEK_CN[d.getDay()]
}

Page({
  data: {
    presets: PRESETS,
    activePreset: 'last_week',
    activePresetLabel: '近1周',
    // 自定义区间
    showCustom: false,
    customStart: '',
    customEnd: '',
    customMin: '2000-01-01',
    today: ymd(new Date()),
    loading: true,
    needLogin: false,
    ov: null,
    ovText: { totalAssets: '0.00', income: '0.00', expense: '0.00', balance: '0.00', rateWidth: 0 },
    assetChange: '',
    invest: { show: false, profitText: '', valueText: '', up: true },

    // 近期账单（首页逐笔明细）
    recentRange: 'follow', // 'follow'=跟随顶部周期 | 3 | 7 天
    recentLabel: '近1周',
    recentLoading: false,
    recentTxs: [],
    billSort: 'time', // time=按时间(按天分组) | cat=按分类分组
    billGroups: [],
    billSummary: { count: 0, expenseText: '0.00', incomeText: '0.00' },

    // 左滑删除
    swipeId: '',
    swipeOffset: 0,

    // 流水详情弹层
    showTxDetail: false,
    detailTxId: '',
    detailTx: null,

    // 分类/账户名映射（账单列表要显示分类图标和账户名）
    categoryMap: {},
    accountMap: {},
    metaLoaded: false,

    // 是否有登录态：决定页面是拉数据还是展示登录引导
    loggedIn: true,
  },

  onShow() {
    this.loadAll()
  },

  /**
   * 下拉刷新：重新拉一遍首页数据。
   * 必须 await 后再 stopPullDownRefresh，否则转圈会立刻消失、看着像没刷新成功。
   * finally 里收，保证接口失败时也能收起，不会卡在刷新态。
   */
  async onPullDownRefresh() {
    try {
      await this.loadAll()
    } finally {
      wx.stopPullDownRefresh()
    }
  },

  async loadAll() {
    /*
     * 未登录不发请求：首页一进来就要 overview/accounts/transactions 四五个接口，
     * 没 token 时每个都 401，白打一轮还刷一屏错误。
     * 这里直接置空并给登录引导，等用户登录回来 onShow 再取数。
     */
    if (!wx.getStorageSync('fl_token')) {
      this.setData({ loading: false, loggedIn: false })
      return
    }
    this.setData({ loading: true, loggedIn: true })
    try {
      const params = { preset: this.data.activePreset }
      if (this.data.activePreset === 'custom') {
        params.start = this.data.customStart
        params.end = this.data.customEnd
      }
      const ov = await api.overview(params)
      const label =
        (PRESETS.find((p) => p.key === this.data.activePreset) || {}).label || ''
      this.setData({ ov, activePresetLabel: label, needLogin: false, ...this._ovView(ov) })
      if (!this.data.metaLoaded) await this.loadMeta()
      this.loadRecent(ov)
      // 收益不随时间范围变，只在进首页时拉一次
      if (!this._returnsLoaded) this.loadReturns()
    } catch (e) {
      if (requireLogin(e)) {
        this.setData({ needLogin: true, ov: null, billGroups: [], recentTxs: [] })
        return
      }
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  /** 把总览数据转成渲染文案（千分位 + 储蓄率宽度） */
  _ovView(ov) {
    const rate = Math.min(Math.max(Number(ov.saving_rate) || 0, 0), 100)
    return {
      ovText: {
        totalAssets: money(ov.total_assets),
        income: money(ov.income),
        expense: money(ov.expense),
        balance: money(ov.balance),
        rateWidth: rate,
      },
      assetChange: this._assetChangeText(ov),
    }
  },

  _assetChangeText(ov) {
    const v = Number(ov.asset_change || 0)
    const sign = v >= 0 ? '+' : ''
    return `比上月 ${sign}¥${yuan(Math.abs(v)).toFixed(2)}`
  },

  // ---- 资产卡上的收益展示：从收益管理接口取
  async loadReturns() {
    this._returnsLoaded = true
    try {
      const r = await api.returns()
      const profit = Number(r.profit_cents) || 0
      this.setData({
        invest: {
          show: !!r.has_invest,
          up: profit >= 0,
          profitText: `${profit >= 0 ? '+' : '-'}¥${money(Math.abs(profit) / 100)}`,
          valueText: money((Number(r.value_cents) || 0) / 100),
        },
      })
    } catch (e) {
      /* 收益拿不到就不展示这一行，不影响其它卡片 */
    }
  },

  // ---- 分类 / 账户元数据：账单列表要显示分类图标、颜色、账户名
  async loadMeta() {
    try {
      const [cats, accs] = await Promise.all([api.categories(), api.accounts()])
      const cmap = {}
      ;(cats.items || cats || []).forEach((c) => (cmap[c.id] = c))
      const amap = {}
      ;(accs.items || accs || []).forEach((a) => (amap[a.id] = a))
      this.setData({ categoryMap: cmap, accountMap: amap, metaLoaded: true })
    } catch (e) {
      /* 元数据拉不到不影响主流程，列表退化为不显示分类图标 */
    }
  },

  // ---- 近期账单
  async loadRecent(ov) {
    this.setData({ recentLoading: true })
    try {
      let from, to
      const data = ov || this.data.ov
      if (this.data.recentRange === 'follow' && data && data.range) {
        // ★ 与顶部时间控件同源：直接用 overview 返回的区间，账单与资产卡口径一致
        from = data.range.start
        to = data.range.end
      } else {
        const days = Number(this.data.recentRange) || 3
        const end = new Date()
        const start = new Date()
        start.setDate(start.getDate() - (days - 1))
        from = ymd(start)
        to = ymd(end)
      }
      const label =
        this.data.recentRange === 'follow' ? this.data.activePresetLabel : `近${this.data.recentRange}日`
      const res = await api.transactions({ date_from: from, date_to: to, page_size: 200 })
      const items = (res.items || res || []).map((t) => this._decorateTx(t))
      items.sort((x, y) => y.dateKey.localeCompare(x.dateKey))
      this.setData({ recentTxs: items, recentLabel: label })
      this._buildBillGroups()
    } catch (e) {
      if (e && e.needLogin) return
      /* 账单列表失败不打扰用户，其它卡片照常 */
    } finally {
      this.setData({ recentLoading: false })
    }
  },

  _decorateTx(t) {
    const c = this.data.categoryMap[t.category_id] || {}
    const a = this.data.accountMap[t.account_id] || {}
    const isLoan = t.type === 'loan_in' || t.type === 'loan_out'
    const isIn = t.type === 'income' || t.type === 'loan_in'
    return {
      ...t,
      isLoan,
      isIn,
      dateKey: (t.transaction_date || '').slice(0, 10),
      catIcon: isLoan ? '🤝' : c.icon || '💸',
      catName: isLoan ? '借钱来往' : c.name || '未分类',
      catColor: isLoan ? '#888780' : c.color || '#888780',
      accountName: a.name || (t.account_id ? '' : '未指定账户'),
      merchant: t.merchant || (isLoan ? '借钱来往' : c.name || (isIn ? '收入' : '支出')),
      amountText: (isIn ? '+' : '-') + yuan(Number(t.amount_cents) || 0).toFixed(2),
    }
  },

  /** 按天 / 按分类分组，与 H5 Home.vue 的 billGroups 同口径 */
  _buildBillGroups() {
    const list = this.data.recentTxs
    const byCat = this.data.billSort === 'cat'
    const map = {}
    const order = []
    list.forEach((t) => {
      const k = byCat ? t.catName || '未分类' : t.dateKey
      if (!map[k]) {
        map[k] = { key: k, items: [], expense: 0, income: 0, icon: t.catIcon, color: t.catColor }
        order.push(k)
      }
      const g = map[k]
      g.items.push(t)
      // 借贷只占一行明细，不混进「支/收」小结，避免与报表口径打架
      if (t.isLoan) return
      if (byCat) {
        if (t.isIn) g.income += t.amount_cents
        else g.expense += t.amount_cents
      } else {
        if (t.type === 'income') g.income += t.amount_cents
        else g.expense += t.amount_cents
      }
    })

    const groups = order
      .map((k) => ({
        ...map[k],
        dayText: dayText(k),
        dayLabel: dayLabel(k),
        expenseText: yuan(map[k].expense).toFixed(2),
        incomeText: yuan(map[k].income).toFixed(2),
      }))
      .sort((a, b) =>
        byCat ? b.expense + b.income - (a.expense + a.income) : b.key.localeCompare(a.key)
      )

    let count = 0
    let expense = 0
    let income = 0
    list.forEach((t) => {
      count += 1
      if (t.isLoan) return
      if (t.isIn) income += t.amount_cents
      else expense += t.amount_cents
    })

    this.setData({
      billGroups: groups,
      billSummary: {
        count,
        expenseText: yuan(expense).toFixed(2),
        incomeText: yuan(income).toFixed(2),
      },
    })
  },

  setBillSort(e) {
    const sort = e.currentTarget.dataset.sort
    if (this.data.billSort === sort) return
    this.setData({ billSort: sort, swipeId: '', swipeOffset: 0 })
    this._buildBillGroups()
  },

  onRecentRange(e) {
    const key = e.currentTarget.dataset.key
    const val = key === 'follow' ? 'follow' : Number(key)
    if (this.data.recentRange === val) return
    this.setData({ recentRange: val, swipeId: '', swipeOffset: 0 })
    this.loadRecent()
  },

  // ---- 左滑删除：与 H5 的手势逻辑一致（方向锁定 + 过半吸附）
  onSwipeStart(e) {
    const t = e.currentTarget.dataset.tx
    if (!t || t.isLoan) return // 借贷流水删不了，也就不给滑
    const touch = (e.touches && e.touches[0]) || {}
    this._startX = touch.clientX || 0
    this._startY = touch.clientY || 0
    this._dragging = true
    this._axisLocked = false
    this._suppressClick = false
    this.setData({ swipeId: t.id, swipeOffset: 0 })
  },

  onSwipeMove(e) {
    if (!this._dragging) return
    const touch = (e.touches && e.touches[0]) || {}
    const dx = (touch.clientX || 0) - this._startX
    const dy = (touch.clientY || 0) - this._startY
    if (!this._axisLocked) {
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return
      // 竖向意图明显 → 放弃本次滑动，交给页面滚动
      if (Math.abs(dy) > Math.abs(dx)) {
        this._dragging = false
        this.setData({ swipeId: '', swipeOffset: 0 })
        return
      }
      this._axisLocked = true
      this._suppressClick = true
    }
    this.setData({ swipeOffset: Math.max(-SWIPE_W, Math.min(0, dx)) })
  },

  onSwipeEnd() {
    if (!this._dragging) return
    this._dragging = false
    const off = this.data.swipeOffset <= -SWIPE_W / 2 ? -SWIPE_W : 0
    this.setData({ swipeOffset: off, swipeId: off === 0 ? '' : this.data.swipeId })
  },

  _resetSwipe() {
    this.setData({ swipeId: '', swipeOffset: 0 })
  },

  /** 点账单条目 → 进记账页改这一笔（借贷流水由借钱来往维护，只能在那里改） */
  onBillTap(e) {
    const t = e.currentTarget.dataset.tx
    if (!t) return
    // 滑动手势结束时会补发一次 click，这里把它吃掉，避免滑完就跳进编辑页
    if (this._suppressClick) {
      this._suppressClick = false
      return
    }
    // 已滑开的条目再点一下 = 收起，不要误进编辑
    if (this.data.swipeId === t.id && this.data.swipeOffset < 0) {
      this._resetSwipe()
      return
    }
    if (t.isLoan) return this.openTxDetail(e)
    this.goEditTx(t.id)
  },

  /**
   * 记账页是 tabBar 页：navigateTo 打不开，只能 switchTab，
   * 而 switchTab 不支持 query，所以用 globalData 把 id 带过去。
   */
  goEditTx(id) {
    getApp().globalData.editTxId = String(id)
    wx.switchTab({ url: '/pages/add/add' })
  },

  async onDelete(e) {
    const id = e.currentTarget.dataset.id
    if (e.currentTarget.dataset.loan) {
      wx.showToast({ title: '借贷流水请到「借钱来往」处理', icon: 'none' })
      return
    }
    if (this._deleting) return
    this._deleting = true
    try {
      await api.removeTx(id)
      this._resetSwipe()
      this.setData({
        recentTxs: this.data.recentTxs.filter((x) => x.id !== id),
      })
      this._buildBillGroups()
      // 余额/统计都变了，整体刷新
      await this.loadAll()
      wx.showToast({ title: '已删除', icon: 'success' })
    } catch (err) {
      wx.showToast({ title: err.message || '删除失败', icon: 'none' })
    } finally {
      this._deleting = false
    }
  },

  // ---- 时间控件
  onPreset(e) {
    const key = e.currentTarget.dataset.key
    if (key === 'custom') {
      // 默认给近一年的区间，方便直接确定
      this.setData({
        showCustom: !this.data.showCustom,
        customStart: this.data.customStart || ymd(new Date(Date.now() - 364 * 864e5)),
        customEnd: this.data.customEnd || ymd(new Date()),
      })
      return
    }
    this.setData({ showCustom: false, activePreset: key })
    this.loadAll()
  },

  onCustomStart(e) {
    const v = e.detail.value
    if (this.data.customEnd && v > this.data.customEnd) {
      wx.showToast({ title: '开始日期不能晚于结束日期', icon: 'none' })
      return
    }
    this.setData({ customStart: v })
  },

  onCustomEnd(e) {
    const v = e.detail.value
    if (this.data.customStart && v < this.data.customStart) {
      wx.showToast({ title: '结束日期不能早于开始日期', icon: 'none' })
      return
    }
    this.setData({ customEnd: v })
  },

  applyCustom() {
    if (!this.data.customStart || !this.data.customEnd) {
      wx.showToast({ title: '请选择起止日期', icon: 'none' })
      return
    }
    this.setData({ showCustom: false, activePreset: 'custom', activePresetLabel: '自定义' })
    this.loadAll()
  },

  // ---- 流水详情弹层
  openTxDetail(e) {
    const t = e.currentTarget.dataset.tx
    if (!t) return
    this.setData({ showTxDetail: true, detailTxId: '', detailTx: t })
  },
  closeTxDetail() {
    this.setData({ showTxDetail: false, detailTx: null, detailTxId: '' })
  },
  onTxEdit(e) {
    const id = e.detail.id
    this.setData({ showTxDetail: false, detailTx: null })
    this.goEditTx(id)
  },
  onTxDeleted() {
    // 删完刷新账单与总览，保证各卡片同步
    this.loadRecent()
    this.loadAll()
  },

  goLogin() {
    wx.navigateTo({ url: '/pages/login/login' })
  },

  goAdd() {
    // 未登录先引导登录：记账必须登录后才能落库
    if (this.data.needLogin) return this.goLogin()
    wx.switchTab({ url: '/pages/add/add' })
  },

  goAsset() {
    wx.navigateTo({ url: '/pages/asset/asset' })
  },

  goReturns() {
    wx.navigateTo({ url: '/pages/returns/returns' })
  },

  // 右上角转发：没有这个钩子时微信会截当前页面，首页数据多时容易截成空白
  onShareAppMessage() {
    return toAppMessage(appPayload())
  },
  onShareTimeline() {
    return toTimeline(appPayload())
  },
})
