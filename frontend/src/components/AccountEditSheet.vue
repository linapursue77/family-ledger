<script setup>
import { ref, computed, reactive, watch } from 'vue'
import { accountApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { toast } from '@/utils/toast'

const auth = useAuthStore()

const props = defineProps({
  visible: Boolean,
  // null = 新建
  account: { type: Object, default: null },
  defaultBook: { type: String, default: 'shared' },
})
const emit = defineEmits(['close', 'saved'])

const CARD_OPTIONS = [
  { value: 'debit', label: '储蓄卡', icon: '🏦' },
  { value: 'credit', label: '信用卡', icon: '💳' },
  { value: 'cash', label: '现金', icon: '💵' },
  { value: 'wallet', label: '数字钱包', icon: '📱' },
  { value: 'invest', label: '投资理财', icon: '📈' },
]
const BOOK_OPTIONS = [
  { value: 'shared', label: '共同', icon: '👨‍👩‍👧' },
  { value: 'husband', label: '账本一', icon: '🧑' },
  { value: 'wife', label: '账本二', icon: '👤' },
]
// ★ 家庭在「账户管理」里改过账本名后，这里必须跟着显示新名，否则选错账本
const bookOptions = computed(() =>
  BOOK_OPTIONS.map((b) => ({ ...b, label: auth.family?.book_labels?.[b.value] || b.label })),
)

const name = ref('')
const cardType = ref('debit')
const bookType = ref('shared')
const visibility = ref('shared')
const balance = ref('')
// 收益管理：勾选后可录入「收益总额」，本金 = 当前金额 − 收益
const isInvest = ref(false)
// 收益可以是负数（亏损），但手机数字键盘没有负号键，
// 所以拆成「盈亏开关 + 只填数字」：开关决定正负，输入框只留绝对值
const profitSign = ref(1)
const profitInput = ref('')
const saving = ref(false)
let originalCardType = 'debit'

// 自绘确认弹层：window.confirm 在预览环境会被吞掉，删除会显得「点了没反应」
const confirmState = reactive({ show: false, title: '', lines: [], okText: '确认' })
let confirmResolve = null

function ask({ title, lines = [], okText = '确认' }) {
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

const isEdit = computed(() => !!props.account)
const title = computed(() => (isEdit.value ? '编辑账户' : '新建账户'))

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    const a = props.account
    name.value = a?.name || ''
    cardType.value = a?.card_type || 'debit'
    originalCardType = cardType.value
    bookType.value = a?.book_type || props.defaultBook || 'shared'
    visibility.value = a?.visibility || 'shared'
    balance.value = a ? String((Number(a.balance_cents) || 0) / 100) : ''
    isInvest.value = !!a?.is_invest
    // 回填收益：收益 = 现值 − 本金（本金未录过则留空，收益从 0 起算）
    // 注意方向别写反：存的是本金、显示的是收益，反了会让每次编辑把收益变号
    const profit =
      a && a.is_invest && Number(a.principal_cents) > 0
        ? (Number(a.balance_cents) - Number(a.principal_cents)) / 100
        : 0
    // 亏了的话回填成负数，并把开关切到「亏损」，用户一眼能看出是亏
    profitSign.value = profit < 0 ? -1 : 1
    profitInput.value = Math.abs(profit) > 0.001 ? String(Math.abs(profit)) : ''
  }
)

// 直接敲负号（桌面端输入法有）时也认，落到的还是同一个开关，不会丢
function onProfitInput(e) {
  let v = String(e.target.value ?? '').trim()
  if (v.startsWith('-')) {
    profitSign.value = -1
    v = v.slice(1)
  } else if (v.startsWith('+')) {
    v = v.slice(1)
  }
  v = v.replace(/[^\d.]/g, '')
  profitInput.value = v
  // 只填了非法字符时过滤结果没变化，v-model 不会回写，这里手动刷掉
  e.target.value = v
}

// 介质选「投资理财」默认纳入收益管理，少一步操作
watch(cardType, (v) => {
  if (v === 'invest') isInvest.value = true
})

function cardIcon(value) {
  return CARD_OPTIONS.find((c) => c.value === value)?.icon || '💰'
}

async function onSave() {
  if (!name.value.trim()) return toast('请输入账户名称')
  saving.value = true
  try {
    const icon = cardIcon(cardType.value)
    const base = {
      name: name.value.trim(),
      type: visibility.value === 'self' ? 'private' : 'personal',
      card_type: cardType.value,
      book_type: bookType.value,
      is_invest: isInvest.value,
    }
    // 用户填的是「收益总额」，后端存的是本金：本金 = 当前金额 − 收益。
    // 收益留空时本金 = 当前金额，收益从 0 开始。
    if (isInvest.value) {
      const bal = Number(balance.value || 0)
      // profitInput 存的是绝对值，正负由 profitSign 决定
      const pf = profitInput.value === '' ? 0 : profitSign.value * Math.abs(Number(profitInput.value))
      if (!Number.isFinite(pf)) return toast('收益金额不正确')
      const principalVal = bal - pf
      if (principalVal < 0) return toast('收益不能大于当前金额')
      base.principal = principalVal.toFixed(2)
    }
    if (isEdit.value) {
      const payload = { ...base }
      // 只有介质变了才同步图标，避免覆盖账户原有图标
      if (cardType.value !== originalCardType) payload.icon = icon
      await accountApi.update(props.account.id, payload)

      const target = Number(balance.value || 0)
      const current = (Number(props.account.balance_cents) || 0) / 100
      if (Math.abs(target - current) > 0.001) {
        await accountApi.adjust(props.account.id, {
          balance: target.toFixed(2),
          reason: '编辑账户时同步余额',
        })
      }
    } else {
      await accountApi.create({ ...base, icon, balance: Number(balance.value || 0).toFixed(2) })
    }
    // 保存成功：先关弹窗再通知刷新，避免父组件刷新时把弹窗又带出来
    emit('close')
    toast('已保存')
    emit('saved')
  } catch (e) {
    toast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  const ok = await ask({
    title: `删除「${props.account?.name}」？`,
    lines: ['该账户及其余额将被移除，删除后不可恢复', '已记的账单不受影响'],
    okText: '删除',
  })
  if (!ok) return
  saving.value = true
  try {
    // 余额不为 0 时后端会拒绝删除；这里代劳「先清零」，
    // 走 adjust 留调整日志，资金去向可追溯
    const bal = Number(balance.value || 0)
    if (Math.abs(bal) > 0.001) {
      const ok2 = await ask({
        title: '账户余额不为 0',
        lines: [`当前余额 ¥${bal.toFixed(2)}`, '删除前会自动把余额清零并记录调整日志'],
        okText: '清零并删除',
      })
      if (!ok2) return
      await accountApi.adjust(props.account.id, {
        balance: '0',
        reason: '删除账户前清零余额',
      })
    }
    await accountApi.remove(props.account.id)
    emit('saved')
    emit('close')
  } catch (e) {
    toast(e.message || '删除失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="visible" class="sheet-mask" @click="emit('close')">
    <div class="sheet acc-sheet" @click.stop>
      <div class="acc-head">
        <span class="acc-title">{{ title }}</span>
        <span class="acc-close" @click="emit('close')">×</span>
      </div>

      <div class="acc-body">
        <div class="fld">
          <label class="fld-label">账户名称</label>
          <input v-model="name" class="fld-input" placeholder="如：建设银行卡（共同）" maxlength="50" />
        </div>

        <div class="fld">
          <label class="fld-label">账户类型</label>
          <div class="chip-row">
            <div
              v-for="c in CARD_OPTIONS"
              :key="c.value"
              class="chip"
              :class="{ on: cardType === c.value }"
              @click="cardType = c.value"
            >
              <span class="chip-ic">{{ c.icon }}</span>
              <span class="chip-tx">{{ c.label }}</span>
            </div>
          </div>
        </div>

        <div class="fld">
          <label class="fld-label">账户归属</label>
          <div class="chip-row">
            <div
              v-for="b in bookOptions"
              :key="b.value"
              class="chip"
              :class="{ on: bookType === b.value }"
              @click="bookType = b.value"
            >
              <span class="chip-ic">{{ b.icon }}</span>
              <span class="chip-tx">{{ b.label }}</span>
            </div>
          </div>
        </div>

        <div class="fld">
          <label class="fld-label">可见性</label>
          <div class="vis-row">
            <div
              class="vis-btn vis-shared"
              :class="{ on: visibility === 'shared' }"
              @click="visibility = 'shared'"
            >
              👁 对方可见
            </div>
            <div
              class="vis-btn vis-self"
              :class="{ on: visibility === 'self' }"
              @click="visibility = 'self'"
            >
              🔒 仅本人可见
            </div>
          </div>
        </div>

        <!-- 收益管理：勾选后该账户按「现值 − 本金」计入收益统计 -->
        <div class="fld">
          <label class="fld-label">收益管理</label>
          <div class="sw-row" @click="isInvest = !isInvest">
            <div class="sw-main">
              <div class="sw-title">纳入收益管理</div>
              <div class="sw-sub">股票 / 基金 / 理财账户勾选后统计收益</div>
            </div>
            <span class="sw" :class="{ on: isInvest }"><i></i></span>
          </div>
        </div>

        <div v-if="isInvest" class="fld">
          <label class="fld-label">收益总额</label>
          <!-- 数字键盘没有负号，用「盈利 / 亏损」切换正负，否则亏损根本填不进去 -->
          <div class="sign-row">
            <div
              class="sign-btn sign-plus"
              :class="{ on: profitSign === 1 }"
              @click="profitSign = 1"
            >
              ＋ 盈利
            </div>
            <div
              class="sign-btn sign-minus"
              :class="{ on: profitSign === -1 }"
              @click="profitSign = -1"
            >
              － 亏损
            </div>
          </div>
          <div class="money-input">
            <span class="money-sign">{{ profitSign === -1 ? '-¥' : '¥' }}</span>
            <input
              :value="profitInput"
              type="text"
              inputmode="decimal"
              placeholder="0.00"
              @input="onProfitInput"
            />
          </div>
          <div class="fld-tip">
            目前累计赚的钱；亏了就选「亏损」；投入本金 = 当前金额 − 收益
          </div>
        </div>

        <div class="fld">
          <label class="fld-label">当前金额{{ isInvest ? '（含收益）' : '' }}</label>
          <div class="money-input">
            <span class="money-sign">¥</span>
            <input v-model="balance" type="number" inputmode="decimal" placeholder="0.00" />
          </div>
        </div>
      </div>

      <div class="acc-actions">
        <button class="btn btn-cancel" :disabled="saving" @click="emit('close')">取消</button>
        <button class="btn btn-primary" :disabled="saving" @click="onSave">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
      <button v-if="isEdit" class="btn btn-delete" :disabled="saving" @click="onDelete">
        删除账户
      </button>
    </div>

    <ConfirmSheet
      :visible="confirmState.show"
      :title="confirmState.title"
      :lines="confirmState.lines"
      :ok-text="confirmState.okText"
      danger
      @ok="answerConfirm(true)"
      @cancel="answerConfirm(false)"
    />
  </div>
</template>

<style scoped>
.acc-sheet {
  max-height: 90vh;
  overflow-y: auto;
}
.acc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.acc-title {
  font-size: 17px;
  font-weight: 600;
  color: #26215c;
}
.acc-close {
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
.fld {
  margin-bottom: 16px;
}
.fld-label {
  display: block;
  font-size: 12px;
  color: #888780;
  margin-bottom: 8px;
}
.fld-input,
.money-input {
  width: 100%;
  border: 0.5px solid #d3d1c7;
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  color: #26215c;
  background: #fff;
  box-sizing: border-box;
  outline: none;
}
.fld-input:focus,
.money-input:focus-within {
  border-color: #ef9f27;
  box-shadow: 0 0 0 2px rgba(239, 159, 39, 0.15);
}
.money-input {
  display: flex;
  align-items: center;
  gap: 6px;
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
  background: transparent;
  min-width: 0;
}
.chip-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
/* 收益管理开关 */
.sw-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 0.5px solid #e8e8e8;
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
}
.sw-title {
  font-size: 14px;
  color: #26215c;
}
.sw-sub {
  font-size: 11px;
  color: #b8b6ae;
  margin-top: 2px;
}
.sw {
  flex: none;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: #d3d1c7;
  position: relative;
  transition: background 0.2s;
}
.sw i {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.sw.on {
  background: #1d9e75;
}
.sw.on i {
  transform: translateX(18px);
}
.fld-tip {
  margin-top: 6px;
  font-size: 11px;
  color: #b8b6ae;
  line-height: 1.5;
}
.sign-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.sign-btn {
  flex: 1;
  text-align: center;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 13px;
  border: 0.5px solid #e8e8e8;
  background: #fff;
  color: #888780;
  cursor: pointer;
}
.sign-plus.on {
  background: #e1f5ee;
  border-color: #1d9e75;
  color: #0f6e56;
  font-weight: 600;
}
.sign-minus.on {
  background: #fcecec;
  border-color: #e24b4a;
  color: #a32d2d;
  font-weight: 600;
}
.chip {
  flex: 1;
  border: 0.5px solid #e8e8e8;
  border-radius: 10px;
  padding: 10px 4px;
  text-align: center;
  cursor: pointer;
  background: #fff;
}
.chip-ic {
  display: block;
  font-size: 20px;
  line-height: 1.2;
}
.chip-tx {
  font-size: 11px;
  color: #5f5e5a;
}
.chip.on {
  border-color: #7f77dd;
  background: #eeedfe;
}
.chip.on .chip-tx {
  color: #534ab7;
  font-weight: 600;
}
.vis-row {
  display: flex;
  gap: 8px;
}
.vis-btn {
  flex: 1;
  text-align: center;
  padding: 11px 0;
  border-radius: 8px;
  font-size: 13px;
  border: 1px solid transparent;
  cursor: pointer;
  background: #fff;
  border-color: #e8e8e8;
  color: #5f5e5a;
}
.vis-shared.on {
  background: #1d9e75;
  border-color: #1d9e75;
  color: #fff;
  font-weight: 500;
}
.vis-self.on {
  background: #fdf3e2;
  border-color: #ef9f27;
  color: #9a6410;
  font-weight: 500;
}
.acc-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
.btn-cancel {
  flex: 1;
  background: #fff;
  border: 0.5px solid #d3d1c7;
  color: #5f5e5a;
  padding: 12px 0;
}
.acc-actions .btn-primary {
  flex: 1;
}
.btn-delete {
  width: 100%;
  margin-top: 10px;
  background: #e24b4a;
  color: #fff;
  padding: 12px 0;
}
</style>
