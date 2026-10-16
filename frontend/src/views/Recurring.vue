<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { accountApi, ledgerApi, recurringApi } from '@/api'
import { toast } from '@/utils/toast'
import { yuan } from '@/utils/money'

const router = useRouter()
const loading = ref(true)
const items = ref([])
const accounts = ref([])
const categories = ref([])

const FREQ = [
  { key: 'daily', label: '每天' },
  { key: 'weekly', label: '每周' },
  { key: 'monthly', label: '每月' },
]
const WEEK = [
  { v: 0, label: '周一' },
  { v: 1, label: '周二' },
  { v: 2, label: '周三' },
  { v: 3, label: '周四' },
  { v: 4, label: '周五' },
  { v: 5, label: '周六' },
  { v: 6, label: '周日' },
]

const TYPES = [
  { key: 'expense', label: '支出' },
  { key: 'income', label: '收入' },
]

function money(cents) {
  return yuan(cents || 0).toFixed(2)
}
function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const activeCount = computed(() => items.value.filter((r) => r.is_active).length)

// ---------------------------------------------------------------- 表单
const showForm = ref(false)
const saving = ref(false)
const editingId = ref('')
const form = reactive({
  name: '',
  type: 'expense',
  amount: '',
  account: '',
  category: '',
  merchant: '',
  frequency: 'monthly',
  interval: 1,
  weekday: 0,
  day_of_month: 1,
  start_date: todayStr(),
  end_date: '',
  is_private: false,
})

const formCats = computed(() => categories.value)
const needWeekday = computed(() => form.frequency === 'weekly')
const needMonthDay = computed(() => form.frequency === 'monthly')

/** 切类型：支出/收入分类不同，清空已选分类避免残留一个列表里没有的值 */
function setType(key) {
  if (form.type === key) return
  form.type = key
  form.category = ''
  loadMeta()
}

async function loadMeta() {
  try {
    const a = await accountApi.list()
    accounts.value = a.items || a || []
  } catch (e) {
    accounts.value = []
  }
  try {
    const c = await ledgerApi.categories(form.type === 'income' ? 'income' : 'expense')
    categories.value = c.items || c || []
  } catch (e) {
    categories.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const list = await recurringApi.list()
    items.value = list || []
  } catch (e) {
    items.value = []
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = ''
  Object.assign(form, {
    name: '',
    type: 'expense',
    amount: '',
    account: (accounts.value[0] && accounts.value[0].id) || '',
    category: '',
    merchant: '',
    frequency: 'monthly',
    interval: 1,
    weekday: 0,
    day_of_month: 1,
    start_date: todayStr(),
    end_date: '',
    is_private: false,
  })
  loadMeta()
  showForm.value = true
}

function openEdit(r) {
  editingId.value = r.id
  Object.assign(form, {
    name: r.name,
    type: r.type,
    amount: String(r.amount),
    account: r.account_id || '',
    category: r.category_id || '',
    merchant: r.merchant || '',
    frequency: r.frequency,
    interval: r.interval || 1,
    weekday: r.weekday == null ? 0 : r.weekday,
    day_of_month: r.day_of_month || 1,
    start_date: r.start_date,
    end_date: r.end_date || '',
    is_private: !!r.is_private,
  })
  loadMeta()
  showForm.value = true
}

function payload() {
  const data = {
    name: form.name,
    type: form.type,
    amount: form.amount,
    account: form.account || null,
    category: form.category || null,
    merchant: form.merchant,
    frequency: form.frequency,
    interval: Number(form.interval) || 1,
    start_date: form.start_date,
    end_date: form.end_date || null,
    is_private: form.is_private && form.type === 'expense',
  }
  if (needWeekday.value) data.weekday = Number(form.weekday)
  if (needMonthDay.value) data.day_of_month = Number(form.day_of_month)
  return data
}

async function submit() {
  const amt = Number(form.amount)
  if (!form.name.trim()) return toast('请填写规则名称')
  if (!amt || amt <= 0) return toast('请输入金额')
  saving.value = true
  try {
    if (editingId.value) {
      await recurringApi.update(editingId.value, payload())
      toast('已更新规则')
    } else {
      await recurringApi.create(payload())
      toast('已创建规则')
    }
    showForm.value = false
    await load()
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggle(r) {
  try {
    await recurringApi.update(r.id, { is_active: !r.is_active })
    await load()
  } catch (e) {
    toast(e.message || '操作失败')
  }
}

async function runNow(r) {
  try {
    const res = await recurringApi.run(r.id)
    toast(res.message || '已记一笔')
    await load()
  } catch (e) {
    toast(e.message || '执行失败')
  }
}

async function remove(r) {
  try {
    await recurringApi.remove(r.id)
    toast('已删除规则')
    await load()
  } catch (e) {
    toast(e.message || '删除失败')
  }
}

onMounted(async () => {
  await loadMeta()
  await load()
})
</script>

<template>
  <div class="page rec-page">
    <div class="top-bar">
      <span class="top-title">⏰ 定时记账</span>
      <span class="top-close" @click="router.push('/mine')">×</span>
    </div>

    <!-- 说明：这个功能做什么，避免用户误以为是「提醒」 -->
    <div class="rec-note">
      按规则自动生成流水并入账，不用每月手动记房租、通勤这类固定收支。规则由服务端每天检查一次。
    </div>

    <div v-if="loading" class="tip">加载中…</div>
    <div v-else-if="!items.length" class="tip">
      还没有定时记账规则，点下面按钮建一条
    </div>

    <div v-else class="list">
      <div v-for="r in items" :key="r.id" class="rec-card" :class="{ off: !r.is_active }">
        <div class="rc-head">
          <span class="rc-icon">{{ r.category_icon || (r.type === 'income' ? '💵' : '💸') }}</span>
          <span class="rc-name">{{ r.name }}</span>
          <span class="rc-amount" :class="r.type === 'income' ? 'text-income' : 'text-expense'">
            {{ r.type === 'income' ? '+' : '-' }}¥{{ money(r.amount_cents) }}
          </span>
        </div>

        <div class="rc-meta">
          <span class="rc-freq">{{ r.schedule_text }}</span>
          <span class="rc-next">下次 {{ r.next_run }}</span>
          <span v-if="r.last_error" class="rc-err">⚠️ {{ r.last_error }}</span>
        </div>

        <div class="rc-sub">
          <span v-if="r.account_name">{{ r.account_icon }} {{ r.account_name }}</span>
          <span v-if="r.end_date">· 至 {{ r.end_date }}</span>
          <span>· 已生成 {{ r.run_count }} 笔</span>
          <span v-if="r.is_private">· 🙈 私密</span>
        </div>

        <div class="rc-ops">
          <span class="rc-op" @click="openEdit(r)">编辑</span>
          <span class="rc-op" @click="toggle(r)">{{ r.is_active ? '停用' : '启用' }}</span>
          <span class="rc-op" @click="runNow(r)">立即记一笔</span>
          <span class="rc-op danger" @click="remove(r)">删除</span>
        </div>
      </div>
    </div>

    <div class="add-float" @click="openCreate">+</div>

    <!-- ---------------------------------------------------------------- 表单 -->
    <div v-if="showForm" class="sheet-mask" @click.self="showForm = false">
      <div class="sheet">
        <div class="sheet-head">
          <span class="sheet-title">{{ editingId ? '编辑规则' : '新建规则' }}</span>
          <span class="sheet-close" @click="showForm = false">✕</span>
        </div>

        <div class="type-bar">
          <span
            v-for="t in TYPES"
            :key="t.key"
            class="type-pill"
            :class="{ active: form.type === t.key }"
            @click="setType(t.key)"
            >{{ t.label }}</span
          >
        </div>

        <label class="form-label">规则名称</label>
        <input v-model="form.name" class="form-input" placeholder="如：房租、通勤、工资" />

        <label class="form-label">金额</label>
        <input v-model="form.amount" class="form-input" type="number" placeholder="0.00" />

        <label class="form-label">频率</label>
        <div class="chips">
          <span
            v-for="f in FREQ"
            :key="f.key"
            class="chip"
            :class="{ on: form.frequency === f.key }"
            @click="form.frequency = f.key"
            >{{ f.label }}</span
          >
          <span class="chip-inline">
            每
            <input v-model="form.interval" class="mini-input" type="number" min="1" />
            {{ form.frequency === 'daily' ? '天' : form.frequency === 'weekly' ? '周' : '月' }}
          </span>
        </div>

        <div v-if="needWeekday" class="chips">
          <span
            v-for="w in WEEK"
            :key="w.v"
            class="chip"
            :class="{ on: Number(form.weekday) === w.v }"
            @click="form.weekday = w.v"
            >{{ w.label }}</span
          >
        </div>

        <label v-if="needMonthDay" class="form-label">每月几号（31 = 月末）</label>
        <input
          v-if="needMonthDay"
          v-model="form.day_of_month"
          class="form-input"
          type="number"
          min="1"
          max="31"
        />

        <label class="form-label">开始日期</label>
        <input v-model="form.start_date" class="form-input" type="date" />

        <label class="form-label">结束日期（留空表示长期）</label>
        <input v-model="form.end_date" class="form-input" type="date" />

        <label class="form-label">账户</label>
        <select v-model="form.account" class="form-input">
          <option value="">不指定</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.icon }} {{ a.name }}
          </option>
        </select>

        <label class="form-label">分类</label>
        <select v-model="form.category" class="form-input">
          <option value="">自动匹配</option>
          <option v-for="c in formCats" :key="c.id" :value="c.id">
            {{ c.icon }} {{ c.name }}
          </option>
        </select>

        <label class="form-label">备注</label>
        <input v-model="form.merchant" class="form-input" placeholder="选填" />

        <label v-if="form.type === 'expense'" class="check-line">
          <input v-model="form.is_private" type="checkbox" />
          <span>记为私密消费（不计入共同支出）</span>
        </label>

        <div class="form-actions">
          <button class="btn-primary" :disabled="saving" @click="submit">
            {{ saving ? '保存中…' : '保存' }}
          </button>
          <button class="btn-secondary" @click="showForm = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rec-page {
  padding: 0 16px 100px;
  max-width: 560px;
  margin: 0 auto;
}
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
}
.top-title {
  font-size: 17px;
  font-weight: 700;
  color: #2c2c2a;
}
.top-close {
  font-size: 24px;
  color: #888780;
  padding: 0 4px;
}
.rec-note {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  font-size: 12px;
  color: #888780;
  line-height: 1.6;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rec-card {
  padding: 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
}
.rec-card.off {
  opacity: 0.55;
}
.rc-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rc-icon {
  font-size: 20px;
}
.rc-name {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: #0d0d0d;
}
.rc-amount {
  font-size: 17px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.rc-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: #5f5e5a;
}
.rc-freq {
  padding: 2px 10px;
  border-radius: 999px;
  background: #eeedfe;
  color: #534ab7;
}
.rc-err {
  color: #e53935;
}
.rc-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #888780;
}
.rc-ops {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0efea;
  font-size: 13px;
  color: #534ab7;
}
.rc-op.danger {
  color: #e53935;
  margin-left: auto;
}
.tip {
  padding: 40px 0;
  text-align: center;
  color: #888780;
  font-size: 13px;
}
.add-float {
  position: fixed;
  right: 20px;
  bottom: 90px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #7f77dd;
  color: #fff;
  font-size: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.4);
}
/* 表单 */
.sheet-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: flex-end;
  z-index: 60;
}
.sheet {
  width: 100%;
  max-width: 560px;
  margin: 0 auto;
  max-height: 84vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 20px 20px 32px;
}
.sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.sheet-title {
  font-size: 16px;
  font-weight: 700;
  color: #2c2c2a;
}
.sheet-close {
  color: #b4b2a9;
  font-size: 18px;
}
.type-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.type-pill {
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 13px;
  background: #f1efe8;
  color: #5f5e5a;
}
.type-pill.active {
  background: #534ab7;
  color: #fff;
  font-weight: 600;
}
.form-label {
  display: block;
  font-size: 12px;
  color: #888780;
  margin: 12px 0 6px;
}
.form-input {
  width: 100%;
  padding: 12px 14px;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  font-size: 14px;
  background: #fafbfc;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.chip {
  padding: 8px 14px;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: #2c2c2a;
}
.chip.on {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #534ab7;
  font-weight: 600;
}
.chip-inline {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #5f5e5a;
}
.mini-input {
  width: 52px;
  padding: 6px 8px;
  border: 0.5px solid #d3d1c7;
  border-radius: 6px;
  text-align: center;
}
.check-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  font-size: 13px;
  color: #5f5e5a;
}
.form-actions {
  margin-top: 20px;
}
.btn-primary,
.btn-secondary {
  width: 100%;
  padding: 12px 0;
  margin-bottom: 8px;
  border-radius: 8px;
  font-size: 15px;
}
.btn-primary {
  background: #7f77dd;
  color: #fff;
}
.btn-secondary {
  background: #f1efe8;
  color: #5f5e5a;
}
</style>
