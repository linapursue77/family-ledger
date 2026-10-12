<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { accountApi } from '@/api'
import { toast } from '@/utils/toast'

const router = useRouter()
const data = ref(null)
const loading = ref(true)
const chartEl = ref(null)
let chart = null

const UP = '#1D9E75'
const DOWN = '#E24B4A'

// 本金录入
const showSheet = ref(false)
const target = ref(null)
const pValue = ref('')
const pMode = ref('set')
const pAmount = ref('')
const pReason = ref('')
const saving = ref(false)

function money(v) {
  const n = Number(v || 0)
  const s = n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return s.endsWith('.00') ? s.slice(0, -3) : s
}
function moneyOf(cents) {
  return money(Number(cents || 0) / 100)
}
function signed(cents) {
  const c = Number(cents || 0)
  const sign = c > 0 ? '+' : c < 0 ? '-' : ''
  return `${sign}¥${moneyOf(Math.abs(c))}`
}
function cls(cents) {
  const c = Number(cents || 0)
  return c > 0 ? 'up' : c < 0 ? 'down' : 'flat'
}
function rateText(rate) {
  return rate === null || rate === undefined ? '—' : `${Number(rate) > 0 ? '+' : ''}${rate}%`
}
function monthLabel(ym) {
  const [y, m] = String(ym || '').split('-')
  if (!m) return ym || ''
  const curY = String(new Date().getFullYear())
  return y === curY ? `${Number(m)}月` : `${y.slice(2)}/${Number(m)}月`
}

const accounts = computed(() => data.value?.accounts || [])
const hasInvest = computed(() => !!data.value?.has_invest)
const points = computed(() =>
  (data.value?.trend || []).filter((p) => p.profit_cents !== null && p.profit_cents !== undefined),
)
// 只有 1 个点时画不出「变化」，仍展示柱状但tooltip可用
const hasTrend = computed(() => points.value.length > 0)

const beginLabel = computed(() => {
  const ym = data.value?.begin_ym
  return ym ? `${monthLabel(ym)}起` : '今年启用收益管理'
})

// 总金额里「本金 / 收益」各占多少：直观看到 200 万里有 10 万是赚的
const splitPct = computed(() => {
  const value = Number(data.value?.value_cents || 0)
  const profit = Number(data.value?.profit_cents || 0)
  if (value <= 0 || profit < 0) return null
  const p = (profit / value) * 100
  return { profit: Math.min(p, 100), principal: Math.max(100 - p, 0), profitText: p.toFixed(2) }
})

// 今年收益明细：按账户（谁在赚钱）+ 按月（什么时候赚的）
const curYear = String(new Date().getFullYear())
const yearAccounts = computed(() =>
  (data.value?.accounts || [])
    .filter((a) => Number(a.year_profit_cents) !== 0)
    .sort((a, b) => Math.abs(b.year_profit_cents) - Math.abs(a.year_profit_cents)),
)
const yearAbsMax = computed(() =>
  Math.max(1, ...yearAccounts.value.map((a) => Math.abs(Number(a.year_profit_cents || 0)))),
)
const yearMonths = computed(() =>
  (data.value?.trend || []).filter(
    (p) => String(p.ym).startsWith(curYear) && p.profit_cents !== null,
  ),
)

// 按账本切换：'' = 全部账本
const activeBook = ref('')
const books = computed(() => data.value?.books || [])

async function load() {
  loading.value = true
  try {
    data.value = await accountApi.returns({ book: activeBook.value || undefined })
    await nextTick()
    renderChart()
  } catch (e) {
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function switchBook(bookType) {
  if (bookType === activeBook.value) return
  activeBook.value = bookType
  load()
}

const currentBookLabel = computed(() => {
  if (!activeBook.value) return '全部账本'
  return books.value.find((b) => b.book_type === activeBook.value)?.label || '全部账本'
})

function renderChart() {
  if (!chartEl.value || !hasTrend.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const pts = points.value
  const xs = pts.map((p) => monthLabel(p.ym))
  const total = pts.map((p) => Number(p.profit) || 0)
  const monthly = pts.map((p) => (p.month_profit === null ? null : Number(p.month_profit) || 0))

  chart.setOption(
    {
      grid: { left: 4, right: 6, top: 26, bottom: 2, containLabel: true },
      legend: {
        data: ['累计收益', '当月新增'],
        top: 0,
        right: 0,
        itemWidth: 10,
        itemHeight: 6,
        textStyle: { fontSize: 10, color: '#888780' },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const p = pts[params[0].dataIndex]
          if (!p) return ''
          const lines = [
            `<b>${p.ym}</b>`,
            `现值 ¥${moneyOf(p.value_cents)}`,
            `本金 ¥${moneyOf(p.principal_cents)}`,
            `累计收益 <b>${signed(p.profit_cents)}</b>`,
          ]
          if (p.month_profit_cents !== null) {
            lines.push(`当月新增 ${signed(p.month_profit_cents)}`)
          }
          return lines.join('<br/>')
        },
      },
      xAxis: {
        type: 'category',
        data: xs,
        axisLabel: { fontSize: 9, color: '#888780', interval: 0, rotate: 45 },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: 'value',
          scale: true,
          axisLabel: {
            fontSize: 9,
            color: '#888780',
            formatter: (v) => (Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(1)}万` : `${v}`),
          },
          splitLine: { lineStyle: { color: '#f1efe8' } },
        },
        {
          type: 'value',
          scale: true,
          show: false,
        },
      ],
      series: [
        {
          name: '累计收益',
          type: 'bar',
          data: total,
          barMaxWidth: 16,
          itemStyle: {
            borderRadius: [3, 3, 0, 0],
            color: (p) => (Number(p.value) >= 0 ? UP : DOWN),
          },
        },
        {
          name: '当月新增',
          type: 'line',
          yAxisIndex: 1,
          data: monthly,
          smooth: true,
          symbol: 'circle',
          symbolSize: 4,
          connectNulls: false,
          lineStyle: { width: 2, color: '#F5A623' },
          itemStyle: { color: '#F5A623' },
        },
      ],
    },
    true
  )
  chart.resize()
}

function onResize() {
  if (chart) chart.resize()
}

// 盘点：股票/基金每月涨跌先把「现值」改了，再看要不要动本金
function openPrincipal(a) {
  target.value = a
  pValue.value = String((Number(a.value_cents) || 0) / 100)
  pMode.value = 'set'
  pAmount.value = String((Number(a.principal_cents) || 0) / 100)
  pReason.value = ''
  showSheet.value = true
}

async function savePrincipal() {
  const id = target.value.id
  const value = Number(pValue.value || 0)
  const amount = Number(pAmount.value || 0)
  if (!Number.isFinite(value) || value < 0) return toast('请输入正确的现值')
  if (!Number.isFinite(amount) || amount < 0) return toast('请输入正确的本金金额')
  if (pMode.value === 'set' && amount === 0) return toast('本金不能为 0')

  const curValue = (Number(target.value.value_cents) || 0) / 100
  const curPrincipal = (Number(target.value.principal_cents) || 0) / 100
  const reason = pReason.value.trim()

  saving.value = true
  try {
    // 现值变了走余额调整（会留审计日志），本金变了走本金调整，两者互不干扰
    if (Math.abs(value - curValue) > 0.001) {
      await accountApi.adjust(id, {
        balance: value.toFixed(2),
        reason: reason || '资产盘点更新现值',
      })
    }
    const changed = pMode.value === 'add' ? amount !== 0 : Math.abs(amount - curPrincipal) > 0.001
    if (changed) {
      await accountApi.setPrincipal(id, {
        principal: amount.toFixed(2),
        mode: pMode.value,
        reason,
      })
    }
    if (Math.abs(value - curValue) <= 0.001 && !changed) {
      showSheet.value = false
      saving.value = false
      return
    }
    showSheet.value = false
    toast(pMode.value === 'add' && changed ? '已加仓并更新' : '盘点已保存')
    await load()
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) chart.dispose()
})
</script>

<template>
  <div class="ret-page">
    <div class="top-bar">
      <span class="top-title">📈 收益管理</span>
      <span class="top-close" @click="router.push('/accounts')">×</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <template v-else-if="hasInvest">
      <!-- 账本切换 -->
      <div v-if="books.length" class="book-tabs">
        <span
          class="book-tab"
          :class="{ on: !activeBook }"
          @click="switchBook('')"
        >全部</span>
        <span
          v-for="b in books"
          :key="b.book_type"
          class="book-tab"
          :class="{ on: activeBook === b.book_type }"
          @click="switchBook(b.book_type)"
        >{{ b.label }}<em :class="cls(b.profit_cents)">{{ signed(b.profit_cents) }}</em></span>
      </div>

      <template v-if="accounts.length">
      <!-- 总金额（含收益）：把「市值」放主位，收益是其中一段 -->
      <div class="card hero">
        <div class="hero-label">
          投资总金额（含收益）<span class="hero-book">{{ currentBookLabel }}</span>
        </div>
        <div class="hero-value">¥{{ moneyOf(data.value_cents) }}</div>
        <div class="hero-sub">
          其中收益
          <em :class="cls(data.profit_cents)">{{ signed(data.profit_cents) }}</em>
          <template v-if="splitPct">，占 {{ splitPct.profitText }}%</template>
          · 收益率 {{ rateText(data.profit_rate) }}
        </div>
        <template v-if="splitPct">
          <div class="split-bar">
            <i class="sb-principal" :style="{ width: splitPct.principal + '%' }"></i>
            <i class="sb-profit" :style="{ width: splitPct.profit + '%' }"></i>
          </div>
          <div class="split-legend">
            <span><i class="dot principal"></i>本金 ¥{{ moneyOf(data.principal_cents) }}</span>
            <span><i class="dot profit"></i>收益 ¥{{ moneyOf(data.profit_cents) }}</span>
          </div>
        </template>
        <div class="hero-note">总金额 = 本金 + 收益；加仓只增加本金、不影响收益</div>
      </div>

      <!-- 今年收益分析 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">今年收益分析</span>
          <span class="card-tag">{{ beginLabel }}</span>
        </div>
        <div class="year-row">
          <span class="yr-value" :class="cls(data.year_profit_cents)">{{
            signed(data.year_profit_cents)
          }}</span>
          <span class="yr-rate">今年收益率 {{ rateText(data.year_profit_rate) }}</span>
        </div>
        <div class="impact">
          <div class="im-line">
            <span>对家庭净资产的影响</span>
            <span class="im-val" :class="cls(data.year_profit_cents)">
              {{ data.year_profit_of_assets_pct === null ? '—' : data.year_profit_of_assets_pct + '%' }}
            </span>
          </div>
          <div class="im-bar">
            <i
              class="im-fill"
              :class="cls(data.year_profit_cents)"
              :style="{
                width: Math.min(Math.abs(data.year_profit_of_assets_pct || 0), 100) + '%',
              }"
            ></i>
          </div>
          <div class="im-note">
            今年收益占家庭净资产 ¥{{ moneyOf(data.net_assets_cents) }} 的比例
          </div>
        </div>
        <div class="kv-row">
          <div class="kv">
            <span class="kv-k">累计收益占比</span>
            <span class="kv-v" :class="cls(data.profit_cents)">
              {{ data.profit_of_assets_pct === null ? '—' : data.profit_of_assets_pct + '%' }}
            </span>
          </div>
          <div class="kv">
            <span class="kv-k">剔除收益后净资产</span>
            <span class="kv-v">¥{{ moneyOf(data.assets_ex_profit_cents) }}</span>
          </div>
        </div>
      </div>

      <!-- 今年收益明细：按账户 + 按月，看清钱是哪赚的、什么时候赚的 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">今年收益明细</span>
          <span class="card-tag">{{ beginLabel }}</span>
        </div>

        <div v-if="yearAccounts.length" class="det-block">
          <div class="det-title">按账户</div>
          <div v-for="a in yearAccounts" :key="a.id" class="det-row">
            <span class="det-ic">{{ a.icon || '📈' }}</span>
            <div class="det-main">
              <div class="det-name">{{ a.name }}</div>
              <div class="det-bar">
                <i
                  class="det-fill"
                  :class="cls(a.year_profit_cents)"
                  :style="{ width: (Math.abs(a.year_profit_cents) / yearAbsMax) * 100 + '%' }"
                ></i>
              </div>
            </div>
            <span class="det-val" :class="cls(a.year_profit_cents)">{{
              signed(a.year_profit_cents)
            }}</span>
          </div>
        </div>

        <div v-if="yearMonths.length" class="det-block">
          <div class="det-title">按月</div>
          <div class="m-head">
            <span>月份</span>
            <span>当月</span>
            <span>月末累计</span>
          </div>
          <div v-for="m in yearMonths" :key="m.ym" class="m-row">
            <span class="m-ym">{{ monthLabel(m.ym) }}</span>
            <span class="m-month" :class="cls(m.month_profit_cents)">{{
              m.month_profit_cents === null ? '—' : signed(m.month_profit_cents)
            }}</span>
            <span class="m-total" :class="cls(m.profit_cents)">{{ signed(m.profit_cents) }}</span>
          </div>
        </div>

        <div v-if="!yearAccounts.length && !yearMonths.length" class="empty sm">
          今年还没有收益变化记录，盘点一次（改现值或本金）后就会按月留下明细
        </div>
      </div>

      <!-- 一年收益变化 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">一年收益变化</span>
          <span class="card-tag">柱=累计收益 · 线=当月新增</span>
        </div>
        <div v-if="hasTrend" ref="chartEl" class="chart"></div>
        <div v-else class="empty sm">
          还没有收益记录，更新一次账户余额或本金后会按月留存快照
        </div>
      </div>

      <!-- 投资账户明细 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">收益账户（{{ data.account_count }}）</span>
          <span class="card-link" @click="router.push('/accounts')">去管理 ›</span>
        </div>
        <div v-for="a in accounts" :key="a.id" class="acc-card" @click="openPrincipal(a)">
          <span class="acc-ic">{{ a.icon || '📈' }}</span>
          <div class="acc-main">
            <div class="acc-name">
              {{ a.name }}
              <em class="acc-rate" :class="cls(a.profit_cents)">{{ rateText(a.profit_rate) }}</em>
            </div>
            <div class="acc-sub">
              现值 ¥{{ moneyOf(a.value_cents) }} · 本金 ¥{{ moneyOf(a.principal_cents) }}
            </div>
            <div class="acc-sub">
              今年 {{ signed(a.year_profit_cents) }}
              <template v-if="a.book_label"> · {{ a.book_label }}</template>
            </div>
          </div>
          <div class="acc-right">
            <div class="acc-value">¥{{ moneyOf(a.value_cents) }}</div>
            <div class="acc-tip" :class="cls(a.profit_cents)">
              含收益 {{ signed(a.profit_cents) }}
            </div>
          </div>
        </div>
        <div class="tip-line">点击账户可盘点：更新现值 / 调整本金（加仓用「追加」）</div>
        </div>
      </template>

      <!-- 选中的账本下没有投资账户 -->
      <div v-else class="card">
        <div class="empty sm">
          「{{ currentBookLabel }}」下还没有纳入收益管理的账户，切回「全部」或去账户管理添加
        </div>
      </div>
    </template>

    <!-- 未开启收益管理 -->
    <div v-else class="card empty-card">
      <div class="ec-ic">📈</div>
      <div class="ec-title">还没有纳入收益管理的账户</div>
      <div class="ec-sub">
        在账户管理里把股票、基金、支付宝理财这类账户勾选「纳入收益管理」并填写投入本金，
        就能看到一年内的收益变化和今年收益对家庭总资产的影响
      </div>
      <button class="btn btn-primary" @click="router.push('/accounts')">去账户管理</button>
    </div>

    <!-- 本金录入 -->
    <div v-if="showSheet" class="sheet-mask" @click="showSheet = false">
      <div class="sheet" @click.stop>
        <div class="sh-head">
          <span class="sh-title">资产盘点 · {{ target?.name }}</span>
          <span class="sh-close" @click="showSheet = false">×</span>
        </div>

        <div class="sh-cur">
          现值 ¥{{ moneyOf(target?.value_cents) }} · 当前本金 ¥{{ moneyOf(target?.principal_cents) }}
          <em :class="cls(target?.profit_cents)">收益 {{ signed(target?.profit_cents) }}</em>
        </div>

        <label class="sh-label">当前现值（股票 / 基金的最新市值）</label>
        <div class="money-input">
          <span class="money-sign">¥</span>
          <input v-model="pValue" type="number" inputmode="decimal" placeholder="0.00" />
        </div>

        <label class="sh-label">本金调整方式</label>
        <div class="mode-row">
          <div class="mode" :class="{ on: pMode === 'set' }" @click="pMode = 'set'">
            盘点：设为该值
          </div>
          <div class="mode" :class="{ on: pMode === 'add' }" @click="pMode = 'add'">
            加仓：追加金额
          </div>
        </div>

        <label class="sh-label">{{ pMode === 'add' ? '追加本金' : '投入本金' }}</label>
        <div class="money-input">
          <span class="money-sign">¥</span>
          <input
            v-model="pAmount"
            type="number"
            inputmode="decimal"
            :placeholder="pMode === 'add' ? '本次加仓金额' : '累计投入本金'"
          />
        </div>

        <label class="sh-label">说明（可选）</label>
        <input v-model="pReason" class="sh-input" maxlength="60" placeholder="如：12 月定投加仓" />

        <button class="btn btn-primary" :disabled="saving" @click="savePrincipal">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ret-page {
  padding-bottom: calc(var(--nav-h, 60px) + env(safe-area-inset-bottom) + 16px);
  min-height: 100vh;
  background: #faf9f6;
}
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px 12px;
}
.top-title {
  font-size: 18px;
  font-weight: 700;
  color: #26215c;
}
.top-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f1efe8;
  color: #888780;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
.card {
  margin: 0 16px 16px;
  padding: 16px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 14px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
}
.card-tag {
  font-size: 11px;
  color: #b8b6ae;
}
.card-link {
  font-size: 11px;
  color: #534ab7;
  cursor: pointer;
}
/* 累计收益 */
.hero-label {
  font-size: 13px;
  color: #5f5e5a;
}
.hero-value {
  font-size: 30px;
  font-weight: 700;
  margin: 6px 0 4px;
  font-variant-numeric: tabular-nums;
}
.hero-sub {
  font-size: 12px;
  color: #888780;
  line-height: 1.6;
}
.hero-note {
  margin-top: 8px;
  font-size: 11px;
  color: #b8b6ae;
}
.up {
  color: #1d9e75;
}
.down {
  color: #d03b3b;
}
.flat {
  color: #888780;
}
/* 今年收益 */
.year-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.yr-value {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.yr-rate {
  font-size: 11px;
  color: #888780;
}
.impact {
  margin-top: 14px;
}
.im-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #5f5e5a;
}
.im-val {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.im-bar {
  margin: 6px 0 4px;
  height: 6px;
  border-radius: 999px;
  background: #f1efe8;
  overflow: hidden;
}
.im-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #1d9e75;
}
.im-fill.down {
  background: #d03b3b;
}
.im-note {
  font-size: 11px;
  color: #b8b6ae;
}
.kv-row {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}
.kv {
  flex: 1;
  background: #faf9f6;
  border-radius: 10px;
  padding: 10px 12px;
}
.kv-k {
  display: block;
  font-size: 11px;
  color: #888780;
}
.kv-v {
  display: block;
  margin-top: 3px;
  font-size: 14px;
  font-weight: 700;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
/* 账本切换 */
.book-tabs {
  display: flex;
  gap: 8px;
  margin: 0 16px 14px;
  overflow-x: auto;
  padding-bottom: 2px;
}
.book-tab {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 999px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  font-size: 12px;
  color: #5f5e5a;
  white-space: nowrap;
  cursor: pointer;
}
.book-tab em {
  font-style: normal;
  font-weight: 700;
  font-size: 11px;
}
.book-tab.on {
  background: #26215c;
  border-color: #26215c;
  color: #fff;
}
.hero-book {
  margin-left: 6px;
  font-size: 11px;
  color: #888780;
}
/* 本金 / 收益构成条 */
.split-bar {
  display: flex;
  margin-top: 12px;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #f1efe8;
}
.sb-principal {
  background: #c9c7bd;
}
.sb-profit {
  background: #1d9e75;
}
.split-legend {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 11px;
  color: #888780;
}
.split-legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.dot.principal {
  background: #c9c7bd;
}
.dot.profit {
  background: #1d9e75;
}
/* 今年收益明细 */
.det-block {
  margin-bottom: 16px;
}
.det-block:last-child {
  margin-bottom: 0;
}
.det-title {
  font-size: 12px;
  color: #888780;
  margin-bottom: 8px;
}
.det-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.det-ic {
  flex: none;
  font-size: 15px;
}
.det-main {
  flex: 1;
  min-width: 0;
}
.det-name {
  font-size: 12px;
  color: #26215c;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.det-bar {
  height: 5px;
  border-radius: 999px;
  background: #f1efe8;
  overflow: hidden;
}
.det-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #1d9e75;
}
.det-fill.down {
  background: #d03b3b;
}
.det-val {
  flex: none;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
/* 月度明细 */
.m-head,
.m-row {
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr;
  align-items: center;
  font-size: 12px;
  padding: 6px 0;
}
.m-head {
  color: #b8b6ae;
  font-size: 11px;
  border-bottom: 0.5px solid #f1efe8;
}
.m-head span:not(:first-child),
.m-row span:not(:first-child) {
  text-align: right;
}
.m-row {
  border-bottom: 0.5px solid #faf9f6;
  font-variant-numeric: tabular-nums;
}
.m-ym {
  color: #5f5e5a;
}
.m-total {
  color: #26215c;
  font-weight: 600;
}
/* 图表 */
.chart {
  width: 100%;
  height: 200px;
}
/* 账户明细 */
.acc-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  border-top: 0.5px solid #f1efe8;
  cursor: pointer;
}
.acc-card:active {
  background: #faf9f6;
}
.acc-ic {
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 10px;
  background: #f4f3fb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.acc-main {
  flex: 1;
  min-width: 0;
}
.acc-name {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acc-rate {
  font-style: normal;
  font-size: 11px;
  font-weight: 600;
  margin-left: 5px;
}
.acc-sub {
  font-size: 11px;
  color: #b8b6ae;
  margin-top: 2px;
}
.acc-right {
  flex: none;
  text-align: right;
}
.acc-value {
  font-size: 15px;
  font-weight: 700;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
.acc-tip {
  font-size: 10px;
  color: #b8b6ae;
  margin-top: 2px;
}
.tip-line {
  margin-top: 8px;
  font-size: 11px;
  color: #b8b6ae;
}
/* 空态 */
.empty-card {
  text-align: center;
  padding: 32px 20px;
}
.ec-ic {
  font-size: 34px;
}
.ec-title {
  margin-top: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #26215c;
}
.ec-sub {
  margin: 8px 0 16px;
  font-size: 12px;
  color: #888780;
  line-height: 1.7;
}
.empty {
  text-align: center;
  color: #b8b6ae;
  font-size: 13px;
  padding: 40px 0;
}
.empty.sm {
  padding: 20px 0;
  font-size: 12px;
}
/* 本金录入弹层 */
.sh-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sh-title {
  font-size: 16px;
  font-weight: 600;
  color: #26215c;
}
.sh-close {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #f1efe8;
  color: #888780;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.sh-cur {
  font-size: 12px;
  color: #888780;
  margin-bottom: 14px;
}
.sh-cur em {
  font-style: normal;
  font-weight: 600;
  margin-left: 6px;
}
.sh-label {
  display: block;
  font-size: 12px;
  color: #888780;
  margin-bottom: 8px;
}
.mode-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.mode {
  flex: 1;
  text-align: center;
  padding: 10px 0;
  font-size: 12px;
  border-radius: 8px;
  border: 0.5px solid #e8e8e8;
  background: #fff;
  color: #5f5e5a;
  cursor: pointer;
}
.mode.on {
  border-color: #7f77dd;
  background: #eeedfe;
  color: #534ab7;
  font-weight: 600;
}
.money-input {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  padding: 12px;
  box-sizing: border-box;
  margin-bottom: 14px;
}
.money-input:focus-within {
  border-color: #ef9f27;
  box-shadow: 0 0 0 2px rgba(239, 159, 39, 0.15);
}
.money-sign {
  color: #888780;
  font-size: 14px;
}
.money-input input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  color: #26215c;
  min-width: 0;
}
.sh-input {
  width: 100%;
  box-sizing: border-box;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  color: #26215c;
  outline: none;
  margin-bottom: 16px;
}
.sh-input:focus {
  border-color: #ef9f27;
  box-shadow: 0 0 0 2px rgba(239, 159, 39, 0.15);
}
</style>
