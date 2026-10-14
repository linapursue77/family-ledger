<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { accountApi } from '@/api'

const props = defineProps({ visible: { type: Boolean, default: false } })
const emit = defineEmits(['close'])

const router = useRouter()
const RECV_COLOR = '#1D9E75'

// 只用来兜底配色和图标；名称一律以服务器返回的为准（家庭可自定义账本名）
const BOOK_META = {
  husband: { label: '账本一', icon: '🧾', color: '#1D9E75' },
  wife: { label: '账本二', icon: '🧾', color: '#E24B4A' },
  shared: { label: '共同账户', icon: '👥', color: '#7F77DD' },
}

const data = ref(null)
const loading = ref(false)
const lineEl = ref(null)
const donutEl = ref(null)
let lineChart = null
let donutChart = null

const metaOf = (book) => BOOK_META[book] || { label: book, icon: '📁', color: '#888780' }
const colorOf = (book) => metaOf(book).color

/** 家庭自定义后的账本名：netvalue 接口每次都带最新的 book_labels */
const bookLabels = computed(() => data.value?.book_labels || {})

/**
 * 账本名称取值顺序：分组自带的 label → 顶层 book_labels → 内置默认名。
 * ★ 不能直接用 BOOK_META：那样家庭改了名，这里永远显示旧的「账本一 / 账本二」。
 */
function groupLabel(g) {
  return g?.label || bookLabels.value[g?.book_type] || metaOf(g?.book_type).label
}

/**
 * 只展示「有数据」的账本：合计为 0 的账本（没开户 / 余额已清零）整组隐藏，
 * 否则空账本会占掉一整块，把有内容的账本挤出可视区。
 * 注意用 !== 0 而不是 > 0：信用卡等负余额账本是有数据的，必须保留。
 */
const visibleGroups = computed(() =>
  (data.value?.groups || []).filter((g) => Number(g.total_cents) !== 0),
)
// 只有正数才能进构成环，负数段会让饼图变形
const donutGroups = computed(() => visibleGroups.value.filter((g) => Number(g.total_cents) > 0))

function money(cents) {
  const n = Number(cents || 0) / 100
  return '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}
function ymLabel(ym) {
  const [y, m] = String(ym || '').split('-')
  return `${y}年${Number(m)}月`
}
const accountCents = computed(() =>
  Number(data.value?.account_assets_cents ?? data.value?.total_assets_cents ?? 0),
)
const receivableCents = computed(() => Number(data.value?.receivable_cents || 0))
const payableCents = computed(() => Number(data.value?.payable_cents || 0))
// 资产构成基数 = 账户余额 + 借出未收：保证环形各段之和与圆心数字对得上
const assetBaseCents = computed(() => accountCents.value + receivableCents.value)
const netCents = computed(() => assetBaseCents.value - payableCents.value)
const loanSum = computed(() => data.value?.loans || null)

function pctOf(cents) {
  if (!assetBaseCents.value) return 0
  return Math.round((Number(cents) / assetBaseCents.value) * 100)
}

function goLoans() {
  emit('close')
  router.push('/loans')
}

// 账本分组的收益小计：只算纳入收益管理的账户
function groupProfit(g) {
  return (g.accounts || [])
    .filter((a) => a.is_invest)
    .reduce((sum, a) => sum + Number(a.profit_cents || 0), 0)
}

const validPoints = computed(() =>
  (data.value?.trend || []).filter((p) => p.assets_cents !== null && p.assets_cents !== undefined)
)
const hasTrend = computed(() => validPoints.value.length > 1)

async function load() {
  loading.value = true
  try {
    data.value = await accountApi.netvalue()
    await nextTick()
    renderLine()
    renderDonut()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function renderLine() {
  if (!lineEl.value || !data.value) return
  if (!lineChart) lineChart = echarts.init(lineEl.value)
  const points = validPoints.value
  const xs = points.map((p) => ymLabel(p.ym))
  const ys = points.map((p) => Number(p.assets_cents) / 100)

  lineChart.setOption(
    {
      grid: { left: 4, right: 18, top: 18, bottom: 2, containLabel: true },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => '¥' + Number(v).toLocaleString('zh-CN'),
      },
      xAxis: {
        type: 'category',
        data: xs,
        boundaryGap: false,
        axisLabel: { fontSize: 9, color: '#888780', rotate: 45, interval: 0 },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { fontSize: 10, color: '#888780', formatter: (v) => `${(v / 10000).toFixed(0)}万` },
        splitLine: { lineStyle: { color: '#f1efe8' } },
      },
      series: [
        {
          type: 'line',
          data: ys,
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2.5, color: '#4F7EF7' },
          itemStyle: { color: '#4F7EF7', borderColor: '#fff', borderWidth: 1 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(79,126,247,0.32)' },
              { offset: 1, color: 'rgba(79,126,247,0.02)' },
            ]),
          },
          markPoint: xs.length
            ? {
                symbol: 'circle',
                symbolSize: 11,
                label: { show: false },
                data: [{ coord: [xs[xs.length - 1], ys[ys.length - 1]], itemStyle: { color: '#F5A623' } }],
              }
            : undefined,
        },
      ],
    },
    true
  )
  lineChart.resize()
}

function renderDonut() {
  if (!donutEl.value || !data.value) return
  if (!donutChart) donutChart = echarts.init(donutEl.value)
  const items = donutGroups.value
    .map((g) => ({
      name: groupLabel(g),
      value: Number(g.total_cents) / 100,
      itemStyle: { color: colorOf(g.book_type) },
    }))
  // 借出未收是真金白银的应收资产，作为单独一段进入构成环
  if (receivableCents.value > 0) {
    items.push({
      name: '借出未收',
      value: receivableCents.value / 100,
      itemStyle: { color: RECV_COLOR },
    })
  }
  donutChart.setOption(
    {
      tooltip: { trigger: 'item', valueFormatter: (v) => '¥' + Number(v).toLocaleString('zh-CN') },
      series: [
        {
          type: 'pie',
          radius: ['64%', '92%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: false,
          label: { show: false },
          labelLine: { show: false },
          data: items,
        },
      ],
    },
    true
  )
  donutChart.resize()
}

watch(
  () => props.visible,
  (v) => {
    if (v) load()
  }
)

onBeforeUnmount(() => {
  if (lineChart) lineChart.dispose()
  if (donutChart) donutChart.dispose()
})
</script>

<template>
  <div v-if="visible" class="asset-mask" @click="emit('close')">
    <div class="asset-sheet" @click.stop>
      <div class="asset-head">
        <span class="asset-title">📊 家庭资产净值曲线</span>
        <span class="asset-close" @click="emit('close')">×</span>
      </div>

      <div v-if="data" class="asset-body">
        <!-- 净值曲线 -->
        <div class="net-card">
          <div ref="lineEl" class="net-chart"></div>
          <div v-if="!hasTrend" class="net-hint">
            历史快照不足，曲线将随每月快照积累逐步完善
          </div>
        </div>

        <!-- 资产构成 -->
        <div class="section-title">💰 资产构成</div>
        <div class="compose">
          <div class="donut-wrap">
            <div ref="donutEl" class="donut"></div>
            <div class="donut-center">
              <div class="donut-total">{{ money(assetBaseCents) }}</div>
              <div class="donut-label">总资产</div>
            </div>
          </div>
          <div class="compose-legend">
            <div v-for="g in visibleGroups" :key="g.book_type" class="compose-row">
              <span class="compose-dot" :style="{ background: colorOf(g.book_type) }"></span>
              <span class="compose-name">{{ metaOf(g.book_type).icon }} {{ groupLabel(g) }}</span>
              <span class="compose-amount">{{ money(g.total_cents) }}</span>
              <span
                class="compose-pct"
                :style="{ background: colorOf(g.book_type) + '22', color: colorOf(g.book_type) }"
              >{{ pctOf(g.total_cents) }}%</span>
            </div>
            <div v-if="receivableCents > 0" class="compose-row">
              <span class="compose-dot" :style="{ background: RECV_COLOR }"></span>
              <span class="compose-name">🤝 借出未收</span>
              <span class="compose-amount">{{ money(receivableCents) }}</span>
              <span
                class="compose-pct"
                :style="{ background: RECV_COLOR + '22', color: RECV_COLOR }"
              >{{ pctOf(receivableCents) }}%</span>
            </div>
            <div v-if="!visibleGroups.length && receivableCents <= 0" class="compose-empty">
              还没有有余额的账户
            </div>
          </div>
        </div>

        <!-- 净资产：总资产扣掉借入未还 -->
        <div v-if="payableCents > 0" class="net-line">
          <span class="nl-row">
            <i>🏦 账户资产</i><b>{{ money(accountCents) }}</b>
          </span>
          <span v-if="receivableCents > 0" class="nl-row">
            <i>🤝 借出未收（应收）</i><b class="plus">{{ money(receivableCents) }}</b>
          </span>
          <span class="nl-row">
            <i>📥 借入未还（负债）</i><b class="minus">{{ money(-payableCents) }}</b>
          </span>
          <span class="nl-row total">
            <i>家庭净资产</i><b>{{ money(netCents) }}</b>
          </span>
        </div>

        <!-- 各账户详情：只列有数据的账本，合计为 0 的账本不占位置 -->
        <template v-if="visibleGroups.length">
          <div class="section-title">📒 各账户详情</div>
          <div v-for="g in visibleGroups" :key="g.book_type" class="group-card">
            <div class="group-head">
              <span>{{ metaOf(g.book_type).icon }} {{ groupLabel(g) }}</span>
              <span class="group-total">
                {{ money(g.total_cents) }}
                <em
                  v-if="groupProfit(g)"
                  class="g-profit"
                  :class="groupProfit(g) > 0 ? 'p-up' : 'p-down'"
                >{{ groupProfit(g) > 0 ? '+' : '-' }}¥{{ money(Math.abs(groupProfit(g)) / 100) }}</em>
              </span>
            </div>
            <template v-for="a in g.accounts" :key="a.id">
              <div class="acc-row">
                <span class="acc-icon">{{ a.icon }}</span>
                <span class="acc-name">
                  {{ a.name }}
                  <i v-if="a.is_invest" class="acc-tag">收</i>
                </span>
                <span class="acc-balance">{{ money(a.balance_cents) }}</span>
              </div>
              <!-- 纳入收益管理的账户：余额下面直接标出「其中收益」占多少 -->
              <div v-if="a.is_invest && Number(a.profit_cents)" class="acc-profit-line">
                其中收益
                <em :class="a.profit_cents > 0 ? 'p-up' : 'p-down'">
                  {{ a.profit_cents > 0 ? '+' : '-' }}¥{{ money(Math.abs(a.profit_cents) / 100) }}
                </em>
                <template v-if="Number(a.balance_cents)">
                  ，占该账户 {{ ((a.profit_cents / a.balance_cents) * 100).toFixed(1) }}%
                </template>
              </div>
            </template>
          </div>
        </template>

        <!-- 借出未收属于应收资产，单独列一笔，避免只藏在环里看不出是谁欠的 -->
        <div v-if="loanSum && (loanSum.lend_cents || loanSum.borrow_cents)" class="group-card">
          <div class="group-head" @click="goLoans" style="cursor: pointer">
            <span>🤝 借钱来往</span>
            <span class="group-total">查看台账 ›</span>
          </div>
          <div v-if="loanSum.lend_cents" class="acc-row">
            <span class="acc-icon">📤</span>
            <span class="acc-name">借出未收（{{ loanSum.lend_count }} 笔）</span>
            <span class="acc-balance">{{ money(loanSum.lend_cents) }}</span>
          </div>
          <div v-if="loanSum.borrow_cents" class="acc-row">
            <span class="acc-icon">📥</span>
            <span class="acc-name">借入未还（{{ loanSum.borrow_count }} 笔）</span>
            <span class="acc-balance" style="color: #ba7517">{{ money(loanSum.borrow_cents) }}</span>
          </div>
          <div v-if="loanSum.overdue_count" class="acc-empty" style="color: #d03b3b">
            ⚠️ 其中 {{ loanSum.overdue_count }} 笔已过约定还款日
          </div>
        </div>

        <div v-if="data.excluded_accounts.length" class="group-card">
          <div class="group-head">
            <span>🚫 不计入总资产</span>
            <span class="group-total">{{ data.excluded_accounts.length }} 个</span>
          </div>
          <div v-for="a in data.excluded_accounts" :key="a.id" class="acc-row">
            <span class="acc-icon">{{ a.icon }}</span>
            <span class="acc-name">{{ a.name }}</span>
            <span class="acc-balance text-muted">{{ money(a.balance_cents) }}</span>
          </div>
        </div>

        <div class="asset-tip">💡 每月更新一次，记录家庭财富增长轨迹</div>
      </div>

      <div v-else class="asset-loading">{{ loading ? '加载中…' : '暂无数据' }}</div>
    </div>
  </div>
</template>

<style scoped>
.asset-mask {
  position: fixed;
  inset: 0;
  background: rgba(38, 33, 92, 0.45);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.asset-sheet {
  width: 100%;
  max-width: 420px;
  max-height: 88vh;
  background: #fff;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: popIn 0.22s ease;
}
@keyframes popIn {
  from {
    transform: scale(0.96);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
.asset-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 0.5px solid #f1efe8;
  flex-shrink: 0;
}
.asset-title {
  font-size: 15px;
  font-weight: 700;
  color: #26215c;
}
.asset-close {
  font-size: 22px;
  color: #888780;
  cursor: pointer;
  line-height: 1;
}
.asset-body {
  padding: 12px 14px 20px;
  overflow-y: auto;
}
.net-card {
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  padding: 10px 6px 4px;
  background: #fff;
}
.net-chart {
  width: 100%;
  height: 210px;
}
.net-hint {
  font-size: 11px;
  color: #b0aeaa;
  text-align: center;
  padding: 4px 0 8px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
  margin: 18px 0 10px;
}
.compose {
  display: flex;
  align-items: center;
  gap: 10px;
}
.donut-wrap {
  position: relative;
  width: 148px;
  height: 148px;
  flex-shrink: 0;
}
.donut {
  width: 100%;
  height: 100%;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.donut-total {
  font-size: 17px;
  font-weight: 700;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
.donut-label {
  font-size: 11px;
  color: #888780;
  margin-top: 2px;
}
.net-line {
  margin-top: 12px;
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  padding: 4px 14px;
  background: #fffdf7;
}
.nl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 0.5px solid #f5f3ec;
  font-size: 12px;
  color: #5f5e5a;
}
.nl-row:last-child {
  border-bottom: none;
}
.nl-row i {
  font-style: normal;
}
.nl-row b {
  font-variant-numeric: tabular-nums;
  color: #26215c;
}
.nl-row b.plus {
  color: #1d9e75;
}
.nl-row b.minus {
  color: #ba7517;
}
.nl-row.total {
  font-weight: 700;
  color: #26215c;
  padding-top: 10px;
}
.compose-legend {
  flex: 1;
  min-width: 0;
}
.compose-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
}
.compose-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.compose-name {
  font-size: 12px;
  color: #5f5e5a;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.compose-amount {
  font-size: 12px;
  font-weight: 600;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
.compose-pct {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.compose-empty {
  font-size: 12px;
  color: #b0aeaa;
  padding: 6px 0;
}
.group-card {
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 12px;
}
.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: #faf9f5;
  font-size: 13px;
  font-weight: 600;
  color: #26215c;
}
.group-total {
  font-variant-numeric: tabular-nums;
}
/* 账本收益小计 & 账户收益明细 */
.g-profit,
.p-up,
.p-down {
  font-style: normal;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.g-profit {
  font-size: 11px;
  margin-left: 6px;
}
.p-up {
  color: #1d9e75;
}
.p-down {
  color: #d03b3b;
}
.acc-tag {
  font-style: normal;
  font-size: 9px;
  color: #534ab7;
  background: #eeedfe;
  border-radius: 4px;
  padding: 1px 4px;
  margin-left: 4px;
  vertical-align: 1px;
}
.acc-profit-line {
  padding: 0 14px 10px 46px;
  margin-top: -4px;
  font-size: 11px;
  color: #888780;
}
.acc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-top: 0.5px solid #f1efe8;
}
.acc-row:first-of-type {
  border-top: none;
}
.acc-icon {
  font-size: 16px;
}
.acc-name {
  flex: 1;
  font-size: 13px;
  color: #2c2c2a;
}
.acc-balance {
  font-size: 13px;
  font-weight: 600;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
.asset-loading {
  padding: 40px 0;
  text-align: center;
  color: #888780;
  font-size: 13px;
}
.acc-empty {
  padding: 14px;
  font-size: 12px;
  color: #b0aeaa;
}
.asset-tip {
  text-align: center;
  font-size: 12px;
  color: #b0aeaa;
  padding: 6px 0 2px;
}
</style>
