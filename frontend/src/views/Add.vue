<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ledgerApi, accountApi } from '@/api'
import dayjs from 'dayjs'
import { toast } from '@/utils/toast'

const router = useRouter()
const types = [
  { key: 'expense', label: '支出' },
  { key: 'income', label: '收入' },
  { key: 'transfer', label: '转账' },
]
const activeType = ref('expense')
const categories = ref([])
const accounts = ref([])
const categoryId = ref('')
const accountId = ref('')
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

// ---------------- 语音输入（备注）
// 国内 Chrome 走 Google 语音服务常常不可用，所以必须先探测能力，
// 不支持就明确提示，而不是点了没反应
const speechOK = !!(
  typeof window !== 'undefined' &&
  (window.SpeechRecognition || window.webkitSpeechRecognition)
)
const listening = ref(false) // 备注语音是否正在听
let recognizer = null

function startVoice() {
  if (!speechOK) return toast('当前浏览器不支持语音输入，请手动输入')
  if (listening.value) {
    // 录音中再点一次 = 停止
    if (recognizer) recognizer.stop()
    listening.value = false
    return
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  recognizer = new SR()
  recognizer.lang = 'zh-CN'
  recognizer.interimResults = false
  recognizer.maxAlternatives = 1
  listening.value = true
  recognizer.onresult = (e) => {
    const text = (e.results?.[0]?.[0]?.transcript || '').trim()
    if (!text) return
    merchant.value = merchant.value ? `${merchant.value} ${text}` : text
    toast('已填入备注')
  }
  recognizer.onerror = (e) => {
    listening.value = false
    const map = {
      'not-allowed': '没有麦克风权限，请在浏览器设置里允许',
      'service-not-allowed': '语音服务不可用，请手动输入',
      'no-speech': '没听到声音，请再说一次',
    }
    toast(map[e.error] || '语音识别失败，请重试')
  }
  recognizer.onend = () => {
    listening.value = false
  }
  try {
    recognizer.start()
  } catch (e) {
    listening.value = false
    toast('语音启动失败，请重试')
  }
}

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
}
async function loadAccounts() {
  try {
    const d = await accountApi.list()
    accounts.value = d.items || d || []
    // 「智能推荐」：默认选中第一个账户，避免漏选导致流水没有归属账户
    if (accounts.value.length && !accountId.value) {
      accountId.value = accounts.value[0].id
    }
  } catch (e) {
    /* ignore */
  }
}
function onType(t) {
  activeType.value = t
  categoryId.value = ''
  loadCategories()
}
async function onSave() {
  const amt = Number(amount.value)
  if (!amt || amt <= 0) return toast('请输入金额')
  if (!categoryId.value) return toast('请选择分类')
  if (!accountId.value) return toast('请选择账户')
  saving.value = true
  try {
    const res = await ledgerApi.createTx({
      type: activeType.value,
      amount: String(amt),
      account: accountId.value || null,
      category: categoryId.value,
      merchant: merchant.value,
      description: description.value,
      transaction_date: txDateTime(),
      is_private: isPrivate.value && activeType.value === 'expense',
    })
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
onMounted(() => {
  loadCategories()
  loadAccounts()
})
</script>

<template>
  <div class="page add-form">
    <!-- 金额 -->
    <div class="form-group">
      <label class="form-label">金额</label>
      <div class="amount-row">
        <span class="amount-symbol">¥</span>
        <input v-model="amount" type="number" class="amount-input" placeholder="0.00" />
      </div>
    </div>

    <!-- 类型 -->
    <div class="form-group">
      <label class="form-label">类型</label>
      <div class="type-selector">
        <div
          v-for="t in types"
          :key="t.key"
          class="type-btn"
          :class="{ active: activeType === t.key }"
          @click="onType(t.key)"
        >{{ t.label }}</div>
      </div>
    </div>

    <!-- 日期 -->
    <div class="form-group">
      <label class="form-label">日期</label>
      <div class="date-picker-row" @click="openDatePanel">
        <span>📅 {{ dateLabel }}</span>
        <span class="date-arrow" :class="{ on: showDatePanel }">›</span>
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
    </div>

    <!-- 分类 -->
    <div class="form-group">
      <div class="form-label-row">
        <label class="form-label">分类</label>
        <span class="add-cat-btn" @click="openAddCat">＋ 新增</span>
      </div>
      <div class="category-grid">
        <div
          v-for="c in categories"
          :key="c.id"
          class="category-chip"
          :class="{ active: categoryId === c.id }"
          @click="categoryId = c.id"
        >
          <span class="icon">{{ c.icon }}</span>
          {{ c.name }}
        </div>
      </div>
    </div>

    <!-- 备注 -->
    <div class="form-group">
      <label class="form-label">备注 支持语音</label>
      <div class="note-row">
        <input v-model="merchant" class="form-input" placeholder="添加备注..." />
        <button
          type="button"
          class="voice-btn-sm"
          :class="{ on: listening }"
          :title="speechOK ? '语音输入备注' : '当前浏览器不支持语音输入'"
          @click="startVoice()"
        >{{ listening ? '■' : '🎤' }}</button>
      </div>
    </div>

    <!-- 账户 -->
    <div class="form-group">
      <label class="form-label">账户 智能推荐</label>
      <div class="quick-account">
        <div
          v-for="a in accounts"
          :key="a.id"
          class="quick-account-btn"
          :class="{ active: accountId === a.id, recommended: accountId === a.id }"
          @click="accountId = a.id"
        >
          <span class="icon">{{ a.icon }}</span>{{ a.name }}
        </div>
        <div v-if="!accounts.length" class="quick-account-btn">💳 未设置账户</div>
      </div>
    </div>


    <!-- 私密消费 -->
    <div class="form-group">
      <div class="toggle-row">
        <div>
          <div class="toggle-label">私密消费</div>
          <div class="toggle-sub">不计入共同支出</div>
        </div>
        <div class="toggle" :class="{ active: isPrivate }" @click="isPrivate = !isPrivate"></div>
      </div>
    </div>

    <!-- 按钮 -->
    <div class="form-actions">
      <button class="btn btn-primary btn-full" :disabled="saving" @click="onSave">保存</button>
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
.amount-row {
  display: flex;
  align-items: center;
  background: #fff;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  padding: 8px 14px;
}
.amount-symbol {
  font-size: 24px;
  font-weight: 600;
  color: #26215c;
}
.amount-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 24px;
  font-weight: 600;
  color: #26215c;
  padding: 6px 10px;
}
.type-selector {
  display: flex;
  gap: 8px;
}
.type-btn {
  flex: 1;
  padding: 12px;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  background: #fff;
  text-align: center;
  cursor: pointer;
  font-size: 13px;
}
.type-btn.active {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #7f77dd;
}
.date-picker-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  padding: 14px;
  font-size: 14px;
  color: #2c2c2a;
  cursor: pointer;
}
.date-arrow {
  display: inline-block;
  color: #b4b2a9;
  margin-left: 2px;
  transition: transform 0.15s ease;
}
.date-arrow.on {
  transform: rotate(90deg);
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
.category-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.category-chip {
  padding: 10px 8px;
  border: 0.5px solid #e8e8e8;
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  font-size: 11px;
  background: #fff;
}
.category-chip.active {
  background: #7f77dd;
  color: #fff;
  border-color: #7f77dd;
}
.category-chip .icon {
  font-size: 18px;
  display: block;
  margin-bottom: 4px;
}
.note-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.note-row .form-input {
  flex: 1;
}
/* ★ 原类名写成 .note-btn-sm，与模板里的 voice-btn-sm 对不上，
   导致备注旁的语音键一直没有样式（白底灰边），顺手修正 */
.voice-btn-sm {
  border: none;
  background: #eeedfe;
  color: #7f77dd;
  border-radius: 8px;
  width: 40px;
  height: 40px;
  flex: none;
  font-size: 18px;
  cursor: pointer;
}
/* 录音中：变红 + 图标换成 ■，让用户知道「真的在听」 */
.voice-btn-sm.on {
  background: #fde8e8;
  color: #d34b4b;
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
.quick-account {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.quick-account-btn {
  padding: 8px 12px;
  border: 0.5px solid #d3d1c7;
  border-radius: 20px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.quick-account-btn.active {
  background: #7f77dd;
  color: #fff;
  border-color: #7f77dd;
}
/* ★ 智能推荐 = 默认选中，二者类名同时存在：
   用 .active.recommended 提高优先级，避免只覆盖背景而文字仍是白色导致看不清 */
.quick-account-btn.active.recommended {
  background: #d6f0e6;
  color: #0b5c43;
  border-color: #1d9e75;
  font-weight: 500;
}
.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  background: #fff;
  border-radius: 8px;
  padding: 14px;
}
.toggle-label {
  font-size: 14px;
  font-weight: 500;
}
.toggle-sub {
  font-size: 12px;
  color: #888780;
  margin-top: 2px;
}
.toggle {
  width: 44px;
  height: 24px;
  background: #d3d1c7;
  border-radius: 12px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
}
.toggle.active {
  background: #1d9e75;
}
.toggle::after {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: left 0.2s;
}
.toggle.active::after {
  left: 22px;
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