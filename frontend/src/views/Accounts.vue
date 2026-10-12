<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { accountApi, familyApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import AccountEditSheet from '@/components/AccountEditSheet.vue'
import { toast } from '@/utils/toast'

const router = useRouter()
const auth = useAuthStore()
const data = ref(null)
const loading = ref(true)

// 编辑 / 新建账户
const showEdit = ref(false)
const editTarget = ref(null)
const defaultBook = ref('shared')

// 收益概览：只在入口行显示一句「累计/今年收益」，详情进收益管理页
const ret = ref(null)

// 修改账本名称
const showRename = ref(false)
const renameBookType = ref('shared')
const renameLabel = ref('')
const savingRename = ref(false)

const BOOK_ICON = { shared: '👨‍👩‍👧', husband: '🧑', wife: '👩' }

// —— 主账号转让统一在家庭管理页操作，这里只标记「哪个账本属于主账号」——
const fam = ref(null)

// 一个账本下可能挂多位成员（上限 5 人、账本只有 3 类），按「组内有无主账号」判断
function isOwnerBook(bookType) {
  return (fam.value?.members || []).some(
    (m) => m.book_type === bookType && m.role === 'owner',
  )
}

async function loadFamily() {
  try {
    fam.value = await familyApi.me()
  } catch (e) {
    fam.value = null
  }
}

const groups = computed(() => (data.value?.groups || []).filter((g) => g.accounts.length))
const totalAssets = computed(() => Number(data.value?.total_assets || 0))
const changeText = computed(() => {
  const c = Number(data.value?.asset_change_cents || 0) / 100
  if (!c) return ''
  const sign = c > 0 ? '+' : '-'
  return `${sign}¥${money(Math.abs(c))}`
})
const accountCount = computed(() => data.value?.account_count || 0)
// 净资产口径：账户余额 + 借出未收 − 借入未还
const accountAssets = computed(() =>
  Number(data.value?.account_assets_cents ?? data.value?.total_assets_cents ?? 0),
)
const receivable = computed(() => Number(data.value?.receivable_cents || 0))
const payable = computed(() => Number(data.value?.payable_cents || 0))
const loanSum = computed(() => data.value?.loans || null)

// 整数不补 .00，保留千分位（与设计稿 ¥180,000 一致）
function money(v) {
  const n = Number(v || 0)
  const s = n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return s.endsWith('.00') ? s.slice(0, -3) : s
}

async function load() {
  loading.value = true
  try {
    data.value = await accountApi.netvalue()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadReturns() {
  try {
    ret.value = await accountApi.returns()
  } catch (e) {
    ret.value = null
  }
}

// 收益概览的带符号金额：分 → 元
function signed(cents) {
  const c = Number(cents || 0)
  const sign = c > 0 ? '+' : c < 0 ? '-' : ''
  return `${sign}¥${money(Math.abs(c) / 100)}`
}
function retCls(cents) {
  const c = Number(cents || 0)
  return c > 0 ? 'up' : c < 0 ? 'down' : ''
}

function openCreate(bookType) {
  editTarget.value = null
  // 未指定账本时默认建在「我的账本」里，与记账页的默认账本保持一致
  defaultBook.value = bookType || auth.member?.book_type || 'shared'
  showEdit.value = true
}
function openEdit(account) {
  editTarget.value = account
  showEdit.value = true
}
function openRename(bookType, label) {
  renameBookType.value = bookType
  renameLabel.value = label
  showRename.value = true
}
async function saveRename() {
  const label = renameLabel.value.trim()
  if (!label) return toast('请输入账本名称')
  savingRename.value = true
  try {
    await accountApi.renameBook({ book_type: renameBookType.value, label })
    showRename.value = false
    await load()
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    savingRename.value = false
  }
}

function onSaved() {
  load()
  loadReturns()
}

onMounted(() => {
  load()
  loadFamily()
  loadReturns()
})
</script>

<template>
  <div class="acc-page">
    <!-- 顶部栏 -->
    <div class="top-bar">
      <span class="top-title">👛 账户管理</span>
      <span class="top-close" @click="router.push('/mine')">×</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <template v-else>
      <!-- 家庭净资产 -->
      <div class="net-card">
        <div class="net-top">
          <span class="net-label">🏦 家庭净资产</span>
          <span v-if="changeText" class="net-change">{{ changeText }}</span>
        </div>
        <div class="net-value">¥{{ money(totalAssets) }}</div>
        <div class="net-sub">
          {{ accountCount }} 个账户 ¥{{ money(accountAssets) }}
          <template v-if="receivable"> ＋ 借出未收 ¥{{ money(receivable) }}</template>
          <template v-if="payable"> － 借入未还 ¥{{ money(payable) }}</template>
        </div>
      </div>

      <!-- 借钱来往：应收算资产，应付算负债 -->
      <div v-if="loanSum" class="loan-line" @click="router.push('/loans')">
        <span class="ll-ic">🤝</span>
        <div class="ll-main">
          <div class="ll-title">借钱来往</div>
          <div class="ll-sub">
            <span v-if="loanSum.lend_cents" class="ll-lend"
              >借出未收 ¥{{ money(loanSum.lend_cents) }}（{{ loanSum.lend_count }} 笔）</span
            >
            <span v-if="loanSum.borrow_cents" class="ll-borrow"
              >借入未还 ¥{{ money(loanSum.borrow_cents) }}（{{ loanSum.borrow_count }} 笔）</span
            >
            <span v-if="!loanSum.lend_cents && !loanSum.borrow_cents">暂无未结清的借贷</span>
            <span v-if="loanSum.overdue_count" class="ll-od"
              >· {{ loanSum.overdue_count }} 笔已过约定日</span
            >
          </div>
        </div>
        <span class="ll-arrow">›</span>
      </div>

      <!-- 收益管理：一年收益变化 + 今年收益对净资产的影响 -->
      <div class="loan-line" @click="router.push('/returns')">
        <span class="ll-ic ret-ic">📈</span>
        <div class="ll-main">
          <div class="ll-title">收益管理</div>
          <div class="ll-sub">
            <template v-if="ret?.has_invest">
              <span :class="retCls(ret.profit_cents)">累计 {{ signed(ret.profit_cents) }}</span>
              <span :class="retCls(ret.year_profit_cents)">今年 {{ signed(ret.year_profit_cents) }}</span>
            </template>
            <span v-else>一年收益变化 · 今年收益对总资产的影响</span>
          </div>
        </div>
        <span class="ll-arrow">›</span>
      </div>

      <!-- 按账本分组 -->
      <div v-for="g in groups" :key="g.book_type" class="book-group">
        <div class="book-head">
          <span class="book-title-wrap">
            <span class="book-title" @click="openRename(g.book_type, g.label)">
              {{ BOOK_ICON[g.book_type] || '📁' }} {{ g.label }}
            </span>
            <span v-if="isOwnerBook(g.book_type)" class="role-tag">主账号</span>
          </span>
          <span class="book-add" @click="openCreate(g.book_type)">+</span>
        </div>

        <div v-for="a in g.accounts" :key="a.id" class="acc-card" @click="openEdit(a)">
          <span class="acc-ic">{{ a.icon }}</span>
          <div class="acc-main">
            <div class="acc-name">{{ a.name }}</div>
            <div class="acc-sub">
              {{ g.label }} · {{ a.card_type_display }}
              <em v-if="a.visibility === 'self'" class="lock">🔒</em>
            </div>
          </div>
          <span class="acc-bal">¥{{ money(a.balance) }}</span>
        </div>
      </div>

      <div v-if="!groups.length" class="empty">还没有账户，点下方按钮新建一个</div>
    </template>

    <!-- 新建按钮放在内容末尾（不悬浮），避免遮挡底部 TabBar -->
    <div class="bottom-bar">
      <button class="btn btn-primary" @click="openCreate('shared')">+ 新建账户</button>
    </div>

    <!-- 编辑 / 新建账户 -->
    <AccountEditSheet
      :visible="showEdit"
      :account="editTarget"
      :default-book="defaultBook"
      @close="showEdit = false"
      @saved="onSaved"
    />

    <!-- 修改账本名称 -->
    <div v-if="showRename" class="sheet-mask" @click="showRename = false">
      <div class="sheet" @click.stop>
        <div class="rename-head">
          <span class="rename-title">修改账本名称</span>
          <span class="rename-close" @click="showRename = false">×</span>
        </div>
        <label class="rename-label">账本名称</label>
        <input v-model="renameLabel" class="rename-input" maxlength="20" placeholder="如：共同账户" />
        <button class="btn btn-primary" :disabled="savingRename" @click="saveRename">
          {{ savingRename ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* ★ 与全局 .page 同一套底部留白：内容永远不会被底部 TabBar 盖住 */
.acc-page {
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
.net-card {
  margin: 0 16px 20px;
  padding: 16px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 14px;
}
.net-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.net-label {
  font-size: 13px;
  color: #5f5e5a;
}
.net-change {
  font-size: 12px;
  font-weight: 600;
  color: #1d9e75;
}
.net-value {
  font-size: 30px;
  font-weight: 700;
  color: #1d9e75;
  margin: 6px 0 4px;
  font-variant-numeric: tabular-nums;
}
.net-sub {
  font-size: 11px;
  color: #b8b6ae;
  line-height: 1.6;
}
/* 借钱来往：应收/应付单独一行，点击进台账 */
.loan-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 16px 18px;
  padding: 12px 14px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  cursor: pointer;
}
.ll-ic {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: #eeedfe;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex: none;
}
.ll-main {
  flex: 1;
  min-width: 0;
}
.ll-title {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
}
.ll-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
  font-size: 11px;
  color: #888780;
}
.ll-lend {
  color: #1d9e75;
}
.ll-borrow {
  color: #ba7517;
}
.ll-od {
  color: #d03b3b;
  font-weight: 600;
}
.ll-arrow {
  color: #c8c6c0;
  font-size: 18px;
  line-height: 1;
}
/* 收益管理入口 */
.ret-ic {
  background: #e6f4ee;
}
.up {
  color: #1d9e75;
}
.down {
  color: #d03b3b;
}
.book-group {
  margin: 0 16px 18px;
}
.book-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 2px 10px;
}
.book-title {
  font-size: 14px;
  font-weight: 600;
  color: #444441;
  cursor: pointer;
}
.book-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
/* 该账本归属者已是主账号 */
.role-tag {
  flex: none;
  font-size: 11px;
  font-weight: 500;
  color: #534ab7;
  background: #eeedfe;
  padding: 1px 7px;
  border-radius: 999px;
  white-space: nowrap;
}
.book-add {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #7f77dd;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.acc-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  padding: 14px 14px;
  margin-bottom: 10px;
  cursor: pointer;
}
.acc-card:active {
  background: #faf9f6;
}
.acc-ic {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 10px;
  background: #f4f3fb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
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
.acc-sub {
  font-size: 11px;
  color: #b8b6ae;
  margin-top: 3px;
}
.lock {
  font-style: normal;
  margin-left: 4px;
}
.acc-bal {
  font-size: 15px;
  font-weight: 700;
  color: #1d9e75;
  font-variant-numeric: tabular-nums;
  flex: none;
}
.bottom-bar {
  margin: 4px 16px 0;
}
.empty {
  text-align: center;
  color: #b8b6ae;
  font-size: 13px;
  padding: 40px 0;
}
.rename-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.rename-title {
  font-size: 17px;
  font-weight: 600;
  color: #26215c;
}
.rename-close {
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
.rename-label {
  display: block;
  font-size: 12px;
  color: #888780;
  margin-bottom: 8px;
}
.rename-input {
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
.rename-input:focus {
  border-color: #ef9f27;
  box-shadow: 0 0 0 2px rgba(239, 159, 39, 0.15);
}
</style>
