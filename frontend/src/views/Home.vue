<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ledgerApi, accountApi } from '@/api'
import { yuan } from '@/utils/money'
import AssetDetailSheet from '@/components/AssetDetailSheet.vue'
import TxDetailSheet from '@/components/TxDetailSheet.vue'

const route = useRoute()
const router = useRouter()

const presets = [
  { key: 'last_week', label: '近1周' },
  { key: 'last_month', label: '近1月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
  { key: 'last_year', label: '近一年' },
]
const active = ref('last_week')
const activeLabel = ref('近1周')
const showOptions = ref(false)
const ov = ref(null)
const loading = ref(true)
const accounts = ref([])
const showAccounts = ref(false)
const showAssetDetail = ref(false)
// —— 近期账单（首页逐笔明细）——
const recentRange = ref('follow') // 'follow'=跟随顶部周期 | 3 | 7 天
const billSort = ref('time') // time=按时间(按天分组) | cat=按分类分组
const recentTxs = ref([])
const recentLoading = ref(false)
const categoryMap = ref({})
const accountMap = ref({})
let metaLoaded = false

async function load() {
  loading.value = true
  try {
    ov.value = await ledgerApi.overview({ preset: active.value })
    const label = presets.find((p) => p.key === active.value)?.label || ''
    activeLabel.value = label
    await ensureMeta()
    await loadRecent()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}
function onPreset(p) {
  active.value = p
  showOptions.value = false
  load()
}
function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
async function ensureMeta() {
  if (metaLoaded) return
  try {
    const [cats, accs] = await Promise.all([ledgerApi.categories(), accountApi.list()])
    const cmap = {}
    ;(cats?.items || cats || []).forEach((c) => (cmap[c.id] = c))
    categoryMap.value = cmap
    const amap = {}
    ;(accs?.items || accs || []).forEach((a) => (amap[a.id] = a))
    accountMap.value = amap
    metaLoaded = true
  } catch (e) {
    console.error(e)
  }
}
async function loadRecent() {
  recentLoading.value = true
  try {
    let from, to
    if (recentRange.value === 'follow' && ov.value?.range) {
      // ★ 与顶部时间控件同源：直接用 overview 返回的区间，账单与资产卡口径一致
      from = ov.value.range.start
      to = ov.value.range.end
    } else {
      const days = Number(recentRange.value) || 3
      to = ymd(new Date())
      const d = new Date()
      d.setDate(d.getDate() - (days - 1))
      from = ymd(d)
    }
    const res = await ledgerApi.transactions({
      date_from: from,
      date_to: to,
      page_size: 200,
    })
    const items = res?.items || res || []
    recentTxs.value = items.map((t) => decorateTx(t))
      .sort((x, y) => y.dateKey.localeCompare(x.dateKey))
  } catch (e) {
    console.error(e)
  } finally {
    recentLoading.value = false
  }
}
function setRecentRange(n) {
  if (recentRange.value === n) return
  recentRange.value = n
  loadRecent()
}
const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六']
function dayText(key) {
  const [, m, d] = (key || '').split('-')
  return m ? `${Number(m)}月${Number(d)}日` : key
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
function amt(cents) {
  return yuan(cents).toFixed(2)
}
const billGroups = computed(() => {
  const list = recentTxs.value
  const map = new Map()
  if (billSort.value === 'cat') {
    list.forEach((t) => {
      const k = t.catName || '未分类'
      if (!map.has(k)) map.set(k, { key: k, items: [], expense: 0, income: 0, icon: t.catIcon, color: t.catColor })
      const g = map.get(k)
      g.items.push(t)
      // 借贷只占一行明细，不混进「支/收」小结，避免与报表口径打架
      if (!t.isLoan) {
        if (t.isIn) g.income += t.amount_cents
        else g.expense += t.amount_cents
      }
    })
    return [...map.values()].sort((a, b) => b.expense + b.income - (a.expense + a.income))
  }
  list.forEach((t) => {
    if (!map.has(t.dateKey)) map.set(t.dateKey, { key: t.dateKey, items: [], expense: 0, income: 0 })
    const g = map.get(t.dateKey)
    g.items.push(t)
    if (t.type === 'income') g.income += t.amount_cents
    else g.expense += t.amount_cents
  })
  return [...map.values()].sort((a, b) => b.key.localeCompare(a.key))
})

const recentLabel = computed(() =>
  recentRange.value === 'follow' ? activeLabel.value : `近${recentRange.value}日`
)
const billSummary = computed(() => {
  let count = 0
  let expense = 0
  let income = 0
  recentTxs.value.forEach((t) => {
    count += 1
    if (t.isLoan) return
    if (t.isIn) income += t.amount_cents
    else expense += t.amount_cents
  })
  return { count, expense, income }
})
function money(v) {
  const n = Number(v)
  if (isNaN(n)) return String(v ?? '0')
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function assetChangeText() {
  const v = Number(ov.value?.asset_change || 0)
  const sign = v >= 0 ? '+' : ''
  return `比上月 ${sign}¥${yuan(Math.abs(v)).toFixed(2)}`
}
// —— 账单明细弹窗 ——
const showDetail = ref(false)
const detailTx = ref(null)
const pageNotice = ref('')
// 借贷流水与收支同列展示，但只做「资金进出」投影：收入侧 = income + loan_in
function decorateTx(t) {
  const c = categoryMap.value[t.category_id] || {}
  const a = accountMap.value[t.account_id] || {}
  const loan = t.type === 'loan_in' || t.type === 'loan_out'
  const income = t.type === 'income' || t.type === 'loan_in'
  return {
    ...t,
    isLoan: loan,
    isIn: income,
    dateKey: (t.transaction_date || '').slice(0, 10),
    catName: loan ? '借钱来往' : c.name || '未分类',
    catIcon: loan ? '🤝' : c.icon || '💸',
    catColor: loan ? '#888780' : c.color || '#888780',
    accountName: a.name || (t.account_id ? '' : '未指定账户'),
    merchant: t.merchant || c.name || (income ? '收入' : '支出'),
    amountText: (income ? '+' : '-') + yuan(t.amount_cents).toFixed(2),
    dateText: (t.transaction_date || '').replace('T', ' ').slice(0, 16),
  }
}
function openDetail(t) {
  if (!t) return
  detailTx.value = decorateTx(t)
  showDetail.value = true
}
// 记账后回首页：只显示一条轻提示，不自动弹窗
function consumeNotice() {
  const notice = route.query.notice
  if (!notice) return
  pageNotice.value = notice
  router.replace({ path: '/', query: {} })
  setTimeout(() => {
    pageNotice.value = ''
  }, 2600)
}
onMounted(async () => {
  await load()
  consumeNotice()
})
</script>

<template>
  <div class="page">
    <!-- 记账后回首页的轻提示：自动消失，不打断操作 -->
    <div v-if="pageNotice" class="page-notice">{{ pageNotice }}</div>

    <!-- 时间控件 -->
    <div class="time-picker-bar" @click="showOptions = !showOptions">
      <div class="time-picker-left">
        <span class="time-picker-icon">📅</span>
        <span class="time-picker-text">{{ activeLabel }}</span>
      </div>
      <span class="time-picker-arrow">›</span>
    </div>
    <div class="time-picker-options" :class="{ show: showOptions }">
      <span
        v-for="p in presets"
        :key="p.key"
        class="time-picker-option"
        :class="{ active: active === p.key }"
        @click="onPreset(p.key)"
      >{{ p.label }}</span>
      <span class="time-picker-option custom">📆 自定义</span>
    </div>
    <div v-if="ov" class="time-range-display">
      <span class="time-range-text">{{ ov.range.start }} ~ {{ ov.range.end }}</span>
    </div>

    <template v-if="ov">
      <!-- 资产卡 -->
      <div class="asset-card" @click="showAssetDetail = true">
        <div class="label">🏦 家庭净资产</div>
        <div class="amount">¥{{ ov.total_assets }}</div>
        <div class="change">{{ assetChangeText() }} › 点击查看净值曲线</div>
      </div>

      <!-- 本期收支：资产卡是「存量」，这里补上所选周期内的「流量」口径 -->
      <div class="flow-card">
        <div class="flow-row">
          <div class="flow-item">
            <div class="flow-label">收入</div>
            <div class="flow-value text-income">¥{{ money(ov.income) }}</div>
          </div>
          <div class="flow-item">
            <div class="flow-label">支出</div>
            <div class="flow-value text-expense">¥{{ money(ov.expense) }}</div>
          </div>
          <div class="flow-item">
            <div class="flow-label">结余</div>
            <div
              class="flow-value"
              :class="Number(ov.balance_cents) >= 0 ? 'text-income' : 'text-expense'"
            >¥{{ money(ov.balance) }}</div>
          </div>
        </div>
        <div class="flow-rate">
          <span class="rate-label">储蓄率</span>
          <div class="rate-bar">
            <span
              class="rate-fill"
              :style="{ width: Math.min(Math.max(Number(ov.saving_rate) || 0, 0), 100) + '%' }"
            ></span>
          </div>
          <span class="rate-value">{{ ov.saving_rate }}%</span>
        </div>
      </div>

      <!-- 近期账单：报告页已覆盖分析，这里展示逐笔流水明细 -->
      <div class="card bill-card">
        <div class="bill-head">
          <div class="bill-title">
            {{ recentLabel }}账单
            <div class="bill-sorts">
              <span :class="{ on: billSort === 'time' }" @click="billSort = 'time'">按时间</span>
              <span :class="{ on: billSort === 'cat' }" @click="billSort = 'cat'">按分类</span>
            </div>
          </div>
        </div>
        <div class="bill-range">
          <span :class="{ on: recentRange === 'follow' }" @click="setRecentRange('follow')">跟随周期</span>
          <span :class="{ on: recentRange === 3 }" @click="setRecentRange(3)">近3日</span>
          <span :class="{ on: recentRange === 7 }" @click="setRecentRange(7)">近1周</span>
        </div>
        <div v-if="!recentLoading && billGroups.length" class="bill-summary">
          共 {{ billSummary.count }} 笔 ·
          <b class="text-expense">支 ¥{{ amt(billSummary.expense) }}</b> ·
          <b class="text-income">收 ¥{{ amt(billSummary.income) }}</b>
        </div>

        <div v-if="recentLoading" class="bill-loading">加载中…</div>
        <div v-else-if="!billGroups.length" class="bill-empty">该区间暂无账单</div>

        <div v-else class="bill-groups">
          <div v-for="g in billGroups" :key="g.key" class="bill-group">
            <div class="bill-day">
              <span class="bill-day-name">
                <template v-if="billSort === 'time'">
                  {{ dayText(g.key) }} <em>{{ dayLabel(g.key) }}</em>
                </template>
                <template v-else>
                  <span class="bill-cat-ic" :style="{ background: g.color + '22' }">{{ g.icon }}</span>{{ g.key }}
                </template>
              </span>
              <span class="bill-day-sum">
                <b v-if="g.expense" class="text-expense">支:{{ amt(g.expense) }}</b>
                <b v-if="g.income" class="text-income">收:{{ amt(g.income) }}</b>
              </span>
            </div>
            <div v-for="t in g.items" :key="t.id" class="bill-item" @click="openDetail(t)">
              <span class="bill-ic" :style="{ background: t.catColor + '22', color: t.catColor }">{{ t.catIcon }}</span>
              <div class="bill-info">
                <div class="bill-merchant">{{ t.merchant }}</div>
                <div v-if="t.accountName" class="bill-account">{{ t.accountName }}</div>
              </div>
              <span
                :class="[
                  'bill-amount',
                  t.isLoan ? 'text-loan' : t.isIn ? 'text-income' : 'text-expense',
                ]"
                >{{ t.amountText }}</span
              >
            </div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="empty">{{ loading ? '加载中…' : '暂无数据' }}</div>

    <router-link to="/add" class="floating-btn">+</router-link>

    <!-- 账户弹窗 -->
    <div v-if="showAccounts" class="sheet-mask" @click="showAccounts = false">
      <div class="sheet" @click.stop>
        <div class="sheet-head">
          <span class="sheet-title">账户管理</span>
          <span class="sheet-close" @click="showAccounts = false">×</span>
        </div>
        <div v-for="a in accounts" :key="a.id" class="list-item">
          <span class="acc-icon">{{ a.icon }}</span>
          <div class="acc-info">
            <span class="acc-name">{{ a.name }}</span>
            <span class="acc-book text-muted">{{ a.book_type }}</span>
          </div>
          <span class="acc-balance">¥{{ yuan(a.balance_cents).toFixed(2) }}</span>
        </div>
      </div>
    </div>

    <!-- 家庭资产净值曲线 -->
    <AssetDetailSheet :visible="showAssetDetail" @close="showAssetDetail = false" />
    <!-- 账单明细（点击流水 / 记账后自动定位） -->
    <TxDetailSheet :visible="showDetail" :tx="detailTx" @close="showDetail = false" />
  </div>
</template>

<style scoped>
.page-notice {
  margin: 12px 16px 0;
  padding: 9px 12px;
  border-radius: 10px;
  background: #eeedfe;
  color: #534ab7;
  font-size: 12px;
}
.time-picker-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #f7f6f3;
  border-radius: 10px;
  margin: 12px 16px 4px;
  cursor: pointer;
}
.time-picker-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.time-picker-icon {
  font-size: 16px;
}
.time-picker-text {
  font-size: 14px;
  font-weight: 500;
  color: #26215c;
}
.time-picker-arrow {
  font-size: 18px;
  color: #c8c6c0;
}
.time-picker-options {
  display: none;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 16px;
  padding: 12px;
  background: #fff;
  border-radius: 10px;
  border: 0.5px solid #e8e8e8;
}
.time-picker-options.show {
  display: flex;
}
.time-picker-option {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  background: #f1efe8;
  color: #5f5e5a;
  cursor: pointer;
}
.time-picker-option.active {
  background: #eeedfe;
  color: #7f77dd;
  font-weight: 500;
}
.time-picker-option.custom {
  background: linear-gradient(135deg, #7f77dd 0%, #9b8fe8 100%);
  color: #fff;
  font-weight: 500;
}
.time-range-display {
  padding: 8px 12px;
  background: #f7f6f3;
  border-radius: 8px;
  margin: 8px 16px;
  text-align: center;
}
.time-range-text {
  font-size: 12px;
  color: #888780;
}
.asset-card {
  cursor: pointer;
  background: linear-gradient(135deg, #7f77dd, #534ab7);
  color: #fff;
  border-radius: 16px;
  padding: 20px;
  margin: 0 16px 16px;
}
.asset-card .label {
  font-size: 12px;
  opacity: 0.8;
}
.asset-card .amount {
  font-size: 28px;
  font-weight: 600;
  margin: 4px 0;
}
.asset-card .change {
  font-size: 12px;
  opacity: 0.9;
}
.card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin: 0 16px 12px;
  border: 0.5px solid #e8e8e8;
}
.floating-btn {
  position: fixed;
  bottom: 90px;
  right: max(16px, calc(50vw - 194px));
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #7f77dd;
  color: #fff;
  font-size: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.4);
  z-index: 40;
  text-decoration: none;
}
.acc-icon {
  font-size: 22px;
}
.acc-info,
.tx-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.acc-name,
.tx-merchant {
  font-weight: 600;
}
.acc-book,
.tx-date {
  font-size: 12px;
}
.acc-balance,
.tx-amount {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* ---------- 本期收支 ---------- */
.flow-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px 16px;
  margin: 0 16px 12px;
  border: 0.5px solid #e8e8e8;
}
.flow-row {
  display: flex;
  align-items: center;
}
.flow-item {
  flex: 1;
  min-width: 0;
}
.flow-item + .flow-item {
  border-left: 0.5px solid #f1efe8;
  padding-left: 12px;
}
.flow-label {
  font-size: 11px;
  color: #888780;
}
.flow-value {
  font-size: 17px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.flow-rate {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 0.5px solid #f1efe8;
}
.rate-label {
  font-size: 11px;
  color: #888780;
  flex: none;
}
.rate-bar {
  flex: 1;
  height: 6px;
  background: #f1efe8;
  border-radius: 3px;
  overflow: hidden;
}
.rate-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #7f77dd, #9b8fe8);
}
.rate-value {
  font-size: 11px;
  font-weight: 600;
  color: #534ab7;
  font-variant-numeric: tabular-nums;
  flex: none;
}

/* ---------- 近期账单 ---------- */
.bill-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.bill-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
}
.bill-sorts {
  display: inline-flex;
  background: #f1efe8;
  border-radius: 20px;
  padding: 2px;
}
.bill-sorts span {
  font-size: 11px;
  font-weight: 400;
  color: #888780;
  padding: 3px 10px;
  border-radius: 20px;
  cursor: pointer;
}
.bill-sorts span.on {
  background: #fff;
  color: #7f77dd;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(38, 33, 92, 0.1);
}
.bill-range {
  display: flex;
  gap: 8px;
  margin-bottom: 2px;
}
.bill-range span {
  flex: 1;
  text-align: center;
  font-size: 11px;
  color: #888780;
  background: #f1efe8;
  border-radius: 20px;
  padding: 5px 0;
  cursor: pointer;
}
.bill-summary {
  font-size: 11px;
  color: #888780;
  padding: 8px 0;
  margin-bottom: 2px;
  border-bottom: 0.5px solid #f1efe8;
}
.bill-summary b {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.bill-range span.on {
  background: #eeedfe;
  color: #7f77dd;
  font-weight: 600;
}
.bill-groups {
  margin-top: 2px;
}
.bill-group + .bill-group {
  margin-top: 8px;
}
.bill-day {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 2px;
  border-bottom: 0.5px solid #f1efe8;
}
.bill-day-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #2c2c2a;
}
.bill-day-name em {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: #a8a79f;
}
/* 借贷流水：中性灰，与收支的红/绿区分开 */
.text-loan {
  color: #888780;
}
.bill-cat-ic {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.bill-day-sum {
  display: flex;
  gap: 10px;
  font-size: 11px;
}
.bill-day-sum b {
  font-weight: 500;
  color: #888780;
}
.bill-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 2px;
  border-bottom: 0.5px solid #f7f6f3;
  cursor: pointer;
}
.bill-item:active {
  background: #f7f6f3;
}
.bill-item:last-child {
  border-bottom: none;
}
.bill-ic {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.bill-info {
  flex: 1;
  min-width: 0;
}
.bill-merchant {
  font-size: 13px;
  font-weight: 500;
  color: #2c2c2a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bill-account {
  font-size: 11px;
  color: #a8a79f;
  margin-top: 2px;
}
.bill-amount {
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.bill-loading,
.bill-empty {
  text-align: center;
  font-size: 12px;
  color: #a8a79f;
  padding: 20px 0;
}
</style>