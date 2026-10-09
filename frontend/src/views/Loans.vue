<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { accountApi, loanApi } from '@/api'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { toast } from '@/utils/toast'
import dayjs from 'dayjs'

const router = useRouter()
const loading = ref(true)
const errorText = ref('')
const items = ref([])
const summary = ref(null)
const accounts = ref([])
const filter = ref('all')
const expanded = ref('')

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'lend', label: '借出' },
  { key: 'borrow', label: '借入' },
  { key: 'unpaid', label: '未还清' },
  { key: 'overdue', label: '逾期' },
  { key: 'settled', label: '已还清' },
]

const shown = computed(() => {
  const list = items.value
  if (filter.value === 'all') return list
  if (filter.value === 'lend' || filter.value === 'borrow') {
    return list.filter((l) => l.direction === filter.value)
  }
  if (filter.value === 'unpaid') return list.filter((l) => l.status !== 'settled')
  if (filter.value === 'settled') return list.filter((l) => l.status === 'settled')
  if (filter.value === 'overdue') return list.filter((l) => l.overdue)
  return list
})

const countByTab = computed(() => {
  const map = { all: items.value.length }
  map.lend = items.value.filter((l) => l.direction === 'lend').length
  map.borrow = items.value.filter((l) => l.direction === 'borrow').length
  map.unpaid = items.value.filter((l) => l.status !== 'settled').length
  map.overdue = items.value.filter((l) => l.overdue).length
  map.settled = items.value.filter((l) => l.status === 'settled').length
  return map
})

// ---------------------------------------------------------------- 新建借款
const showForm = ref(false)
const saving = ref(false)
const form = reactive({
  direction: 'lend',
  party: '',
  amount: '',
  account: '',
  loan_date: '',
  due_date: '',
  note: '',
})

function openForm() {
  Object.assign(form, {
    direction: 'lend',
    party: '',
    amount: '',
    account: accounts.value[0]?.id || '',
    loan_date: dayjs().format('YYYY-MM-DD'),
    due_date: '',
    note: '',
  })
  showForm.value = true
}

async function submitForm() {
  if (!form.party.trim()) return toast('请填写对方是谁')
  const amt = Number(form.amount)
  if (!amt || amt <= 0) return toast('请输入金额')
  saving.value = true
  try {
    await loanApi.create({
      direction: form.direction,
      party: form.party.trim(),
      amount: String(amt),
      account: form.account || null,
      loan_date: form.loan_date || undefined,
      due_date: form.due_date || null,
      note: form.note.trim(),
    })
    showForm.value = false
    toast(form.direction === 'lend' ? '已记借出' : '已记借入')
    await load()
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- 还款
const repayTarget = ref(null)
const showRepay = ref(false)
const repayForm = reactive({ amount: '', account: '', repay_date: '', note: '' })

function openRepay(loan) {
  repayTarget.value = loan
  Object.assign(repayForm, {
    amount: (loan.remaining_cents / 100).toFixed(2),
    account: loan.account || '',
    repay_date: dayjs().format('YYYY-MM-DD'),
    note: '',
  })
  showRepay.value = true
}

async function submitRepay() {
  const amt = Number(repayForm.amount)
  if (!amt || amt <= 0) return toast('请输入还款金额')
  saving.value = true
  try {
    const r = await loanApi.repay(repayTarget.value.id, {
      amount: String(amt),
      account: repayForm.account || null,
      repay_date: repayForm.repay_date || undefined,
      note: repayForm.note.trim(),
    })
    showRepay.value = false
    toast(r?.loan?.status === 'settled' ? '这笔已结清 🎉' : '还款已记录')
    await load()
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function undoRepayment(rp) {
  const ok = await ask({
    title: `撤销 ${day(rp.repay_date)} 还的 ¥${rp.amount}？`,
    lines: ['这笔还款会被删除', '收付账户余额同步回退', '借款状态会退回未还/部分还'],
    okText: '确认撤销',
  })
  if (!ok) return
  try {
    await loanApi.removeRepayment(rp.id)
    toast('还款已撤销')
    await load()
  } catch (e) {
    toast(e.message || '撤销失败')
  }
}

// ---------------------------------------------------------------- 二次确认
// ★ 一律用页内 ConfirmSheet：原生 confirm() 在内置预览 / WebView 里会被静默吞掉
const confirmState = reactive({ show: false, title: '', lines: [], okText: '确认' })
let confirmResolve = null

function ask({ title, lines, okText = '确认' }) {
  confirmState.title = title
  confirmState.lines = lines
  confirmState.okText = okText
  confirmState.show = true
  return new Promise((resolve) => {
    confirmResolve = resolve
  })
}

function answerConfirm(ok) {
  confirmState.show = false
  const fn = confirmResolve
  confirmResolve = null
  if (fn) fn(ok)
}

async function askRemove(loan) {
  const ok = await ask({
    title: `删除「${loan.party}」这笔 ${loan.direction_display}？`,
    lines: [
      `金额 ¥${loan.amount}${loan.repaid_cents ? `，已还 ¥${loan.repaid}` : ''}`,
      '关联账户余额会同步回退',
      '删除后无法恢复',
    ],
    okText: '确认删除',
  })
  if (!ok) return
  try {
    await loanApi.remove(loan.id)
    toast('已删除')
    await load()
  } catch (e) {
    toast(e.message || '删除失败')
  }
}

// ---------------------------------------------------------------- 数据
function money(c) {
  return (Number(c || 0) / 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
const day = (v) => (v ? String(v).slice(0, 10) : '')
function pct(loan) {
  if (!loan.amount_cents) return 0
  return Math.min(100, Math.round((loan.repaid_cents / loan.amount_cents) * 100))
}

async function load() {
  loading.value = true
  errorText.value = ''
  try {
    const d = await loanApi.list()
    items.value = d.items || []
    summary.value = d.summary || null
  } catch (e) {
    errorText.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadAccounts() {
  try {
    const a = await accountApi.list()
    accounts.value = a.items || a || []
  } catch (e) {
    accounts.value = []
  }
}

onMounted(async () => {
  await loadAccounts()
  await load()
})
</script>

<template>
  <div class="loan-page">
    <div class="top-bar">
      <span class="top-title">🤝 借钱来往</span>
      <span class="top-close" @click="router.push('/mine')">×</span>
    </div>

    <!-- 总览 -->
    <div v-if="summary" class="sum-card">
      <div class="sum-row">
        <div class="sum-item">
          <div class="sum-label">📤 借出未收</div>
          <div class="sum-value lend">¥{{ money(summary.lend_cents) }}</div>
          <div class="sum-sub">{{ summary.lend_count }} 笔别人欠咱家</div>
        </div>
        <div class="sum-split"></div>
        <div class="sum-item">
          <div class="sum-label">📥 借入未还</div>
          <div class="sum-value borrow">¥{{ money(summary.borrow_cents) }}</div>
          <div class="sum-sub">{{ summary.borrow_count }} 笔咱家欠别人</div>
        </div>
      </div>
      <div class="sum-foot">
        <span>
          {{ summary.net_cents >= 0
            ? `净借出 ¥${money(summary.net_cents)}，属家庭应收资产`
            : `净欠人 ¥${money(-summary.net_cents)}，属家庭负债` }}
        </span>
        <span v-if="summary.overdue_count" class="sum-overdue">
          ⚠️ {{ summary.overdue_count }} 笔已过约定日
        </span>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="tabs">
      <span
        v-for="t in TABS"
        :key="t.key"
        class="tab"
        :class="{ on: filter === t.key }"
        @click="filter = t.key"
        >{{ t.label }}<em v-if="countByTab[t.key]">{{ countByTab[t.key] }}</em></span
      >
    </div>

    <div v-if="loading" class="tip">加载中…</div>
    <div v-else-if="errorText" class="tip">{{ errorText }}</div>
    <div v-else-if="!shown.length" class="tip">
      {{ filter === 'all' ? '还没有借钱记录，点下面按钮记一笔' : '这个筛选下没有记录' }}
    </div>

    <div v-else class="list">
      <div v-for="l in shown" :key="l.id" class="loan-card">
        <div class="lc-head">
          <span class="lc-dir" :class="l.direction">
            {{ l.direction === 'lend' ? '📤 借出' : '📥 借入' }}
          </span>
          <span class="lc-party">{{ l.party }}</span>
          <span class="lc-amount" :class="l.direction">¥{{ money(l.amount_cents) }}</span>
        </div>

        <div class="lc-bar">
          <div class="bar">
            <i :class="l.direction" :style="{ width: pct(l) + '%' }"></i>
          </div>
          <span class="bar-text">
            已还 ¥{{ money(l.repaid_cents) }} · 剩 ¥{{ money(l.remaining_cents) }}
          </span>
        </div>

        <div class="lc-meta">
          <span class="tag" :class="[l.status, { od: l.overdue }]">
            {{ l.overdue ? '逾期未还' : l.status_display }}
          </span>
          <span>{{ day(l.loan_date) }}</span>
          <span v-if="l.due_date" :class="{ danger: l.overdue }">约定 {{ day(l.due_date) }}</span>
          <span v-if="l.account_name">· {{ l.account_name }}</span>
          <span v-if="l.note" class="note">“{{ l.note }}”</span>
        </div>

        <div class="lc-ops">
          <span v-if="l.repayments?.length" class="op" @click="expanded = expanded === l.id ? '' : l.id">
            {{ expanded === l.id ? '收起还款' : `还款 ${l.repayments.length} 次` }}
          </span>
          <span v-if="l.status !== 'settled'" class="op primary" @click="openRepay(l)">记还款</span>
          <span class="op danger" @click="askRemove(l)">删除</span>
        </div>

        <div v-if="expanded === l.id" class="repay-list">
          <div v-for="rp in l.repayments" :key="rp.id" class="rp-row">
            <span>{{ day(rp.repay_date) }}</span>
            <span class="rp-amt">¥{{ money(rp.amount_cents) }}</span>
            <span class="rp-sub">
              {{ rp.account_name || '未关联账户' }} · {{ rp.operator_name }}
              <em v-if="rp.note">{{ rp.note }}</em>
            </span>
            <span class="op danger" @click="undoRepayment(rp)">撤销</span>
          </div>
        </div>
      </div>
    </div>

    <button class="btn btn-primary full-btn" @click="openForm">＋ 记一笔借钱来往</button>

    <div class="rule-note">
      关联账户后，借出会立刻扣减该账户余额、借入会进账；还款同理反向冲正。
      不选账户则只留台账，不影响余额。借款记录全家可见。
    </div>
  </div>

  <!-- 新建弹层 -->
  <div v-if="showForm" class="sheet-mask" @click="showForm = false">
    <div class="sheet" @click.stop>
      <div class="sheet-head">
        <span class="sheet-title">记一笔</span>
        <span class="sheet-close" @click="showForm = false">×</span>
      </div>

      <div class="dir-row">
        <div class="dir-btn" :class="{ on: form.direction === 'lend' }" @click="form.direction = 'lend'">
          📤 我借给别人
          <em>对方欠咱家</em>
        </div>
        <div class="dir-btn" :class="{ on: form.direction === 'borrow' }" @click="form.direction = 'borrow'">
          📥 我借进来
          <em>咱家欠对方</em>
        </div>
      </div>

      <div class="fld">
        <label class="fld-label">对方</label>
        <input v-model="form.party" class="fld-input" placeholder="如：小王 / 哥哥" maxlength="50" />
      </div>
      <div class="fld">
        <label class="fld-label">金额</label>
        <input v-model="form.amount" class="fld-input" type="number" placeholder="0.00" />
      </div>
      <div class="fld">
        <label class="fld-label">关联账户{{ form.direction === 'lend' ? '（钱从哪出去）' : '（钱进哪个账户）' }}</label>
        <div class="chip-row">
          <span class="chip" :class="{ active: !form.account }" @click="form.account = ''">不关联</span>
          <span
            v-for="a in accounts"
            :key="a.id"
            class="chip"
            :class="{ active: form.account === a.id }"
            @click="form.account = a.id"
            >{{ a.icon }} {{ a.name }}</span
          >
        </div>
      </div>
      <div class="fld-row">
        <div class="fld">
          <label class="fld-label">发生日期</label>
          <input v-model="form.loan_date" class="fld-input" type="date" />
        </div>
        <div class="fld">
          <label class="fld-label">约定还款日（选填）</label>
          <input v-model="form.due_date" class="fld-input" type="date" />
        </div>
      </div>
      <div class="fld">
        <label class="fld-label">备注（选填）</label>
        <input v-model="form.note" class="fld-input" placeholder="如：装修周转，年底还" maxlength="255" />
      </div>

      <button class="btn btn-primary full-btn" :disabled="saving" @click="submitForm">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </div>
  </div>

  <!-- 还款弹层 -->
  <div v-if="showRepay" class="sheet-mask" @click="showRepay = false">
    <div class="sheet" @click.stop>
      <div class="sheet-head">
        <span class="sheet-title">记还款</span>
        <span class="sheet-close" @click="showRepay = false">×</span>
      </div>
      <div class="repay-sum">
        {{ repayTarget?.party }} · {{ repayTarget?.direction_display }} ¥{{ repayTarget?.amount }}
        <em>剩 ¥{{ repayTarget?.remaining }}</em>
      </div>
      <div class="fld">
        <label class="fld-label">本次还款</label>
        <input v-model="repayForm.amount" class="fld-input" type="number" placeholder="0.00" />
      </div>
      <div class="fld">
        <label class="fld-label">
          {{ repayTarget?.direction === 'lend' ? '收到的钱进哪个账户' : '从哪个账户付出去' }}
        </label>
        <div class="chip-row">
          <span class="chip" :class="{ active: !repayForm.account }" @click="repayForm.account = ''">不关联</span>
          <span
            v-for="a in accounts"
            :key="a.id"
            class="chip"
            :class="{ active: repayForm.account === a.id }"
            @click="repayForm.account = a.id"
            >{{ a.icon }} {{ a.name }}</span
          >
        </div>
      </div>
      <div class="fld">
        <label class="fld-label">还款日期</label>
        <input v-model="repayForm.repay_date" class="fld-input" type="date" />
      </div>
      <div class="fld">
        <label class="fld-label">备注（选填）</label>
        <input v-model="repayForm.note" class="fld-input" placeholder="如：微信转账还了一半" maxlength="255" />
      </div>
      <button class="btn btn-primary full-btn" :disabled="saving" @click="submitRepay">
        {{ saving ? '保存中…' : '确认还款' }}
      </button>
    </div>
  </div>

  <ConfirmSheet
    :visible="confirmState.show"
    :title="confirmState.title"
    :lines="confirmState.lines"
    :ok-text="confirmState.okText"
    :danger="true"
    @ok="answerConfirm(true)"
    @cancel="answerConfirm(false)"
  />
</template>

<style scoped>
.loan-page {
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

/* 总览 */
.sum-card {
  margin: 0 16px 14px;
  padding: 14px 16px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 14px;
}
.sum-row {
  display: flex;
  align-items: stretch;
}
.sum-item {
  flex: 1;
  min-width: 0;
}
.sum-split {
  width: 0.5px;
  background: #eeece4;
  margin: 2px 10px;
}
.sum-label {
  font-size: 12px;
  color: #5f5e5a;
}
.sum-value {
  font-size: 21px;
  font-weight: 700;
  margin: 4px 0 2px;
  font-variant-numeric: tabular-nums;
}
.sum-value.lend {
  color: #1d9e75;
}
.sum-value.borrow {
  color: #ba7517;
}
.sum-sub {
  font-size: 11px;
  color: #b8b6ae;
}
.sum-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 0.5px solid #f1efe8;
  font-size: 11px;
  color: #888780;
}
.sum-overdue {
  color: #d03b3b;
  font-weight: 600;
}

/* 筛选 */
.tabs {
  display: flex;
  gap: 6px;
  padding: 0 16px 12px;
  overflow-x: auto;
}
.tab {
  flex: none;
  font-size: 12px;
  padding: 5px 11px;
  border-radius: 999px;
  background: #fff;
  border: 0.5px solid #e8e6de;
  color: #5f5e5a;
  cursor: pointer;
  white-space: nowrap;
}
.tab em {
  font-style: normal;
  margin-left: 3px;
  color: #b8b6ae;
}
.tab.on {
  background: #534ab7;
  border-color: #534ab7;
  color: #fff;
}
.tab.on em {
  color: rgba(255, 255, 255, 0.8);
}

.tip {
  text-align: center;
  font-size: 13px;
  color: #b8b6ae;
  padding: 40px 20px;
}
.list {
  padding: 0 16px;
}

/* 单条 */
.loan-card {
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  padding: 13px 14px;
  margin-bottom: 10px;
}
.lc-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lc-dir {
  flex: none;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #eaf5ef;
  color: #1d9e75;
}
.lc-dir.borrow {
  background: #fbf0e2;
  color: #ba7517;
}
.lc-party {
  font-size: 15px;
  font-weight: 600;
  color: #26215c;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lc-amount {
  flex: none;
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.lc-amount.lend {
  color: #1d9e75;
}
.lc-amount.borrow {
  color: #ba7517;
}
.lc-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 9px 0 7px;
}
.bar {
  flex: 1;
  height: 5px;
  border-radius: 999px;
  background: #f1efe8;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: #1d9e75;
  border-radius: 999px;
}
.bar i.borrow {
  background: #ba7517;
}
.bar-text {
  flex: none;
  font-size: 11px;
  color: #888780;
  font-variant-numeric: tabular-nums;
}
.lc-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #888780;
}
.lc-meta .danger {
  color: #d03b3b;
  font-weight: 600;
}
.lc-meta .note {
  color: #a8a69e;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f1efe8;
  color: #5f5e5a;
}
.tag.pending {
  background: #fdf1e6;
  color: #ba7517;
}
.tag.partial {
  background: #eeedfe;
  color: #534ab7;
}
.tag.settled {
  background: #eaf5ef;
  color: #1d9e75;
}
.tag.od {
  background: #fbe9e9;
  color: #d03b3b;
  font-weight: 600;
}
.lc-ops {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 9px;
  padding-top: 9px;
  border-top: 0.5px solid #f5f3ec;
}
.op {
  font-size: 12px;
  color: #5f5e5a;
  cursor: pointer;
}
.op.primary {
  color: #534ab7;
  font-weight: 600;
}
.op.danger {
  color: #d03b3b;
}
.repay-list {
  margin-top: 8px;
  background: #faf9f6;
  border-radius: 8px;
  padding: 4px 10px;
}
.rp-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #5f5e5a;
  padding: 7px 0;
  border-bottom: 0.5px solid #f0eee6;
}
.rp-row:last-child {
  border-bottom: none;
}
.rp-amt {
  font-weight: 600;
  color: #1d9e75;
  font-variant-numeric: tabular-nums;
}
.rp-sub {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: #a8a69e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rp-sub em {
  font-style: normal;
  margin-left: 4px;
}

.full-btn {
  width: calc(100% - 32px);
  margin: 6px 16px 0;
}
.rule-note {
  margin: 12px 16px 0;
  font-size: 11px;
  line-height: 1.7;
  color: #a8a69e;
}

/* 弹层内表单 */
.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
}
.sheet-title {
  font-size: 16px;
  font-weight: 700;
  color: #26215c;
}
.sheet-close {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #f1efe8;
  color: #888780;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  cursor: pointer;
}
.dir-row {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}
.dir-btn {
  flex: 1;
  border: 1px solid #e8e6de;
  border-radius: 10px;
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #5f5e5a;
  background: #fff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dir-btn em {
  font-style: normal;
  font-size: 11px;
  font-weight: 400;
  color: #a8a69e;
}
.dir-btn.on {
  border-color: #534ab7;
  background: #eeedfe;
  color: #26215c;
}
.fld {
  margin-bottom: 12px;
  flex: 1;
  min-width: 0;
}
.fld-row {
  display: flex;
  gap: 10px;
}
.fld-label {
  display: block;
  font-size: 11px;
  color: #888780;
  margin-bottom: 5px;
}
.fld-input {
  width: 100%;
  box-sizing: border-box;
  font-size: 14px;
  padding: 10px;
  border: 0.5px solid #e3e1da;
  border-radius: 8px;
  background: #fff;
  color: #1c1b1a;
}
.fld-input:focus {
  outline: none;
  border-color: #7f77dd;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.repay-sum {
  font-size: 13px;
  color: #5f5e5a;
  background: #faf9f6;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 12px;
}
.repay-sum em {
  font-style: normal;
  float: right;
  font-weight: 700;
  color: #d03b3b;
}
</style>
