<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ledgerApi, accountApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { yuan } from '@/utils/money'
import dayjs from 'dayjs'
import { toast } from '@/utils/toast'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ---------------- 编辑模式：从首页点账单进来时带 ?id=
const editingId = ref('')
const isEdit = computed(() => !!editingId.value)
const types = [
  { key: 'expense', label: '支出' },
  { key: 'income', label: '收入' },
  { key: 'transfer', label: '借还' },
]
const activeType = ref('expense')
const categories = ref([])
const accounts = ref([])
const categoryId = ref('')
const accountId = ref('')

// ---------------- 账本：默认跟随登录身份，只展示家庭里真实存在的账本
const DEFAULT_BOOK = { shared: '共同账本', husband: '账本一', wife: '账本二' }
const BOOK_ORDER = ['husband', 'wife', 'shared']
/** 我在家庭里的账本（主账号=账本一、第二人=账本二…） */
const myBook = computed(() => auth.member?.book_type || 'husband')
const bookType = ref('')
function bookName(type) {
  return auth.family?.book_labels?.[type] || DEFAULT_BOOK[type] || type
}
/**
 * 可记账的账户：只保留「我名下」的账户。
 * 后端 AccountSerializer 回 is_mine（不暴露 user_id，隐私更稳），
 * 记账只能落到自己的账户上，对方名下的账户即便可见也不该出现在这里。
 */
const myAccounts = computed(() => accounts.value.filter((a) => a.is_mine !== false))
/**
 * 可选的账本：只出现「我的账本 + 共同账本」。
 * 对方专属账本（如我属 husband、对方属 wife）整本不进选择，
 * 避免在自己账号体系下误选到对方的账本。
 */
const existingBooks = computed(() => {
  const used = new Set(myAccounts.value.map((a) => a.book_type))
  return BOOK_ORDER.filter((b) => {
    // 只留「我的账本」与「共同账本」，对方专属账本一律不出现
    if (b !== 'shared' && b !== myBook.value) return false
    // 且必须真的建过账户，没建的空账本不占位置
    return used.has(b)
  })
})
/**
 * 账本 chips 实际渲染的列表：可选账本之外，把「编辑中的老账单所属账本」补进来。
 * 否则老账单落在已不可选的账本时，chips 里没有选中项，用户会以为没选账本。
 */
const bookChoices = computed(() => {
  const list = [...existingBooks.value]
  if (bookType.value && !list.includes(bookType.value)) list.push(bookType.value)
  return list
})
/** 当前账本下的账户；账本为空表示不过滤 */
const visibleAccounts = computed(() =>
  bookType.value
    ? myAccounts.value.filter((a) => a.book_type === bookType.value)
    : myAccounts.value,
)
/** 编辑态下账户可能不在我的账户里（老数据），兜底保留原账户，避免保存时被清空 */
const accountChoices = computed(() => {
  const list = [...visibleAccounts.value]
  if (accountId.value && !list.some((a) => a.id === accountId.value)) {
    const origin = accounts.value.find((a) => a.id === accountId.value)
    if (origin) list.push(origin)
  }
  return list
})
const amount = ref('')
const merchant = ref('')
const description = ref('')
const isPrivate = ref(false)
const saving = ref(false)
const showAddCat = ref(false)

// ---------------- 新增自定义分类
const CAT_ICONS = ['💰', '🍜', '🛒', '🚗', '🏠', '💊', '🎁', '📚', '✈️', '🐱', '💪', '🎮', '💄', '👶', '🧾', '☕']
const newCat = ref({ name: '', icon: '💰' })
const catSaving = ref(false)

function openAddCat() {
  newCat.value = { name: '', icon: '💰' }
  showAddCat.value = true
}
async function submitCat() {
  const name = newCat.value.name.trim()
  if (!name) return toast('请填写分类名称')
  // 转账用的是支出分类（与 loadCategories 的规则保持一致）
  const kind = activeType.value === 'income' ? 'income' : 'expense'
  catSaving.value = true
  try {
    const c = await ledgerApi.createCategory({ name, kind, icon: newCat.value.icon })
    showAddCat.value = false
    await loadCategories()
    categoryId.value = c.id // 新建完直接选中，省一步
    toast(`已新增分类「${c.name}」`)
  } catch (e) {
    toast(e.message || '新增失败')
  } finally {
    catSaving.value = false
  }
}

// ---------------- 备注历史：同一分类下最近用过的备注，最多 5 条
const merchantHistory = ref([])
async function loadMerchantHistory() {
  if (!categoryId.value) {
    merchantHistory.value = []
    return
  }
  try {
    const list = await ledgerApi.merchantHistory({ category_id: categoryId.value })
    merchantHistory.value = Array.isArray(list) ? list : []
  } catch (e) {
    merchantHistory.value = []
  }
}
// 分类一换就重新拉历史（切换类型时 categoryId 也会被重置）
watch(categoryId, () => {
  loadMerchantHistory()
})

// 日期：默认今天，点开展开日历可改到过去任意一天（不允许选未来）
const txDate = ref(dayjs().format('YYYY-MM-DD'))
const WEEK = ['一', '二', '三', '四', '五', '六', '日']
const todayStr = computed(() => dayjs().format('YYYY-MM-DD'))
const showDatePanel = ref(false)
const viewYM = ref(dayjs().format('YYYY-MM'))
const dateLabel = computed(() => {
  const d = dayjs(txDate.value)
  const today = dayjs().startOf('day')
  if (d.isSame(today, 'day')) return `今天 · ${d.format('M月D日')}`
  if (d.isSame(today.subtract(1, 'day'), 'day')) return `昨天 · ${d.format('M月D日')}`
  return d.format('YYYY年M月D日')
})

const viewTitle = computed(() => dayjs(`${viewYM.value}-01`).format('YYYY年M月'))
// 当月之后没有可记的日子，「下一月」直接禁用
const nextDisabled = computed(
  () => !dayjs(`${viewYM.value}-01`).isBefore(dayjs().startOf('month')),
)

const calendarDays = computed(() => {
  const first = dayjs(`${viewYM.value}-01`)
  const total = first.daysInMonth()
  const lead = (first.day() + 6) % 7 // 周一做为一周首日
  const cells = []
  for (let i = lead; i > 0; i--) {
    const d = first.subtract(i, 'day')
    cells.push({ key: `p${d.format('YYYY-MM-DD')}`, date: d.format('YYYY-MM-DD'), day: d.date(), muted: true })
  }
  for (let n = 1; n <= total; n++) {
    const d = first.date(n)
    cells.push({ key: d.format('YYYY-MM-DD'), date: d.format('YYYY-MM-DD'), day: n, muted: false })
  }
  let tail = 1
  while (cells.length % 7 !== 0 || cells.length < 42) {
    const d = first.date(total + tail++)
    cells.push({ key: `n${d.format('YYYY-MM-DD')}`, date: d.format('YYYY-MM-DD'), day: d.date(), muted: true })
  }
  return cells
})

function openDatePanel() {
  viewYM.value = dayjs(txDate.value).format('YYYY-MM')
  showDatePanel.value = !showDatePanel.value
}
function shiftMonth(step) {
  if (step > 0 && nextDisabled.value) return
  viewYM.value = dayjs(`${viewYM.value}-01`).add(step, 'month').format('YYYY-MM')
}
function pickDate(cell) {
  if (cell.date > todayStr.value) return
  txDate.value = cell.date
  showDatePanel.value = false
}
function pickToday() {
  txDate.value = todayStr.value
  viewYM.value = dayjs().format('YYYY-MM')
  showDatePanel.value = false
}

/** 选今天就用当前时刻；选过去某天则保留当天 + 当前时分秒，排序更自然 */
function txDateTime() {
  const now = dayjs()
  const picked = dayjs(txDate.value)
  const at = picked.isSame(now, 'day')
    ? now
    : picked.hour(now.hour()).minute(now.minute()).second(now.second())
  return at.format('YYYY-MM-DDTHH:mm:ss')
}

async function loadCategories() {
  try {
    const d = await ledgerApi.categories(activeType.value === 'transfer' ? 'expense' : activeType.value)
    categories.value = d.items || d || []
  } catch (e) {
    console.error(e)
  }
  await loadMerchantHistory()
}
async function loadAccounts() {
  try {
    const d = await accountApi.list()
    accounts.value = d.items || d || []
    // 账本默认跟随登录身份：优先我自己的账本，自己名下没账户再退到共同账本
    if (!bookType.value || !existingBooks.value.includes(bookType.value)) {
      const preferred = [myBook.value, 'shared', ...BOOK_ORDER]
      bookType.value =
        preferred.find((b) => visibleAccounts.value.some((a) => a.book_type === b)) ||
        (existingBooks.value[0] ?? 'shared')
    }
    // 「智能推荐」：默认选中该账本第一个账户，避免漏选导致流水没有归属账户
    const pool = visibleAccounts.value.length ? visibleAccounts.value : myAccounts.value
    if (pool.length && !accountId.value) {
      accountId.value = pool[0].id
    }
  } catch (e) {
    /* ignore */
  }
}

function onBook(type) {
  bookType.value = type
  accountId.value = visibleAccounts.value[0]?.id || ''
}

/** 快捷条/备注行里的短日期：今天直接显示「今天」 */
const shortDate = computed(() =>
  txDate.value === todayStr.value ? '今天' : dayjs(txDate.value).format('M月D日'),
)
/**
 * 日期框里显示的完整日期，对齐原生日期控件的「YYYY/MM/DD」写法。
 * 不再用「今天/昨天」这类相对词：日期框本身就该是确定值，
 * 相对描述留给下方提示条，避免同一处出现两种日期语言。
 */
const dateDisplay = computed(() => dayjs(txDate.value).format('YYYY/MM/DD'))
function onType(t) {
  activeType.value = t
  categoryId.value = ''
  loadCategories()
}

/** 编辑模式：把已有流水回填进表单（金额由分转回元） */
async function loadEditing() {
  const id = route.query.id
  if (!id) return
  editingId.value = String(id)
  try {
    const t = await ledgerApi.txDetail(id)
    if (!t) return
    activeType.value = t.type || 'expense'
    await loadCategories()
    categoryId.value = t.category_id || ''
    amount.value = String(yuan(t.amount_cents ?? 0))
    merchant.value = t.merchant || ''
    description.value = t.description || ''
    isPrivate.value = !!t.is_private
    txDate.value = (t.transaction_date || '').slice(0, 10) || todayStr.value
    // 账户：先等账户列表就位，再定位到该账户所属的账本
    await loadAccounts()
    const acc = accounts.value.find((a) => a.id === t.account_id)
    if (acc) {
      // 老账单若落在对方账本（现在已不可选），账本 chips 里不会有它，
      // 但编辑必须保留原归属，否则一保存就把账户/账本改掉了（见 bookChoices）
      bookType.value = acc.book_type
      accountId.value = acc.id
    }
  } catch (e) {
    toast(e.message || '加载账单失败')
  }
}
async function onSave() {
  const amt = Number(amount.value)
  if (!amt || amt <= 0) return toast('请输入金额')
  if (!categoryId.value) return toast('请选择分类')
  if (!accountId.value) return toast('请选择账户')
  saving.value = true
  try {
    const payload = {
      type: activeType.value,
      amount: String(amt),
      account: accountId.value || null,
      category: categoryId.value,
      merchant: merchant.value,
      description: description.value,
      transaction_date: txDateTime(),
      is_private: isPrivate.value && activeType.value === 'expense',
    }
    if (isEdit.value) {
      await ledgerApi.updateTx(editingId.value, payload)
      router.push({ path: '/', query: { notice: '已保存修改' } })
      return
    }
    const res = await ledgerApi.createTx(payload)
    const t = res.threshold || {}
    let msg = '已记账'
    if (t.action === 'notify') msg = '已记账，将通知对方'
    else if (t.action === 'approval') msg = '已记账，需对方审批'
    else if (t.action === 'joint') msg = '已记账，需共同决策'
    if (res.privacy && res.privacy.will_auto_public) msg = '已记账，超出隐私额度已计入共同支出'
    // 保存成功直接回首页（不弹窗），仅把额度/审批类提示带过去轻提示一下
    router.push({ path: '/', query: msg !== '已记账' ? { notice: msg } : {} })
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
onMounted(async () => {
  // 刷新后 store 里的成员信息是空的，先补齐才能按登录身份选账本
  if (!auth.member && auth.token) {
    try {
      await auth.fetchMe()
    } catch (e) {
      /* ignore */
    }
  }
  if (route.query.id) {
    await loadEditing()
  } else {
    loadCategories()
    await loadAccounts()
  }
})
</script>

<template>
  <div class="page add-form">
    <!-- 编辑态：给个明确出处，避免用户以为在记新账 -->
    <div v-if="isEdit" class="edit-bar">
      <span class="edit-tip">正在修改已记录的账单</span>
      <span class="edit-cancel" @click="router.push('/')">取消</span>
    </div>

    <!-- 顶部类型条：支出 / 收入 / 转账，选中为胶囊高亮；＋ 新增分类 -->
    <div class="type-bar">
      <div
        v-for="t in types"
        :key="t.key"
        class="type-pill"
        :class="{ active: activeType === t.key }"
        @click="onType(t.key)"
      >{{ t.label }}</div>
      <span class="bar-spacer"></span>
      <span class="bar-add" title="新增分类" @click="openAddCat">＋</span>
    </div>

    <!-- 分类网格：5 列大图标，参考常见记账 App 的宫格样式 -->
    <div class="category-grid">
      <div
        v-for="c in categories"
        :key="c.id"
        class="category-cell"
        :class="{ active: categoryId === c.id }"
        @click="categoryId = c.id"
      >
        <span class="cat-icon">{{ c.icon }}</span>
        <span class="cat-name">{{ c.name }}</span>
      </div>
    </div>

    <!-- 金额 · 日期：同一张卡，金额不再单独放大，与日期视觉权重一致 -->
    <div class="amount-note-card">
      <div class="an-main">
        <span class="an-label">金额</span>
        <div class="an-amount">
          <span class="amount-symbol">¥</span>
          <input v-model="amount" type="number" class="amount-input" placeholder="0.00" />
        </div>
        <span class="an-sep"></span>
        <!-- 日期胶囊：与账本/账户 chips 同一套样式，
             点一下仍走自绘日历，选中即生效，不额外加「确定」 -->
        <div class="an-date" :class="{ on: showDatePanel }" @click="openDatePanel">
          <span class="an-date-tx">{{ dateDisplay }}</span>
          <i class="an-date-ic"></i>
        </div>
      </div>
    </div>

    <!-- 备注：独立一栏，与金额卡拉开间距，下面挂该分类的历史记录 -->
    <div class="form-group note-group">
      <label class="form-label">备注</label>
      <input v-model="merchant" class="form-input" placeholder="添加备注..." />
      <div v-if="merchantHistory.length" class="history-row">
        <span
          v-for="h in merchantHistory"
          :key="h"
          class="history-chip"
          :class="{ on: merchant === h }"
          @click="merchant = h"
        >{{ h }}</span>
      </div>
    </div>

    <!-- 日历与表单同宽：原生面板宽度由浏览器控制，改不了，故自绘 -->
    <div v-if="showDatePanel" class="date-panel">
        <div class="dp-head">
          <span class="dp-nav" @click="shiftMonth(-1)">‹</span>
          <span class="dp-title">{{ viewTitle }}</span>
          <span class="dp-nav" :class="{ off: nextDisabled }" @click="shiftMonth(1)">›</span>
        </div>
        <div class="dp-week">
          <span v-for="w in WEEK" :key="w">{{ w }}</span>
        </div>
        <div class="dp-grid">
          <div
            v-for="d in calendarDays"
            :key="d.key"
            class="dp-cell"
            :class="{
              muted: d.muted,
              on: d.date === txDate,
              off: d.date > todayStr,
              today: d.date === todayStr,
            }"
            @click="pickDate(d)"
          >
            {{ d.day }}
          </div>
        </div>
        <div class="dp-foot">
          <span class="dp-btn" @click="showDatePanel = false">收起</span>
          <span class="dp-btn primary" @click="pickToday">回到今天</span>
        </div>
      </div>

    <!-- 账本：只展示「我的账本 + 共同账本」，对方专属账本不出现 -->
    <div class="quick-bar">
      <div
        v-for="b in bookChoices"
        :key="b"
        class="q-chip"
        :class="{ on: bookType === b }"
        @click="onBook(b)"
      >
        📒 {{ bookName(b) }}<span v-if="b === myBook" class="q-tag">我的</span>
      </div>
      <div class="q-chip" :class="{ on: isPrivate }" @click="isPrivate = !isPrivate">
        🙈 {{ isPrivate ? '不计入共同支出' : '计入共同支出' }}
      </div>
    </div>

    <!-- 账户：只列我名下的账户，横向 chips，选中高亮 -->
    <div class="account-bar">
      <div
        v-for="a in accountChoices"
        :key="a.id"
        class="q-chip acct"
        :class="{ on: accountId === a.id }"
        @click="accountId = a.id"
      >
        {{ a.icon }} {{ a.name }}
      </div>
      <div v-if="!accountChoices.length" class="q-chip">💳 这本账下还没有你的账户</div>
    </div>

    <!-- 按钮 -->
    <div class="form-actions">
      <button class="btn btn-primary btn-full" :disabled="saving" @click="onSave">
        {{ isEdit ? '保存修改' : '保存' }}
      </button>
      <button class="btn btn-secondary btn-full" @click="router.push('/')">取消</button>
    </div>

    <!-- 新增分类：底部弹层，与项目其它弹层风格一致 -->
    <div v-if="showAddCat" class="sheet-mask" @click.self="showAddCat = false">
      <div class="sheet">
        <div class="sheet-head">
          <span class="sheet-title">新增分类</span>
          <span class="sheet-close" @click="showAddCat = false">✕</span>
        </div>
        <div class="sheet-body">
          <label class="form-label">图标</label>
          <div class="icon-picker">
            <span
              v-for="ic in CAT_ICONS"
              :key="ic"
              class="icon-opt"
              :class="{ on: newCat.icon === ic }"
              @click="newCat.icon = ic"
            >{{ ic }}</span>
          </div>
          <label class="form-label cat-label">名称</label>
          <input
            v-model="newCat.name"
            class="form-input"
            maxlength="10"
            placeholder="如：宠物、健身、车位"
            @keyup.enter="submitCat"
          />
          <div class="cat-hint">
            将归到「{{ activeType === 'income' ? '收入' : '支出' }}」分类下，新增后所有家庭成员都能用
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary btn-full" :disabled="catSaving" @click="submitCat">
            {{ catSaving ? '保存中…' : '保存' }}
          </button>
          <button class="btn btn-secondary btn-full" @click="showAddCat = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.add-form {
  padding: 16px;
  padding-bottom: 80px;
}
.form-group {
  margin-bottom: 16px;
}
.form-label {
  font-size: 12px;
  color: #888780;
  margin-bottom: 6px;
  display: block;
}
.form-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.add-cat-btn {
  font-size: 12px;
  color: #7f77dd;
  cursor: pointer;
}
/* 备注 · 日期 · 金额 同卡一行：一眼能看到记的是什么、哪天、多少 */
.amount-note-card {
  background: #fff;
  border: 0.5px solid #d3d1c7;
  border-radius: 12px;
  padding: 10px 12px;
}
.an-main {
  display: flex;
  align-items: center;
  gap: 10px;
}
.an-label {
  flex: none;
  font-size: 13px;
  color: #5f5e5a;
}
/* 金额与日期同一视觉层级：都不做背景高亮，避免金额过分突出 */
.an-sep {
  flex: none;
  width: 1px;
  height: 18px;
  background: #e8e6dc;
}
/* 备注栏与金额卡之间多留一拍，避免两块白卡贴在一起 */
.note-group {
  margin-top: 20px;
}
/* 备注历史：同一分类下最近用过的备注，点一下直接填入 */
.history-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.history-chip {
  padding: 5px 10px;
  border: 0.5px solid #d3d1c7;
  border-radius: 999px;
  background: #faf9f5;
  font-size: 12px;
  color: #5f5e5a;
  cursor: pointer;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-chip.on {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #534ab7;
}
/*
 * 日期胶囊：与页内账本 / 账户 chips 同一套语言（浅灰底 + 全圆角 + 深灰字），
 * 不再做成「白底细边输入框」——那种方框浮在圆角卡片里像原生控件，很跳。
 */
.an-date {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  border-radius: 999px;
  background: #f1efe8;
  font-size: 13px;
  color: #2c2c2a;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
/* 日期数字等宽，切换日期时胶囊宽度不跳动 */
.an-date-tx {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
/* 日历图标：纯 CSS 画的实心小方块，比字符图标清楚，也不引图标库 */
.an-date-ic {
  flex: none;
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border-radius: 2px;
  border: 1.5px solid #888780;
  /* 顶部加粗画出「日历头」，一眼能认出是日历 */
  border-top-width: 4px;
}
/* 展开态：整颗变浅紫 + 主色字，与 chips 的选中态一致 */
.an-date.on {
  background: #eeedfe;
  color: #534ab7;
  font-weight: 600;
}
.an-date.on .an-date-ic {
  border-color: #7f77dd;
}
.an-amount {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 2px;
}
/* 金额不再单独放大加粗：与日期同一视觉层级，避免抢走分类区的注意力 */
.amount-symbol {
  font-size: 18px;
  font-weight: 500;
  color: #2c2c2a;
}
.amount-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  font-size: 18px;
  font-weight: 500;
  color: #2c2c2a;
  padding: 6px 4px;
}
/* 编辑态提示条 */
.edit-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 10px;
  border-radius: 10px;
  background: #eeedfe;
}
.edit-tip {
  font-size: 12px;
  color: #534ab7;
  font-weight: 600;
}
.edit-cancel {
  font-size: 12px;
  color: #888780;
  cursor: pointer;
}
/* 顶部类型条：文字胶囊，选中实色，右侧 ＋ 新增分类 */
.type-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 0 10px;
  overflow-x: auto;
}
.type-pill {
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 14px;
  color: #5f5e5a;
  white-space: nowrap;
  cursor: pointer;
}
.type-pill.active {
  background: #534ab7;
  color: #fff;
  font-weight: 600;
}
.bar-spacer {
  flex: 1;
}
.bar-add {
  flex: none;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #534ab7;
  font-size: 18px;
  cursor: pointer;
  background: #eeedfe;
}
/* 自绘日历：宽度跟随表单，与上方输入框完全对齐 */
.date-panel {
  margin-top: 6px;
  padding: 10px 12px 8px;
  background: #fff;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
}
.dp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 8px;
  font-size: 14px;
  font-weight: 600;
  color: #2c2c2a;
}
.dp-nav {
  width: 28px;
  height: 28px;
  line-height: 26px;
  text-align: center;
  border-radius: 6px;
  background: #eeedfe;
  color: #534ab7;
  font-size: 16px;
  cursor: pointer;
}
.dp-nav.off {
  background: #f1efe9;
  color: #cfcdc4;
  cursor: default;
}
.dp-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  padding-bottom: 4px;
  text-align: center;
  font-size: 11px;
  color: #b4b2a9;
}
.dp-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px 0;
}
.dp-cell {
  height: 34px;
  line-height: 34px;
  text-align: center;
  border-radius: 6px;
  font-size: 13px;
  color: #2c2c2a;
  cursor: pointer;
}
.dp-cell.muted {
  color: #cfcdc4;
}
.dp-cell.off {
  color: #e4e2da;
  cursor: default;
}
.dp-cell.today {
  box-shadow: inset 0 0 0 1px #d3d1c7;
}
.dp-cell.on {
  background: #534ab7;
  color: #fff;
  font-weight: 600;
  box-shadow: none;
}
.dp-foot {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 0.5px solid #f0eee6;
}
.dp-btn {
  font-size: 13px;
  color: #888780;
  cursor: pointer;
}
.dp-btn.primary {
  color: #534ab7;
  font-weight: 600;
}
/* 分类宫格：5 列大图标，选中浅紫底 */
.category-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  padding-bottom: 4px;
}
.category-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 2px 8px;
  background: #fff;
  border: 0.5px solid transparent;
  border-radius: 12px;
  cursor: pointer;
}
.cat-icon {
  font-size: 26px;
  line-height: 1;
}
.cat-name {
  font-size: 11px;
  color: #2c2c2a;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.category-cell.active {
  background: #eeedfe;
  border-color: #7f77dd;
}
.category-cell.active .cat-name {
  color: #534ab7;
  font-weight: 600;
}
/* ---------------- 新增分类弹层 */
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
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 16px 16px 24px;
  max-height: 80vh;
  overflow-y: auto;
}
.sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 16px;
  font-weight: 600;
  color: #2c2c2a;
}
.sheet-close {
  color: #b4b2a9;
  cursor: pointer;
  padding: 0 4px;
}
.icon-picker {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 6px;
}
.icon-opt {
  height: 34px;
  line-height: 34px;
  text-align: center;
  border-radius: 8px;
  background: #f7f6f2;
  font-size: 18px;
  cursor: pointer;
}
.icon-opt.on {
  background: #eeedfe;
  box-shadow: inset 0 0 0 1px #7f77dd;
}
.cat-label {
  margin-top: 12px;
}
.cat-hint {
  font-size: 12px;
  color: #888780;
  margin-top: 10px;
  line-height: 1.5;
}
.form-input {
  width: 100%;
  padding: 14px;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  font-size: 14px;
  background: #fafbfc;
}
/* 快捷条与账户条：白色小 chips，横向滚动，选中浅紫 */
.quick-bar,
.account-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 2px 0;
}
.q-chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  background: #fff;
  font-size: 12px;
  color: #2c2c2a;
  cursor: pointer;
  white-space: nowrap;
}
.q-chip.on {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #534ab7;
  font-weight: 600;
}
.q-chip .q-tag {
  margin-left: 2px;
  font-size: 10px;
  color: #1d9e75;
}
.form-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.btn-secondary {
  background: #f1efe8;
  color: #5f5e5a;
}
</style>