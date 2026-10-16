const api = require('../../utils/api')
const { requireLogin } = require('../../utils/request')
const { yuan } = require('../../utils/money')

// 与 H5 AssetDetailSheet 保持一致：只用来兜底配色和图标，
// 名称一律以服务器返回的为准（家庭可自定义账本名）
const BOOK_META = {
  husband: { label: '账本一', icon: '🧾', color: '#1D9E75' },
  wife: { label: '账本二', icon: '🧾', color: '#E24B4A' },
  shared: { label: '共同账户', icon: '👥', color: '#7F77DD' },
}
const RECV_COLOR = '#1D9E75'

function fmt(n) {
  const neg = Number(n) < 0
  const parts = Math.abs(Number(n) || 0).toFixed(2).split('.')
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return (neg ? '-' : '') + parts.join('.')
}

function money(cents) {
  return '¥' + fmt(yuan(Number(cents) || 0))
}

function signed(cents) {
  const n = yuan(Number(cents) || 0)
  return (n >= 0 ? '+' : '-') + fmt(Math.abs(n))
}

function ymLabel(ym) {
  const arr = String(ym || '').split('-')
  return Number(arr[1]) + '月'
}

Page({
  data: {
    loading: true,
    loaded: false,

    // 净值曲线（CSS 柱状，小程序没有 echarts）
    bars: [],
    hasTrend: false,
    pointCount: 0,

    // 资产构成
    donutStyle: '',
    legends: [],
    assetBaseText: '¥0.00',

    // 净资产
    showNet: false,
    netLines: [],
    netText: '¥0.00',

    // 各账户详情：只列有数据的账本（合计为 0 的不展示）
    groups: [],

    // 借钱来往 / 不计入总资产
    lendText: '¥0.00',
    borrowText: '¥0.00',
    loanSummary: null,
    excluded: [],
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const res = await api.netValue()
      this.build(res || {})
      this.setData({ loaded: true })
    } catch (e) {
      if (requireLogin(e)) {
        // 未登录进不了本页：提示后回上一页（各 tab 首页已有登录引导）
        wx.navigateBack({ delta: 1 })
        return
      }
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  build(raw) {
    const labels = raw.book_labels || {}
    const accountCents = Number(raw.account_assets_cents ?? raw.total_assets_cents ?? 0)
    const receivableCents = Number(raw.receivable_cents || 0)
    const payableCents = Number(raw.payable_cents || 0)
    // 资产构成基数 = 账户余额 + 借出未收，保证各段之和与圆心数字一致
    const assetBaseCents = accountCents + receivableCents

    // ★ 合计为 0 的账本整组隐藏：空账本会占掉一整块，把有内容的挤出去。
    // 用 !== 0 而不是 > 0：信用卡等负余额账本是有数据的，必须保留。
    const visible = (raw.groups || []).filter((g) => Number(g.total_cents) !== 0)

    const groups = visible.map((g) => {
      const meta = BOOK_META[g.book_type] || { label: g.book_type, icon: '📁', color: '#888780' }
      const invests = (g.accounts || []).filter((a) => a.is_invest)
      const profit = invests.reduce((s, a) => s + Number(a.profit_cents || 0), 0)
      return {
        book_type: g.book_type,
        icon: meta.icon,
        color: meta.color,
        // 账本名取值顺序：分组自带 label → 顶层 book_labels → 内置默认
        label: g.label || labels[g.book_type] || meta.label,
        totalText: money(g.total_cents),
        profitText: profit ? signed(profit) : '',
        profitUp: profit > 0,
        accounts: (g.accounts || []).map((a) => ({
          ...a,
          balanceText: money(a.balance_cents),
          profitText: a.is_invest && Number(a.profit_cents) ? signed(a.profit_cents) : '',
          profitUp: Number(a.profit_cents) > 0,
          rateText:
            a.is_invest && Number(a.balance_cents)
              ? ((Number(a.profit_cents) / Number(a.balance_cents)) * 100).toFixed(1) + '%'
              : '',
        })),
      }
    })

    // 构成环：只有正数才能进环，负数段会让环变形
    const items = visible
      .filter((g) => Number(g.total_cents) > 0)
      .map((g) => ({
        name: g.label || labels[g.book_type] || BOOK_META[g.book_type].label,
        value: Number(g.total_cents),
        color: (BOOK_META[g.book_type] || {}).color || '#888780',
      }))
    if (receivableCents > 0) {
      items.push({ name: '借出未收', value: receivableCents, color: RECV_COLOR })
    }

    let donutStyle = ''
    if (items.length && assetBaseCents > 0) {
      let acc = 0
      const segs = items.map((i) => {
        const p = (i.value / assetBaseCents) * 100
        const seg = `${i.color} ${acc.toFixed(2)}% ${(acc + p).toFixed(2)}%`
        acc += p
        return seg
      })
      donutStyle = `background: conic-gradient(${segs.join(', ')})`
    }

    const legends = items.map((i) => ({
      color: i.color,
      name: i.name,
      amountText: money(i.value),
      pct: assetBaseCents ? Math.round((i.value / assetBaseCents) * 100) : 0,
    }))

    // 净值曲线：缺快照的月份直接跳过
    const points = (raw.trend || []).filter(
      (p) => p.assets_cents !== null && p.assets_cents !== undefined,
    )
    const values = points.map((p) => Number(p.assets_cents))
    const max = values.length ? Math.max.apply(null, values) : 0
    const min = values.length ? Math.min.apply(null, values) : 0
    const span = max - min
    const bars = points.map((p) => {
      const v = Number(p.assets_cents)
      const ratio = span > 0 ? (v - min) / span : 0.6
      return {
        ym: p.ym,
        label: ymLabel(p.ym),
        // 最低也给 8%，避免首尾月变成一条看不见的线
        height: (8 + ratio * 92).toFixed(1) + '%',
        value: Math.round(v / 100),
      }
    })

    const netLines = [
      { key: 'account', icon: '🏦', label: '账户资产', text: money(accountCents), cls: '' },
    ]
    if (receivableCents > 0) {
      netLines.push({
        key: 'recv',
        icon: '🤝',
        label: '借出未收（应收）',
        text: money(receivableCents),
        cls: 'plus',
      })
    }
    if (payableCents > 0) {
      netLines.push({
        key: 'pay',
        icon: '📥',
        label: '借入未还（负债）',
        text: money(-payableCents),
        cls: 'minus',
      })
    }

    this.setData({
      bars,
      hasTrend: points.length > 1,
      pointCount: points.length,
      donutStyle,
      legends,
      assetBaseText: money(assetBaseCents),
      showNet: payableCents > 0,
      netLines,
      netText: money(assetBaseCents - payableCents),
      groups,
      lendText: money(receivableCents),
      borrowText: money(payableCents),
      loanSummary: raw.loans || null,
      excluded: (raw.excluded_accounts || []).map((a) => ({
        ...a,
        balanceText: money(a.balance_cents),
      })),
    })
  },

  goLoans() {
    wx.navigateTo({ url: '/pages/loans/loans' })
  },
})
