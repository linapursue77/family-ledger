const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')

// 周期与 H5 Report.vue 完全一致
const PRESETS = [
  { key: 'last_week', label: '近1周' },
  { key: 'last_month', label: '近1月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
  { key: 'last_year', label: '近一年' },
]

// 成员头像用中性图标，不预设身份（与 H5 同）
const MEMBER_EMOJI = { husband: '🧑', wife: '👤', shared: '👥' }

/** 千分位 + 固定两位小数，等价 H5 的 toLocaleString('zh-CN', {min/max:2}) */
function fmt(n) {
  const v = Number(n || 0)
  const neg = v < 0
  const [int, dec] = Math.abs(v).toFixed(2).split('.')
  const s = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return (neg ? '-' : '') + s + '.' + dec
}

/** 分为单位转元并去掉无意义的末尾 0，等价 H5 的 fm() */
function fm(cents) {
  const v = yuan(cents)
  const s = String(Math.abs(v)).replace(/\.?0+$/, '')
  return (v < 0 ? '-' : '') + (s === '' ? '0' : s)
}

function memberEmoji(book) {
  return MEMBER_EMOJI[book] || '👤'
}

/** #RRGGBB → rgba()。8 位 hex（#RRGGBBAA）在部分基础库上不支持，统一转 rgba 更稳 */
function rgba(hex, a) {
  const h = String(hex || '').replace('#', '')
  if (h.length !== 6) return `rgba(140,140,140,${a})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

/** 健康分 → 环形颜色 */
function scoreColor(s) {
  if (s == null) return '#c8c6c0'
  if (s >= 70) return '#1d9e75'
  if (s >= 55) return '#7f77dd'
  if (s >= 40) return '#ef9f27'
  return '#e24b4a'
}

/** 分类占比拼成 conic-gradient，零依赖画环形图 */
function donutGradient(categories) {
  if (!categories.length) return 'none'
  let acc = 0
  const parts = categories.map((c) => {
    const start = acc
    const end = acc + Math.max(0, Math.min(Number(c.percent) || 0, 100))
    acc = end
    return `${c.color || '#cccccc'} ${start}% ${end}%`
  })
  return `conic-gradient(${parts.join(', ')})`
}

/** y 轴刻度取整好看的步长 */
function niceStep(raw) {
  if (!(raw > 0)) return 1
  const exp = Math.pow(10, Math.floor(Math.log10(raw)))
  const f = raw / exp
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10
  return nf * exp
}

function kmb(v) {
  if (v >= 10000) return (v / 10000).toFixed(v % 10000 ? 1 : 0) + '万'
  if (v >= 1000) return (v / 1000).toFixed(v % 1000 ? 1 : 0) + 'k'
  return String(Math.round(v))
}

Page({
  data: {
    presets: PRESETS,
    preset: 'last_month',
    type: 'expense',
    accountId: '',

    loading: true,
    range: {},
    summary: {},
    categories: [],
    byMember: [],
    filterableAccounts: [],
    scope: null,
    typeLabel: '支出',
    isExpense: true,
    scopeName: '全部账户',
    perAvgText: '0.00',
    donut: 'none',
    hasData: false,

    // 智能分析
    insight: null,
    // 首屏只展示前两条洞察，其余折叠，避免一屏全是文字
    insightShown: [],
    insightMore: false,
    insightLoading: false,
    insightError: '',
    useAI: false,
    aiAvailable: false,
    insightSource: '',
    scoreColor: '#c8c6c0',
    scoreRing: 'none',

    // 分类下钻
    showCategory: false,
    activeCat: null,
    catTxs: [],
    catFilter: 'all',
    members: [],
    filteredTxs: [],
    filteredTotal: '0',
  },

  onShow() {
    this.load()
  },

  // ---------- 加载
  async load() {
    this.setData({ loading: true })
    try {
      const d = await api.report({
        preset: this.data.preset,
        type: this.data.type,
        account_id: this.data.accountId || undefined,
      })
      this.applyReport(d)
      this.loadInsight()
    } catch (e) {
      if (requireLogin(e)) return
      // VIP 权益等限制直接告诉用户，移动端静默失败体验太差
      wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      this.setData({ hasData: false, categories: [], byMember: [], donut: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  /** 把后端数据整理成 WXML 直接可用的形状 */
  applyReport(d) {
    const range = d.range || {}
    const summary = d.summary || {}
    const categories = d.categories || []
    const byAccount = d.by_account || []
    const scope = d.scope || null
    const isExpense = this.data.type === 'expense'
    const typeLabel = isExpense ? '支出' : '收入'
    const count = Number(summary.count) || 0
    const perAvg = count ? Number(summary.total || 0) / count : 0
    // 后端只给 book_type，头像要到这一层换成 emoji；金额补千分位对齐 H5 的 fmt()
    const byMember = (d.by_member || []).map((m) => ({
      ...m,
      avatar: memberEmoji(m.book_type),
      amount: fmt(m.amount),
    }))
    const cats = categories.map((c) => ({
      ...c,
      amount: fmt(c.amount),
      w: Math.max(Number(c.percent) || 0, 1),
      bg: rgba(c.color, 0.12),
    }))
    const summaryView = {
      count: summary.count,
      total: fmt(summary.total),
      income: fmt(summary.income),
      expense: fmt(summary.expense),
      balance: fmt(summary.balance),
      avg_daily: fmt(summary.avg_daily),
      expense_of_income: summary.expense_of_income,
      saving_rate: summary.saving_rate,
    }

    this.setData(
      {
        range,
        summary: summaryView,
        categories: cats,
        byMember,
        scope,
        isExpense,
        typeLabel,
        perAvgText: fmt(perAvg),
        // 「未指定账户」没有 id，选它等同「全部」，不进筛选条
        filterableAccounts: byAccount.filter((a) => a.account_id),
        scopeName: scope ? `${scope.icon || '💰'} ${scope.name}` : '全部账户',
        donut: donutGradient(categories),
        hasData: true,
      },
      () => this.drawTrend(d.trend || []),
    )
  },

  // ---------- 智能分析（后端规则引擎，与报告同源同口径）
  async loadInsight() {
    this.setData({ insightLoading: true, insightError: '' })
    try {
      const res = await api.reportInsight({
        preset: this.data.preset,
        type: this.data.type,
        account_id: this.data.accountId || undefined,
        ai: this.data.useAI ? 1 : 0,
      })
      const ai = res.ai || {}
      let source = '本地规则引擎 · 数据不外传'
      if (ai.used) source = `AI 分析 · ${ai.model || '大模型'}`
      else if (ai.reason) source = `本地规则引擎 · ${ai.reason}`
      const all = res.insights || []
      this.setData({
        insight: res,
        // 默认折叠：首屏给前两条，剩下的点「展开全部」再看
        insightShown: this.data.insightMore ? all : all.slice(0, 2),
        aiAvailable: !!ai.enabled,
        insightSource: source,
        scoreColor: scoreColor(res.score),
        scoreRing:
          res.score == null
            ? 'none'
            : `conic-gradient(${scoreColor(res.score)} ${res.score * 3.6}deg, #ecebe6 0)`,
      })
    } catch (e) {
      if (!requireLogin(e)) this.setData({ insightError: (e && e.message) || '分析失败' })
    } finally {
      this.setData({ insightLoading: false })
    }
  },

  toggleInsightMore() {
    const more = !this.data.insightMore
    const all = (this.data.insight && this.data.insight.insights) || []
    this.setData({
      insightMore: more,
      insightShown: more ? all : all.slice(0, 2),
    })
  },

  toggleAI() {
    if (!this.data.aiAvailable) return
    const useAI = !this.data.useAI
    wx.setStorageSync('insight_use_ai', useAI ? '1' : '0')
    this.setData({ useAI })
    this.loadInsight()
  },

  // ---------- 交互
  onPreset(e) {
    this.setData({ preset: e.currentTarget.dataset.key })
    this.load()
  },

  onType(e) {
    this.setData({ type: e.currentTarget.dataset.key })
    this.load()
  },

  onAccount(e) {
    this.setData({ accountId: e.currentTarget.dataset.id || '' })
    this.load()
  },

  // ---------- 分类下钻
  async openCat(e) {
    const id = e.currentTarget.dataset.id
    const cat = this.data.categories.find((c) => String(c.category_id) === String(id))
    if (!cat) return
    this.setData({
      activeCat: cat,
      catTxs: [],
      filteredTxs: [],
      catFilter: 'all',
      showCategory: true,
    })
    try {
      const [list, me] = await Promise.all([
        api.transactions({
          category: cat.category_id,
          date_from: this.data.range.start,
          date_to: this.data.range.end,
          page_size: 200,
        }),
        this.data.members.length ? Promise.resolve(null) : api.familyMe(),
      ])
      if (me && me.members) this.setData({ members: me.members })
      const catTxs = (list && list.items ? list.items : []).map((t) => ({
        ...t,
        dateText: (t.transaction_date || '').slice(0, 10),
        dayText: (t.transaction_date || '').slice(5, 10),
        amountText: fm(t.amount_cents),
        isIncome: t.type === 'income',
        memberText: '',
        avatar: '',
      }))
      this.setData({ catTxs }, () => this.applyCatFilter())
    } catch (e) {
      wx.showToast({ title: '明细加载失败', icon: 'none' })
    }
  },

  closeCat() {
    this.setData({ showCategory: false })
  },

  onCatFilter(e) {
    this.setData({ catFilter: String(e.currentTarget.dataset.id || 'all') })
    this.applyCatFilter()
  },

  applyCatFilter() {
    const { catTxs, catFilter, members } = this.data
    const memberMap = {}
    members.forEach((m) => {
      memberMap[String(m.user)] = m
    })
    const list = (catFilter === 'all'
      ? catTxs
      : catTxs.filter((t) => String(t.user_id) === String(catFilter))
    ).map((t) => {
      const m = memberMap[String(t.user_id)]
      return {
        ...t,
        avatar: memberEmoji(m && m.book_type),
        memberText: m ? m.nickname || m.username || '成员' : '未知成员',
      }
    })
    const total = list.reduce((s, t) => s + Number(t.amount_cents || 0), 0)
    this.setData({ filteredTxs: list, filteredTotal: fm(total) })
  },

  // ---------- 趋势图：零依赖，canvas 2d 手绘（图例交给 WXML）
  drawTrend(trend) {
    if (!trend || !trend.length) {
      this.setData({ trendEmpty: true })
      return
    }
    this.setData({ trendEmpty: false })
    const query = wx.createSelectorQuery().in(this)
    query
      .select('#trendCanvas')
      .fields({ node: true, size: true })
      .exec((res) => {
        const info = res && res[0]
        if (!info || !info.node) return
        const canvas = info.node
        const ctx = canvas.getContext('2d')
        const dpr = wx.getSystemInfoSync().pixelRatio || 1
        const w = info.width
        const h = info.height
        canvas.width = w * dpr
        canvas.height = h * dpr
        ctx.clearRect(0, 0, w, h)
        ctx.scale(dpr, dpr)

        const pad = { l: 36, r: 8, t: 10, b: 20 }
        const cw = w - pad.l - pad.r
        const ch = h - pad.t - pad.b
        if (cw <= 0 || ch <= 0) return

        let maxV = 0
        trend.forEach((t) => {
          maxV = Math.max(maxV, Number(t.income) || 0, Number(t.expense) || 0)
        })
        const step = niceStep(maxV / 4 || 1)
        const top = Math.max(step, Math.ceil(maxV / step) * step)

        const X = (i) => (trend.length === 1 ? pad.l + cw / 2 : pad.l + (cw * i) / (trend.length - 1))
        const Y = (v) => pad.t + ch - (ch * v) / top

        // 网格 + y 轴刻度
        ctx.font = '10px sans-serif'
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        ctx.lineWidth = 1
        for (let v = 0; v <= top; v += step) {
          const y = Y(v)
          ctx.beginPath()
          ctx.strokeStyle = '#f1efe8'
          ctx.moveTo(pad.l, y)
          ctx.lineTo(pad.l + cw, y)
          ctx.stroke()
          ctx.fillStyle = '#888780'
          ctx.fillText(kmb(v), pad.l - 4, y)
        }

        // x 轴标签：点多了就隔个显示
        // ★ trend.label 本身就是 '10-01' 这种短标签（不是完整日期），直接画，
        //   不能按 transaction_date 的习惯去 slice，否则会截成空串
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        const every = Math.ceil(trend.length / 6)
        trend.forEach((t, i) => {
          if (i % every !== 0 && i !== trend.length - 1) return
          ctx.fillStyle = '#888780'
          ctx.fillText(String(t.label), X(i), pad.t + ch + 5)
        })

        // 收支双折线：当前查看的口径加粗
        const series = [
          { key: 'income', color: '#1d9e75' },
          { key: 'expense', color: '#e24b4a' },
        ]
        series.forEach((s) => {
          const active = this.data.type === s.key
          ctx.beginPath()
          trend.forEach((t, i) => {
            const x = X(i)
            const y = Y(Number(t[s.key]) || 0)
            if (i === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          })
          ctx.strokeStyle = s.color
          ctx.lineWidth = active ? 3 : 1.5
          ctx.lineJoin = 'round'
          ctx.lineCap = 'round'
          ctx.stroke()

          ctx.fillStyle = s.color
          trend.forEach((t, i) => {
            ctx.beginPath()
            ctx.arc(X(i), Y(Number(t[s.key]) || 0), active ? 3 : 2, 0, Math.PI * 2)
            ctx.fill()
          })
        })
      })
  },
})
