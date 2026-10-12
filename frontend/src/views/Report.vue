<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ledgerApi, familyApi } from '@/api'

const periods = [
  { key: 'last_week', label: '近1周' },
  { key: 'last_month', label: '近1月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
  { key: 'last_year', label: '近一年' },
]

const preset = ref('last_month')
const type = ref('expense')
const accountId = ref('')

const data = ref(null)
const loading = ref(true)
// —— 智能分析（后端规则引擎，与报告同源同口径）——
const insight = ref(null)
const insightLoading = ref(false)
const insightError = ref('')
// AI 分析开关：后端未配置大模型时（ai.enabled=false）自动回落到本地规则引擎
const useAI = ref(localStorage.getItem('insight_use_ai') === '1')
const aiAvailable = computed(() => !!insight.value?.ai?.enabled)
const insightSource = computed(() => {
  const ai = insight.value?.ai
  if (!ai) return '本地规则引擎 · 数据不外传'
  if (ai.used) return `AI 分析 · ${ai.model || '大模型'}`
  return ai.reason ? `本地规则引擎 · ${ai.reason}` : '本地规则引擎 · 数据不外传'
})
function toggleAI() {
  if (!aiAvailable.value) return
  useAI.value = !useAI.value
  localStorage.setItem('insight_use_ai', useAI.value ? '1' : '0')
  loadInsight()
}
const trendEl = ref(null)
let trendChart = null

const range = computed(() => data.value?.range || {})
const summary = computed(() => data.value?.summary || {})
const categories = computed(() => data.value?.categories || [])
const byAccount = computed(() => data.value?.by_account || [])
const byMember = computed(() => data.value?.by_member || [])
const scope = computed(() => data.value?.scope || null)
// 账户筛选只列出真实账户：「未指定账户」没有 id，选它等同于「全部」
const filterableAccounts = computed(() => byAccount.value.filter((a) => a.account_id))
// 笔均 = 合计 / 笔数
const perAvg = computed(() => {
  const c = Number(summary.value.count) || 0
  return c ? summary.value.total / c : 0
})

// 成员头像用中性图标 + 配色区分，不预设身份
const MEMBER_EMOJI = { husband: '🧑', wife: '👤', shared: '👥' }
function memberEmoji(book) {
  return MEMBER_EMOJI[book] || '👤'
}

// 后端返回的金额已是「元」，这里只做千分位展示
function fmt(n) {
  return Number(n || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

// 健康分 → 环形进度颜色
function scoreColor(s) {
  if (s == null) return '#c8c6c0'
  if (s >= 70) return '#1d9e75'
  if (s >= 55) return '#7f77dd'
  if (s >= 40) return '#ef9f27'
  return '#e24b4a'
}

const isExpense = computed(() => type.value === 'expense')
const typeLabel = computed(() => (isExpense.value ? '支出' : '收入'))

const scopeName = computed(() =>
  scope.value ? `${scope.value.icon || '💰'} ${scope.value.name}` : '全部账户'
)

// —— 分类占比环形图 ——
const pieEl = ref(null)
let pieChart = null
function renderPie() {
  if (!pieEl.value) return
  if (!pieChart) pieChart = echarts.init(pieEl.value)
  pieChart.setOption({
    series: [
      {
        type: 'pie',
        radius: ['55%', '80%'],
        avoidLabelOverlap: false,
        label: { show: false },
        data: categories.value.map((c) => ({
          name: c.name,
          value: c.percent,
          itemStyle: { color: c.color },
        })),
      },
    ],
  })
}

// —— 分类下钻：逐笔明细 ——
const showCategory = ref(false)
const activeCat = ref(null)
const catTxs = ref([])
const catFilter = ref('all')
const members = ref([])
const memberMap = computed(() => {
  const m = {}
  members.value.forEach((x) => (m[String(x.user)] = x))
  return m
})
function memberLabel(userId) {
  const m = memberMap.value[String(userId)]
  if (!m) return '未知成员'
  return m.nickname || m.username || '成员'
}
// ★ 与上方成员分布用的 memberEmoji(book_type) 区分：这里按 user_id 查账本再取头像
function txMemberEmoji(userId) {
  const m = memberMap.value[String(userId)]
  if (!m) return '🙂'
  return memberEmoji(m.book_type)
}
const filteredTxs = computed(() =>
  catFilter.value === 'all'
    ? catTxs.value
    : catTxs.value.filter((t) => String(t.user_id) === String(catFilter.value))
)
const filteredTotal = computed(() =>
  filteredTxs.value.reduce((s, t) => s + Number(t.amount_cents || 0), 0)
)
function fm(cents) {
  return (Number(cents || 0) / 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
}
async function openCat(cat) {
  activeCat.value = cat
  catTxs.value = []
  catFilter.value = 'all'
  showCategory.value = true
  try {
    const [list, me] = await Promise.all([
      ledgerApi.transactions({
        category: cat.category_id,
        date_from: range.value.start,
        date_to: range.value.end,
        page_size: 200,
      }),
      members.value.length ? Promise.resolve(null) : familyApi.me(),
    ])
    if (me?.members) members.value = me.members
    catTxs.value = (list?.items || []).map((t) => ({
      ...t,
      dateText: (t.transaction_date || '').slice(0, 10),
    }))
  } catch (e) {
    console.error(e)
  }
}

async function load() {
  loading.value = true
  try {
    data.value = await ledgerApi.report({
      preset: preset.value,
      type: type.value,
      account_id: accountId.value || undefined,
    })
    await nextTick()
    renderPie()
    renderTrend()
    loadInsight()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 分析单独请求：报告先出图，分析结果随后补上，不阻塞主流程
async function loadInsight() {
  insightLoading.value = true
  insightError.value = ''
  try {
    insight.value = await ledgerApi.reportInsight({
      preset: preset.value,
      type: type.value,
      account_id: accountId.value || undefined,
      ai: useAI.value ? 1 : 0,
    })
  } catch (e) {
    insightError.value = e?.message || '分析失败'
  } finally {
    insightLoading.value = false
  }
}

function renderTrend() {
  if (!trendEl.value) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  const trend = data.value?.trend || []
  // 当前查看的口径（收入/支出）用粗线强调，另一条做对照
  const lineWidth = (key) => (type.value === key ? 3 : 1.5)
  trendChart.setOption({
    grid: { left: 4, right: 8, top: 30, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['收入', '支出'],
      top: 0,
      right: 0,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#5f5e5a' },
    },
    xAxis: {
      type: 'category',
      data: trend.map((t) => t.label),
      axisLabel: { fontSize: 10, color: '#888780' },
      axisLine: { lineStyle: { color: '#e8e8e8' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: '#888780' },
      splitLine: { lineStyle: { color: '#f1efe8' } },
    },
    series: [
      {
        name: '收入',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: trend.map((t) => t.income),
        itemStyle: { color: '#1d9e75' },
        lineStyle: { width: lineWidth('income'), color: '#1d9e75' },
      },
      {
        name: '支出',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: trend.map((t) => t.expense),
        itemStyle: { color: '#e24b4a' },
        lineStyle: { width: lineWidth('expense'), color: '#e24b4a' },
      },
    ],
  })
}

function onResize() {
  trendChart && trendChart.resize()
  pieChart && pieChart.resize()
}

watch([preset, type, accountId], load)

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  trendChart && trendChart.dispose()
  pieChart && pieChart.dispose()
})
</script>

<template>
  <div class="page report-page">
    <div class="navbar">
      <span class="navbar-title">收支报告</span>
      <span class="range-text text-muted">{{ range.start }} ~ {{ range.end }}</span>
    </div>

    <!-- 周期 -->
    <div class="chip-row">
      <span
        v-for="p in periods"
        :key="p.key"
        class="chip"
        :class="{ active: preset === p.key }"
        @click="preset = p.key"
      >{{ p.label }}</span>
    </div>

    <!-- 收入 / 支出 主切换 -->
    <div class="type-switch">
      <div
        class="switch-item expense"
        :class="{ active: isExpense }"
        @click="type = 'expense'"
      >
        <span class="sw-label">💸 支出报告</span>
        <span class="sw-amount">¥{{ fmt(summary.expense) }}</span>
      </div>
      <div
        class="switch-item income"
        :class="{ active: !isExpense }"
        @click="type = 'income'"
      >
        <span class="sw-label">💰 收入报告</span>
        <span class="sw-amount">¥{{ fmt(summary.income) }}</span>
      </div>
    </div>

    <!-- 账户范围 -->
    <div class="chip-row">
      <span class="chip" :class="{ active: !accountId }" @click="accountId = ''">全部账户</span>
      <span
        v-for="a in filterableAccounts"
        :key="a.account_id"
        class="chip"
        :class="{ active: accountId === a.account_id }"
        @click="accountId = a.account_id"
      >{{ a.icon }} {{ a.name }}</span>
    </div>

    <!-- 汇总 -->
    <div class="card hero" :class="isExpense ? 'hero-expense' : 'hero-income'">
      <div class="hero-top">
        <span>{{ range.label }} · {{ scopeName }}</span>
      </div>
      <div class="hero-amount">¥{{ fmt(summary.total) }}</div>
      <div class="hero-sub">
        {{ typeLabel }}合计 · {{ summary.count }} 笔
      </div>
      <div class="hero-stats">
        <div class="stat">
          <b>¥{{ fmt(summary.avg_daily) }}</b>
          <span>日均{{ typeLabel }}</span>
        </div>
        <div class="stat">
          <b>¥{{ fmt(perAvg) }}</b>
          <span>笔均{{ typeLabel }}</span>
        </div>
        <div class="stat">
          <b v-if="isExpense">{{ summary.expense_of_income }}%</b>
          <b v-else>{{ summary.saving_rate }}%</b>
          <span>{{ isExpense ? '占收入' : '储蓄率' }}</span>
        </div>
      </div>
    </div>

    <!-- 智能分析：健康分 + 洞察 + 改进建议（后端规则引擎，与报告同口径） -->
    <div class="card insight-card">
      <div class="sec-title">
        智能分析
        <span class="insight-sub">{{ insightSource }}</span>
      </div>

      <div class="ai-bar">
        <span class="ai-tip">
          {{ aiAvailable ? '已接入大模型，可切换分析方式' : '未配置大模型，当前使用本地规则分析' }}
        </span>
        <span
          class="ai-switch"
          :class="{ on: useAI && aiAvailable, off: !aiAvailable }"
          @click="toggleAI"
        >
          <span class="ai-dot"></span>{{ useAI && aiAvailable ? 'AI' : '本地' }}
        </span>
      </div>

      <div v-if="insightLoading && !insight" class="insight-loading">
        {{ useAI && aiAvailable ? 'AI 分析中…' : '正在分析…' }}
      </div>
      <div v-else-if="insightError" class="insight-error">
        {{ insightError }}<span class="retry" @click="loadInsight">重试</span>
      </div>
      <template v-else-if="insight">
        <div class="insight-hero">
          <div
            class="score-ring"
            :style="{ '--pct': insight.score ?? 0, '--ring': scoreColor(insight.score) }"
          >
            <span class="score-num">{{ insight.score ?? '--' }}</span>
            <span class="score-unit">分</span>
          </div>
          <div class="insight-hero-main">
            <div class="score-label">财务健康度 · {{ insight.score_label }}</div>
            <div class="score-text">{{ insight.summary_text }}</div>
          </div>
        </div>
        <div v-if="insight.prev_range" class="insight-cmp">
          环比基准 {{ insight.prev_range.start }} ~ {{ insight.prev_range.end }}
        </div>
        <div
          v-for="(i, idx) in insight.insights"
          :key="idx"
          class="insight-item"
          :class="'lv-' + i.level"
        >
          <span class="ins-ic">{{ i.icon }}</span>
          <div class="ins-main">
            <div class="ins-title">{{ i.title }}</div>
            <div class="ins-detail">{{ i.detail }}</div>
            <div class="ins-sug">建议：{{ i.suggestion }}</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 分类占比 + 明细（点击分类看下钻流水） -->
    <div class="card">
      <div class="sec-title">{{ typeLabel }}分类明细</div>
      <div v-if="categories.length" class="pie-row">
        <div ref="pieEl" class="pie"></div>
        <div class="mini-legend">
          <div v-for="c in categories" :key="'lg' + c.category_id" class="legend-row">
            <span class="legend-name">{{ c.icon }} {{ c.name }}</span>
            <span class="legend-pct">{{ c.percent }}%</span>
          </div>
        </div>
      </div>
      <div v-if="!categories.length" class="empty-sm">该区间暂无{{ typeLabel }}记录</div>
      <div v-for="c in categories" :key="c.category_id" class="cat-row" @click="openCat(c)">
        <span class="cat-icon" :style="{ background: c.color + '1f', color: c.color }">{{ c.icon }}</span>
        <div class="cat-main">
          <div class="cat-line">
            <span class="cat-name">{{ c.name }}</span>
            <span class="cat-right">
              <b class="cat-amt">¥{{ fmt(c.amount) }}</b>
              <span class="cat-pct">{{ c.percent }}%</span>
            </span>
          </div>
          <div class="bar">
            <span :style="{ width: Math.max(c.percent, 1) + '%', background: c.color }"></span>
          </div>
        </div>
        <span class="cat-count">{{ c.count }}笔</span>
      </div>
    </div>

    <!-- 账户维度：仅在筛选到具体账户时展示收支概览（全部账户时不再重复列分布，上方 chip 已可切换） -->
    <div class="card" v-if="accountId">
      <div class="sec-title">当前账户收支</div>
      <div class="acc-summary">
        <div class="as-item">
          <span class="as-label">收入</span>
          <span class="as-val text-income">¥{{ fmt(summary.income) }}</span>
        </div>
        <div class="as-item">
          <span class="as-label">支出</span>
          <span class="as-val text-expense">¥{{ fmt(summary.expense) }}</span>
        </div>
        <div class="as-item">
          <span class="as-label">结余</span>
          <span class="as-val">¥{{ fmt(summary.balance) }}</span>
        </div>
      </div>
    </div>

    <!-- 成员维度 -->
    <div class="card">
      <div class="sec-title">成员{{ typeLabel }}分布</div>
      <div v-if="!byMember.length" class="empty-sm">该区间暂无{{ typeLabel }}记录</div>
      <div v-for="m in byMember" :key="m.user_id" class="mem-row">
        <span class="mem-avatar">{{ memberEmoji(m.book_type) }}</span>
        <div class="mem-main">
          <div class="mem-line">
            <span class="mem-name">{{ m.name }}</span>
            <span class="mem-amt">¥{{ fmt(m.amount) }}<em>{{ m.percent }}%</em></span>
          </div>
          <div class="bar">
            <span
              class="bar-fill"
              :class="isExpense ? 'fill-expense' : 'fill-income'"
              :style="{ width: Math.max(m.percent, 1) + '%' }"
            ></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 趋势 -->
    <div class="card">
      <div class="sec-title">
        收支趋势
        <span class="unit">单位：元 · 当前口径「{{ typeLabel }}」加粗显示</span>
      </div>
      <div ref="trendEl" class="trend"></div>
    </div>

    <div v-if="loading" class="loading-tip">加载中…</div>

    <!-- 分类逐笔明细弹窗 -->
    <div v-if="showCategory" class="cat-mask" @click="showCategory = false">
      <div class="cat-card" @click.stop>
        <div class="cat-head">
          <span class="cat-head-title">{{ activeCat.icon }} {{ activeCat.name }} 明细</span>
          <span class="cat-head-close" @click="showCategory = false">×</span>
        </div>
        <div class="cat-body">
          <div class="cat-summary">
            <div class="cat-summary-icon" :style="{ background: (activeCat.color || '#8d6e63') + '1a' }">
              {{ activeCat.icon }}
            </div>
            <div class="cat-summary-info">
              <div class="cat-summary-name">{{ activeCat.name }} · {{ filteredTxs.length }} 笔</div>
              <div
                class="cat-summary-amount"
                :class="isExpense ? 'text-expense' : 'text-income'"
              >¥{{ fm(filteredTotal) }}</div>
            </div>
          </div>

          <div class="cat-filters">
            <span class="cat-filter" :class="{ active: catFilter === 'all' }" @click="catFilter = 'all'">全部</span>
            <span
              v-for="m in members"
              :key="m.id"
              class="cat-filter"
              :class="{ active: catFilter === String(m.user) }"
              @click="catFilter = String(m.user)"
            >{{ m.book_type === 'wife' ? '👤' : '🧑' }} {{ m.nickname || m.username }}</span>
          </div>

          <div class="cat-list">
            <div v-for="t in filteredTxs" :key="t.id" class="cat-tx">
              <span class="cat-tx-avatar">{{ txMemberEmoji(t.user_id) }}</span>
              <div class="cat-tx-info">
                <div class="cat-tx-title">{{ t.merchant || '未填写商户' }}</div>
                <div class="cat-tx-sub">
                  {{ memberLabel(t.user_id) }} · {{ (t.transaction_date || '').slice(5, 10) }}<template v-if="t.description"> · {{ t.description }}</template>
                </div>
              </div>
              <span :class="['cat-tx-amount', t.type === 'income' ? 'text-income' : 'text-expense']">
                {{ t.type === 'income' ? '+' : '-' }}¥{{ fm(t.amount_cents) }}
              </span>
            </div>
            <div v-if="!filteredTxs.length" class="cat-empty">暂无记录</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-page {
  /* ★ 底部必须留出 TabBar 高度，否则最后一张卡（趋势图）会被导航遮住 */
  padding: 0 16px calc(var(--nav-h) + 24px);
}
/* 各卡片之间统一留间距，并补左右内边距，避免金额/笔数贴边溢出 */
.report-page .card {
  padding: 14px 16px;
  margin-bottom: 12px;
}
.report-page .card:last-of-type {
  margin-bottom: 0;
}
.navbar {
  padding: 12px 0 8px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.range-text {
  font-size: var(--font-xs);
}
.chip-row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
  margin-bottom: 12px;
  scrollbar-width: none;
}
.chip-row::-webkit-scrollbar {
  display: none;
}
.chip {
  flex: none;
}

/* 收入 / 支出 主切换 */
.type-switch {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.switch-item {
  flex: 1;
  padding: 12px;
  border-radius: var(--radius-card);
  background: #fff;
  border: 0.5px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.switch-item .sw-label {
  font-size: var(--font-sm);
  color: var(--text-sub);
}
.switch-item .sw-amount {
  font-size: 17px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-main);
}
.switch-item.active.expense {
  background: #fdecec;
  border-color: var(--expense);
}
.switch-item.active.expense .sw-label,
.switch-item.active.expense .sw-amount {
  color: var(--expense);
}
.switch-item.active.income {
  background: #e8f5f0;
  border-color: var(--income);
}
.switch-item.active.income .sw-label,
.switch-item.active.income .sw-amount {
  color: var(--income);
}

/* 汇总卡 */
.hero {
  padding: 16px;
  margin-bottom: 12px;
  color: #fff;
  border: none;
}
.hero-expense {
  background: linear-gradient(135deg, #e24b4a, #b8322f);
}
.hero-income {
  background: linear-gradient(135deg, #1d9e75, #157a5b);
}
.hero-top {
  font-size: var(--font-sm);
  opacity: 0.9;
}
.hero-amount {
  font-size: 30px;
  font-weight: 700;
  margin: 8px 0 2px;
  font-variant-numeric: tabular-nums;
}
.hero-sub {
  font-size: var(--font-xs);
  opacity: 0.9;
}
.hero-stats {
  display: flex;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 0.5px solid rgba(255, 255, 255, 0.28);
}
.stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}
.stat b {
  font-size: var(--font-md);
  font-variant-numeric: tabular-nums;
}
.stat span {
  font-size: 11px;
  opacity: 0.85;
}

/* ---------- 智能分析 ---------- */
.insight-sub {
  float: right;
  font-size: 10px;
  font-weight: 400;
  color: var(--text-muted);
  line-height: 1.8;
}
/* AI / 本地分析切换：后端未配置大模型时开关置灰，强制走本地 */
.ai-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.ai-tip {
  font-size: 11px;
  color: var(--text-muted);
}
.ai-switch {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 20px;
  background: #f1efe8;
  color: #888780;
  cursor: pointer;
}
.ai-switch.on {
  background: var(--primary);
  color: #fff;
}
.ai-switch.off {
  opacity: 0.45;
  cursor: not-allowed;
}
.ai-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.insight-loading,
.insight-error {
  font-size: var(--font-sm);
  color: var(--text-muted);
  padding: 6px 0;
}
.insight-error .retry {
  color: var(--primary);
  margin-left: 8px;
  cursor: pointer;
}
.insight-hero {
  display: flex;
  align-items: center;
  gap: 14px;
}
.score-ring {
  position: relative;
  flex: none;
  width: 62px;
  height: 62px;
  border-radius: 50%;
  background: conic-gradient(var(--ring) calc(var(--pct) * 1%), #f1efe8 0);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.score-ring::after {
  content: '';
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: #fff;
}
.score-num {
  position: relative;
  z-index: 1;
  font-size: 19px;
  font-weight: 700;
  color: var(--text-main);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.score-unit {
  position: relative;
  z-index: 1;
  font-size: 10px;
  color: var(--text-muted);
}
.insight-hero-main {
  flex: 1;
  min-width: 0;
}
.score-label {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}
.score-text {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
  margin-top: 4px;
}
.insight-cmp {
  margin-top: 12px;
  font-size: 10px;
  color: var(--text-muted);
}
.insight-item {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  padding: 8px 0 8px 10px;
  border-left: 3px solid #e8e8e8;
  background: #faf9f6;
  border-radius: 0 8px 8px 0;
}
.insight-item.lv-good {
  border-left-color: #1d9e75;
}
.insight-item.lv-info {
  border-left-color: #7f77dd;
}
.insight-item.lv-warn {
  border-left-color: #ef9f27;
}
.insight-item.lv-danger {
  border-left-color: #e24b4a;
}
.ins-ic {
  font-size: 16px;
  line-height: 1.4;
  flex: none;
}
.ins-main {
  min-width: 0;
}
.ins-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
}
.ins-detail {
  font-size: 11px;
  color: var(--text-body);
  line-height: 1.5;
  margin-top: 2px;
}
.ins-sug {
  font-size: 11px;
  color: var(--primary);
  line-height: 1.5;
  margin-top: 3px;
}

.sec-title {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 12px;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.unit {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
}

/* 分类 / 成员 通用行 */
.cat-row,
.mem-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 0.5px solid var(--divider);
}
.cat-row:last-child,
.mem-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.cat-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  background: var(--divider);
  flex: none;
}
.cat-main,
.mem-main {
  flex: 1;
  min-width: 0;
}
.cat-line,
.mem-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.cat-name {
  font-size: var(--font-md);
  font-weight: 500;
  color: var(--text-body);
}
.cat-amt,
.mem-amt {
  font-size: var(--font-md);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-main);
}
/* 金额 / 百分比分列对齐，避免挤成一团 */
.cat-right {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.cat-pct {
  font-size: var(--font-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  min-width: 46px;
  text-align: right;
}
.mem-name {
  font-weight: 500;
}
.mem-line em {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 4px;
}
.cat-count {
  font-size: 11px;
  color: var(--text-muted);
  flex: none;
}
.bar {
  height: 6px;
  background: var(--divider);
  border-radius: 3px;
  overflow: hidden;
}
.bar > span {
  display: block;
  height: 100%;
  border-radius: 3px;
}
.bar-fill.fill-expense {
  background: var(--expense);
}
.bar-fill.fill-income {
  background: var(--income);
}
.mem-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--primary-light);
  color: var(--primary-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  flex: none;
}

.acc-summary {
  display: flex;
}
.as-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}
.as-label {
  font-size: var(--font-xs);
  color: var(--text-sub);
}
.as-val {
  font-size: var(--font-md);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.trend {
  height: 200px;
}
.empty-sm {
  font-size: var(--font-sm);
  color: var(--text-muted);
  padding: 8px 0;
  text-align: center;
}
.loading-tip {
  text-align: center;
  font-size: var(--font-xs);
  color: var(--text-muted);
  padding: 8px 0;
}

/* ---------- 分类占比环形图 ---------- */
.pie-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 0.5px solid var(--divider);
}
.pie {
  width: 110px;
  height: 110px;
  flex: none;
}
.mini-legend {
  flex: 1;
  min-width: 0;
  max-height: 110px;
  overflow-y: auto;
}
.legend-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 0;
}
.legend-name {
  font-size: var(--font-sm);
  color: var(--text-sub);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.legend-pct {
  font-size: var(--font-sm);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  flex: none;
}
.cat-row {
  cursor: pointer;
}

/* ---------- 分类逐笔明细弹窗 ---------- */
.cat-mask {
  position: fixed;
  inset: 0;
  background: rgba(38, 33, 92, 0.45);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.cat-card {
  width: 100%;
  max-width: 420px;
  max-height: 86vh;
  background: #fff;
  border-radius: var(--radius-large);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--divider);
  flex: none;
}
.cat-head-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-main);
}
.cat-head-close {
  font-size: 22px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
}
.cat-body {
  padding: 12px 14px 16px;
  overflow-y: auto;
}
.cat-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: #faf9f5;
  border-radius: var(--radius-card);
}
.cat-summary-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex: none;
}
.cat-summary-name {
  font-size: var(--font-sm);
  color: var(--text-muted);
}
.cat-summary-amount {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}
.cat-filters {
  display: flex;
  gap: 8px;
  margin: 14px 0 6px;
}
.cat-filter {
  flex: 1;
  text-align: center;
  padding: 9px 0;
  border-radius: var(--radius-btn);
  font-size: var(--font-sm);
  background: var(--divider);
  color: var(--text-sub);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cat-filter.active {
  background: var(--primary-dark);
  color: #fff;
  font-weight: 500;
}
.cat-tx {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  border-bottom: 0.5px solid var(--divider);
}
.cat-tx:last-child {
  border-bottom: none;
}
.cat-tx-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #fdf6ec;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex: none;
}
.cat-tx-info {
  flex: 1;
  min-width: 0;
}
.cat-tx-title {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-body);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cat-tx-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cat-tx-amount {
  font-size: var(--font-sm);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  flex: none;
}
.cat-empty {
  padding: 32px 0;
  text-align: center;
  font-size: var(--font-sm);
  color: var(--text-muted);
}
</style>
