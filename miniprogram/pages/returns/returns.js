const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

function money(cents) {
  return yuan(cents).toFixed(2)
}

function signed(cents) {
  const v = yuan(cents)
  return (v >= 0 ? '+' : '-') + Math.abs(v).toFixed(2)
}

Page({
  data: {
    loading: true,
    book: '',
    books: [],
    bookIndex: 0,
    d: null,
    view: {},
    accounts: [],
    // 柱状图：小程序没有图表库，用高度百分比画
    bars: [],
    // 明细切换
    detailTab: 'account',
    monthly: [],

    // 盘点
    showPrincipal: false,
    current: null,
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
      const params = {}
      if (this.data.book) params.book = this.data.book
      const d = await api.returns(params)

      const accounts = (d.accounts || []).map((a) => ({
        ...a,
        valueText: money(a.value_cents),
        principalText: money(a.principal_cents),
        profitText: signed(a.profit_cents),
        yearText: signed(a.year_profit_cents),
        rateText: a.profit_rate == null ? '—' : `${a.profit_rate.toFixed(2)}%`,
      }))

      // 趋势：跳过缺数据的月份，柱子高度按收益绝对值缩放
      const trend = (d.trend || []).filter((t) => t.profit_cents != null)
      const maxAbs = Math.max(
        1,
        ...trend.map((t) => Math.abs(t.profit_cents)),
      )
      const bars = trend.map((t) => ({
        ym: t.ym,
        label: t.ym.slice(5),
        profit: t.profit_cents,
        text: signed(t.profit_cents),
        // 负值往下长：容器上下各留一半，正柱从中间往上，负柱往下
        height: Math.max(6, Math.round((Math.abs(t.profit_cents) / maxAbs) * 46)),
        positive: t.profit_cents >= 0,
      }))

      const monthly = trend
        .filter((t) => t.month_profit_cents != null)
        .map((t) => ({
          ym: t.ym,
          label: `${t.ym.slice(5)} 月`,
          text: signed(t.month_profit_cents),
          positive: t.month_profit_cents >= 0,
        }))
        .reverse()

      const rawBooks = d.books || []
      this.setData({
        d,
        accounts,
        bars,
        monthly,
        books: rawBooks,
        // 第 0 项是「全部账本」，其余按后端给的有投资账户的账本排
        bookTabs: [
          { book_type: '', label: '全部账本' },
          ...rawBooks.map((b) => ({ ...b, label: `${b.label} (${b.count})` })),
        ],
        bookIndex: this.currentBookIndex(d),
        view: {
          value: money(d.value_cents || 0),
          principal: money(d.principal_cents || 0),
          profit: signed(d.profit_cents || 0),
          profitPositive: (d.profit_cents || 0) >= 0,
          rate: d.profit_rate == null ? '—' : `${d.profit_rate.toFixed(2)}%`,
          yearProfit: signed(d.year_profit_cents || 0),
          yearPositive: (d.year_profit_cents || 0) >= 0,
          yearRate: d.year_profit_rate == null ? '—' : `${d.year_profit_rate.toFixed(2)}%`,
          beginYm: d.begin_ym || '—',
          netAssets: money(d.net_assets_cents || 0),
          pct: d.profit_of_assets_pct == null ? '—' : `${d.profit_of_assets_pct.toFixed(2)}%`,
          yearPct: d.year_profit_of_assets_pct == null
            ? '—'
            : `${d.year_profit_of_assets_pct.toFixed(2)}%`,
          exProfit: money(d.assets_ex_profit_cents || 0),
          // 本金 / 收益占比条
          principalPct: this.ratio(d.principal_cents || 0, d.value_cents || 0),
        },
      })
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  currentBookIndex(d) {
    const books = d.books || []
    if (!this.data.book) return 0
    const idx = books.findIndex((b) => b.book_type === this.data.book)
    return idx < 0 ? 0 : idx + 1
  },

  ratio(part, total) {
    if (!total) return 0
    return Math.min(100, Math.round((part / total) * 100))
  },

  onBook(e) {
    const index = Number(e.detail.value)
    const books = this.data.books || []
    // 第 0 项是「全部账本」
    this.setData({ bookIndex: index, book: index === 0 ? '' : books[index - 1].book_type })
    this.load()
  },

  onDetailTab(e) {
    this.setData({ detailTab: e.currentTarget.dataset.tab })
  },

  // ---- 盘点
  openPrincipal(e) {
    const a = this.data.accounts.find((i) => i.id === e.currentTarget.dataset.id)
    if (!a) return
    this.setData({
      showPrincipal: true,
      current: a,
      principalValue: String(yuan(a.principal_cents)),
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

  goAccounts() {
    wx.navigateTo({ url: '/pages/accounts/accounts' })
  },
})
