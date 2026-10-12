<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { accountApi, authApi, exportTransactions, familyApi, ledgerApi, loanApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { yuan } from '@/utils/money'

const router = useRouter()
const auth = useAuthStore()
const accounts = ref([])
const ov = ref(null)
// 家庭管理入口：协商阈值与成员数，直接读真实数据，避免假数字
const thr = ref(null)
const famInfo = ref(null)

// —— AI 智能分析：配置存后端库、保存即生效；未配置时报告页自动走本地规则引擎 ——
const PROVIDERS = {
  deepseek: { label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  qwen: { label: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  moonshot: { label: 'Kimi (Moonshot)', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  openai: { label: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { label: '自定义（OpenAI 兼容）', base_url: '', model: '' },
}
const aiCfg = ref(null)
const showAiForm = ref(false)
const aiSaving = ref(false)
const aiTesting = ref(false)
const aiMsg = ref('')
const useAI = ref(localStorage.getItem('insight_use_ai') === '1')
const aiForm = reactive({ provider: 'deepseek', base_url: '', model: '', api_key: '' })

// configured=Key/接口地址/模型名齐全，此时顶部开关才能打开（开关即“启用 AI”）
const aiConfigured = computed(
  () => !!aiCfg.value?.has_key && !!aiForm.base_url && !!aiForm.model
)
const aiStateText = computed(() =>
  !aiConfigured.value ? '未配置' : useAI.value ? '已开启' : '已关闭'
)

function setProvider(p) {
  aiForm.provider = p
  const preset = PROVIDERS[p]
  if (preset && p !== 'custom') {
    aiForm.base_url = preset.base_url
    aiForm.model = preset.model
  }
}
async function loadAi() {
  try {
    const r = await ledgerApi.aiConfig()
    aiCfg.value = r
    aiForm.provider = PROVIDERS[r.provider] ? r.provider : 'custom'
    aiForm.base_url = r.base_url || ''
    aiForm.model = r.model || ''
    // 界面存过配置时，开关状态以库里为准（家庭共享同一份配置）
    if (r.source === 'ui') {
      useAI.value = !!r.enabled
      localStorage.setItem('insight_use_ai', r.enabled ? '1' : '0')
    }
  } catch (e) {
    aiCfg.value = null
  }
}
async function toggleAI() {
  if (!aiConfigured.value) {
    // 没配置时点开关不是“没反应”，而是直接带用户去填配置
    showAiForm.value = true
    aiMsg.value = aiCfg.value?.has_key
      ? '还差接口地址或模型名：在下方补全后保存'
      : '还没配置大模型：填好 API Key 并保存后，这里就能切换到 AI 分析'
    return
  }
  // 顶部开关 = 启用/停用：只提交 enabled，失败则回滚，避免界面与库里不一致
  aiMsg.value = ''
  const next = !useAI.value
  useAI.value = next
  localStorage.setItem('insight_use_ai', next ? '1' : '0')
  try {
    aiCfg.value = await ledgerApi.saveAiConfig({ enabled: next })
  } catch (e) {
    useAI.value = !next
    localStorage.setItem('insight_use_ai', useAI.value ? '1' : '0')
    aiMsg.value = e?.message || '切换失败'
  }
}
async function testAi() {
  aiTesting.value = true
  aiMsg.value = ''
  try {
    const r = await ledgerApi.testAiConfig({
      base_url: aiForm.base_url,
      model: aiForm.model,
      api_key: aiForm.api_key,
    })
    aiMsg.value = (r.ok ? '✅ ' : '⚠️ ') + r.message
  } catch (e) {
    aiMsg.value = '⚠️ ' + (e?.message || '测试失败')
  } finally {
    aiTesting.value = false
  }
}
async function saveAi() {
  aiSaving.value = true
  aiMsg.value = ''
  try {
    aiCfg.value = await ledgerApi.saveAiConfig({
      provider: aiForm.provider,
      base_url: aiForm.base_url,
      model: aiForm.model,
      api_key: aiForm.api_key,
      // 表单里不再放重复的启用开关，以顶部「AI 智能分析」为准
      enabled: useAI.value,
    })
    useAI.value = !!aiCfg.value.enabled
    localStorage.setItem('insight_use_ai', useAI.value ? '1' : '0')
    aiForm.api_key = ''
    showAiForm.value = false // 保存即收起，点「配置大模型」可再展开
    if (!aiConfigured.value) {
      aiMsg.value = '已保存，但 Key / 接口地址 / 模型名不全，暂仍使用本地分析'
    } else {
      aiMsg.value = useAI.value ? '已保存并启用，去报告页点 AI 即可' : '已保存（顶部开关未打开，仍是本地分析）'
    }
  } catch (e) {
    aiMsg.value = e?.message || '保存失败'
  } finally {
    aiSaving.value = false
  }
}

const myAssets = computed(() => yuan(accounts.value.reduce((s, a) => s + (a.balance_cents || 0), 0)).toFixed(2))
const monthExpense = computed(() => (ov.value ? yuan(ov.value.expense_cents).toFixed(2) : '0.00'))
const monthBalance = computed(() => (ov.value ? yuan(ov.value.balance_cents).toFixed(2) : '0.00'))

const thrYuan = (c) => Math.round((Number(c) || 0) / 100)
const thrText = computed(() => {
  if (!thr.value) return '未设置'
  return `¥${thrYuan(thr.value.small_limit)} / ¥${thrYuan(thr.value.notify_limit)} / ¥${thrYuan(thr.value.approve_limit)}`
})
const memberCountText = computed(() => {
  if (!famInfo.value) return ''
  return `${famInfo.value.members.length}/${famInfo.value.member_limit} 人`
})
// 主账号设置：显示「我是主账号」或当前主账号是谁，让人一眼知道管理权在谁手上
const ownerText = computed(() => {
  const list = famInfo.value?.members || []
  const owner = list.find((m) => m.role === 'owner')
  if (auth.isOwner) return '我是主账号'
  return owner ? `当前：${owner.nickname || owner.username}` : '未设置'
})
const inviteText = computed(() => {
  const n = famInfo.value?.members?.length || 0
  return n >= (famInfo.value?.member_limit || 5) ? '已满' : '›'
})

// 借钱来往：只取总览，菜单上直接显示未收/未付
const loanSum = ref(null)
const loanText = computed(() => {
  const s = loanSum.value
  if (!s) return ''
  const parts = []
  if (s.lend_cents) parts.push(`借出 ¥${Math.round(s.lend_cents / 100)}`)
  if (s.borrow_cents) parts.push(`借入 ¥${Math.round(s.borrow_cents / 100)}`)
  return parts.join(' · ')
})

// 收益管理：菜单上直接显示累计收益，没开收益管理时留空
const retSum = ref(null)
const retText = computed(() => {
  const s = retSum.value
  if (!s || !s.has_invest) return ''
  const c = Number(s.profit_cents || 0)
  return `${c > 0 ? '+' : c < 0 ? '-' : ''}¥${Math.round(Math.abs(c) / 100)}`
})

async function load() {
  try {
    const [me, a, o] = await Promise.all([
      authApi.me(),
      accountApi.list(),
      ledgerApi.overview({ preset: 'last_month' }),
    ])
    auth.user = me.user
    auth.family = me.family
    auth.member = me.member
    accounts.value = a.items || a || []
    ov.value = o
  } catch (e) {
    console.error(e)
  }
  // 家庭信息与阈值独立拉取：未加入家庭 / 无权查看时不影响本页其它数据
  try {
    famInfo.value = await familyApi.me()
  } catch (e) {
    famInfo.value = null
  }
  try {
    thr.value = await familyApi.thresholds()
  } catch (e) {
    thr.value = null
  }
  try {
    loanSum.value = (await loanApi.list()).summary || null
  } catch (e) {
    loanSum.value = null
  }
  try {
    retSum.value = await accountApi.returns()
  } catch (e) {
    retSum.value = null
  }
}

// —— 隐私额度：每人一份，私密支出超过额度部分自动计入共同支出 ——
const PRIVACY_MIN = 100 // 与后端 ProfileUpdateView 的 10000~200000 分对齐
const PRIVACY_MAX = 2000
const PRIVACY_PRESETS = [300, 500, 1000, 2000]
const showPrivacyForm = ref(false)
const privacySaving = ref(false)
const privacyMsg = ref('')
const privacyYuan = ref(500)

const privacyText = computed(() => {
  const c = auth.user?.privacy_limit_cents
  return c == null ? '未设置' : `每月 ¥${Math.round(Number(c) / 100)}`
})

function openPrivacy() {
  privacyYuan.value = Math.round(Number(auth.user?.privacy_limit_cents || 50000) / 100)
  privacyMsg.value = ''
  showPrivacyForm.value = !showPrivacyForm.value
}

async function savePrivacy() {
  const n = Math.round(Number(privacyYuan.value))
  if (!n || n < PRIVACY_MIN || n > PRIVACY_MAX) {
    privacyMsg.value = `额度需在 ¥${PRIVACY_MIN} ~ ¥${PRIVACY_MAX} 之间`
    return
  }
  privacySaving.value = true
  privacyMsg.value = ''
  try {
    auth.user = await authApi.updateProfile({ privacy_limit_cents: n * 100 })
    privacyMsg.value = `已保存：每月 ¥${n}，本月立即生效`
  } catch (e) {
    privacyMsg.value = e?.message || '保存失败'
  } finally {
    privacySaving.value = false
  }
}

// —— 导出账单：区间与报告页同一套 preset，导出内容 = 屏幕上能看到的内容 ——
const EXPORT_RANGES = [
  { key: 'last_month', label: '本月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'last_year', label: '近一年' },
  { key: 'all', label: '全部' },
]
const EXPORT_TYPES = [
  { key: '', label: '全部类型' },
  { key: 'expense', label: '支出' },
  { key: 'income', label: '收入' },
]
const showExport = ref(false)
const exportRange = ref('last_month')
const exportType = ref('')
const exporting = ref(false)
const exportMsg = ref('')

async function doExport() {
  exporting.value = true
  exportMsg.value = ''
  const label = (EXPORT_RANGES.find((r) => r.key === exportRange.value) || {}).label || ''
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  try {
    const size = await exportTransactions(
      { preset: exportRange.value, type: exportType.value || undefined },
      `家庭账单_${label}_${stamp}.csv`,
    )
    exportMsg.value = `已导出 ${label} · ${(size / 1024).toFixed(1)} KB，请在浏览器下载中查看`
  } catch (e) {
    exportMsg.value = e?.message || '导出失败'
  } finally {
    exporting.value = false
  }
}

// —— 推送：当前版本没有接任何推送通道，如实告知，不放假开关 ——
const showPush = ref(false)
const PUSH_ITEMS = [
  { label: '对方大额支出知会', state: '未接入' },
  { label: '超阈值支出待确认', state: '未接入' },
  { label: '每月账单汇总', state: '未接入' },
]

function onLogout() {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  load()
  loadAi()
})
</script>

<template>
  <div class="page mine-page">
    <!-- 用户信息 -->
    <div class="profile-header">
      <div class="profile-avatar">{{ auth.user?.nickname?.[0] || '财' }}</div>
      <div class="profile-info">
        <div class="profile-name">{{ auth.user?.nickname || '未设置昵称' }}</div>
        <div class="profile-bind">👥 已绑定{{ auth.family?.name || '家庭' }}</div>
      </div>
    </div>

    <!-- 账户总览 -->
    <div class="account-overview">
      <div class="ov-item">
        <div class="ov-value">¥{{ myAssets }}</div>
        <div class="ov-label">我的资产</div>
      </div>
      <div class="ov-item">
        <div class="ov-value text-expense">¥{{ monthExpense }}</div>
        <div class="ov-label">本月支出</div>
      </div>
      <div class="ov-item">
        <div class="ov-value text-income">¥{{ monthBalance }}</div>
        <div class="ov-label">本月结余</div>
      </div>
    </div>

    <!-- 账户管理 -->
    <div class="menu-section">
      <div class="menu-item" @click="router.push('/accounts')">
        <span class="menu-icon">💳</span>
        <span class="menu-text">账户管理</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 智能分析：界面直接配大模型，保存即生效；不配则走本地规则引擎 -->
    <div class="menu-section">
      <div class="menu-title">智能分析</div>
      <div class="menu-item" @click="toggleAI">
        <span class="menu-icon">🤖</span>
        <span class="menu-text">AI 智能分析</span>
        <span class="menu-value">{{ aiStateText }}</span>
        <span
          class="switch"
          :class="{ on: useAI && aiConfigured, off: !aiConfigured }"
          @click.stop="toggleAI"
        >
          <span class="switch-dot"></span>
        </span>
      </div>
      <!-- 配置入口默认收起：只有开关被打开（或已配好 Key）后才出现 -->
      <div v-if="showAiForm || aiConfigured" class="menu-item" @click="showAiForm = !showAiForm">
        <span class="menu-icon">⚙️</span>
        <span class="menu-text">配置大模型</span>
        <span class="menu-value">{{ aiCfg?.has_key ? '已存 Key' : '未填写' }}</span>
        <span class="menu-arrow">{{ showAiForm ? '⌃' : '›' }}</span>
      </div>

      <div v-if="aiMsg" class="ai-msg">{{ aiMsg }}</div>

      <div v-if="showAiForm" class="ai-form">
        <div class="ai-field">
          <label>服务商</label>
          <select v-model="aiForm.provider" @change="setProvider(aiForm.provider)">
            <option v-for="(v, k) in PROVIDERS" :key="k" :value="k">{{ v.label }}</option>
          </select>
        </div>
        <div class="ai-field">
          <label>接口地址</label>
          <input v-model="aiForm.base_url" placeholder="https://api.deepseek.com/v1" />
        </div>
        <div class="ai-field">
          <label>模型名</label>
          <input v-model="aiForm.model" placeholder="deepseek-chat" />
        </div>
        <div class="ai-field">
          <label>API Key</label>
          <input
            v-model="aiForm.api_key"
            type="password"
            :placeholder="aiCfg?.has_key ? '已保存 ' + aiCfg.key_mask + '，留空则不修改' : 'sk-...'"
          />
        </div>
        <div class="ai-actions">
          <button class="ai-btn secondary" :disabled="aiTesting" @click="testAi">
            {{ aiTesting ? '测试中…' : '测试连接' }}
          </button>
          <button class="ai-btn primary" :disabled="aiSaving" @click="saveAi">
            {{ aiSaving ? '保存中…' : '保存' }}
          </button>
        </div>
        <div class="ai-note">
          Key 只存在本机数据库，接口只回传掩码；未配置时智能分析走本地规则引擎，账单数据不外传。
        </div>
      </div>
    </div>

    <!-- 信任规则 -->
    <div class="menu-section">
      <div class="menu-title">信任规则</div>
      <div class="menu-item" @click="router.push({ path: '/family', query: { view: 'threshold' } })">
        <span class="menu-icon">💰</span>
        <span class="menu-text">协商阈值</span>
        <span class="menu-value">{{ thrText }}</span>
        <span class="menu-arrow">›</span>
      </div>
      <div class="menu-item" @click="openPrivacy">
        <span class="menu-icon">🔐</span>
        <span class="menu-text">隐私额度</span>
        <span class="menu-value">{{ privacyText }}</span>
        <span class="menu-arrow">{{ showPrivacyForm ? '⌃' : '›' }}</span>
      </div>

      <div v-if="showPrivacyForm" class="ai-form">
        <div class="quota-chips">
          <span
            v-for="p in PRIVACY_PRESETS"
            :key="p"
            class="qchip"
            :class="{ on: Number(privacyYuan) === p }"
            @click="privacyYuan = p"
            >¥{{ p }}</span
          >
        </div>
        <div class="ai-field">
          <label>每月私密额度（元）</label>
          <input v-model="privacyYuan" type="number" :min="PRIVACY_MIN" :max="PRIVACY_MAX" />
        </div>
        <div v-if="privacyMsg" class="ai-msg">{{ privacyMsg }}</div>
        <div class="ai-actions">
          <button class="ai-btn primary" :disabled="privacySaving" @click="savePrivacy">
            {{ privacySaving ? '保存中…' : '保存' }}
          </button>
        </div>
        <div class="ai-note">
          标记为私密的支出，每月累计在额度以内对方完全看不到；超出额度的部分会自动计入共同支出。额度
          ¥{{ PRIVACY_MIN }} ~ ¥{{ PRIVACY_MAX }}，只对本人生效，保存后当月立即按新额度计算。
        </div>
      </div>
    </div>

    <!-- 资金往来 -->
    <div class="menu-section">
      <div class="menu-title">资金往来</div>
      <div class="menu-item" @click="router.push('/loans')">
        <span class="menu-icon">🤝</span>
        <span class="menu-text">借钱来往</span>
        <span class="menu-value">{{ loanText }}</span>
        <span class="menu-arrow">›</span>
      </div>
      <div class="menu-item" @click="router.push('/returns')">
        <span class="menu-icon">📈</span>
        <span class="menu-text">收益管理</span>
        <span class="menu-value">{{ retText || '未开启' }}</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 家庭管理 -->
    <div class="menu-section">
      <div class="menu-title">家庭管理</div>
      <div class="menu-item" @click="router.push({ path: '/family', query: { invite: '1' } })">
        <span class="menu-icon">👥</span>
        <span class="menu-text">邀请成员</span>
        <span class="menu-value">{{ inviteText === '已满' ? '已满' : '' }}</span>
        <span class="menu-arrow">{{ inviteText }}</span>
      </div>
      <div class="menu-item" @click="router.push('/family')">
        <span class="menu-icon">👥</span>
        <span class="menu-text">家庭成员</span>
        <span class="menu-value">{{ memberCountText }}</span>
        <span class="menu-arrow">›</span>
      </div>
      <!-- 主账号设置：注册的人默认就是主账号，可在这里把管理权转让给对方 -->
      <div class="menu-item" @click="router.push({ path: '/family', query: { view: 'members' } })">
        <span class="menu-icon">👑</span>
        <span class="menu-text">主账号设置</span>
        <span class="menu-value">{{ ownerText }}</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 其他 -->
    <div class="menu-section">
      <div class="menu-title">其他</div>
      <div class="menu-item" @click="router.push('/import')">
        <span class="menu-icon">📥</span>
        <span class="menu-text">账单导入</span>
        <span class="menu-arrow">›</span>
      </div>
      <div class="menu-item" @click="showExport = !showExport">
        <span class="menu-icon">📤</span>
        <span class="menu-text">导出账单</span>
        <span class="menu-value">CSV</span>
        <span class="menu-arrow">{{ showExport ? '⌃' : '›' }}</span>
      </div>
      <div v-if="showExport" class="ai-form">
        <div class="quota-chips">
          <span
            v-for="r in EXPORT_RANGES"
            :key="r.key"
            class="qchip"
            :class="{ on: exportRange === r.key }"
            @click="exportRange = r.key"
            >{{ r.label }}</span
          >
        </div>
        <div class="quota-chips">
          <span
            v-for="t in EXPORT_TYPES"
            :key="t.key || 'all'"
            class="qchip"
            :class="{ on: exportType === t.key }"
            @click="exportType = t.key"
            >{{ t.label }}</span
          >
        </div>
        <div v-if="exportMsg" class="ai-msg">{{ exportMsg }}</div>
        <div class="ai-actions">
          <button class="ai-btn primary" :disabled="exporting" @click="doExport">
            {{ exporting ? '生成中…' : '导出 CSV' }}
          </button>
        </div>
        <div class="ai-note">
          导出内容与流水里看到的一致：对方未授权的私密消费不会进文件，已授权的也只带总额、不含商户与备注。
        </div>
      </div>

      <div class="menu-item" @click="showPush = !showPush">
        <span class="menu-icon">🔔</span>
        <span class="menu-text">推送设置</span>
        <span class="menu-value">未接入</span>
        <span class="menu-arrow">{{ showPush ? '⌃' : '›' }}</span>
      </div>
      <div v-if="showPush" class="ai-form">
        <div v-for="p in PUSH_ITEMS" :key="p.label" class="push-row">
          <span>{{ p.label }}</span>
          <em>{{ p.state }}</em>
        </div>
        <div class="ai-note">
          系统推送需要微信服务号模板消息或浏览器 Push 授权，当前版本还没有接通道，所以这里没有开关可以拨。
          现在能拿到的提醒是记账后的即时提示：超过「事后知会」提示你知会对方，超过「事前申请」提示需对方确认。
        </div>
      </div>
      <div class="menu-item" @click="onLogout">
        <span class="menu-icon">🚪</span>
        <span class="menu-text text-expense">退出登录</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

  </div>
</template>

<style scoped>
.mine-page {
  padding-bottom: 80px;
}
.profile-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 20px;
  background: linear-gradient(135deg, #7f77dd, #534ab7);
  color: #fff;
}
.profile-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
}
.profile-info {
  display: flex;
  flex-direction: column;
}
.profile-name {
  font-size: 18px;
  font-weight: 700;
}
.profile-bind {
  font-size: 13px;
  opacity: 0.85;
  margin-top: 4px;
}
.account-overview {
  display: flex;
  background: #fff;
  border-radius: 12px;
  margin: 16px;
  padding: 16px 0;
  border: 0.5px solid #e8e8e8;
}
.ov-item {
  flex: 1;
  text-align: center;
  display: flex;
  flex-direction: column;
}
.ov-value {
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.ov-label {
  font-size: 12px;
  color: #888780;
  margin-top: 4px;
}
.menu-section {
  background: #fff;
  border-radius: 12px;
  margin: 0 16px 12px;
  padding: 4px 16px;
  border: 0.5px solid #e8e8e8;
}
.menu-title {
  font-size: 12px;
  color: #888780;
  padding: 12px 0 4px;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 0.5px solid #f1efe8;
  cursor: pointer;
}
.menu-item:last-child {
  border-bottom: none;
}
.menu-icon {
  font-size: 18px;
}
.menu-text {
  flex: 1;
  font-size: 14px;
}
.menu-value {
  font-size: 12px;
  color: #888780;
}
.menu-arrow {
  color: #c8c6c0;
  font-size: 16px;
}
.menu-tip {
  font-size: 11px;
  color: #888780;
  line-height: 1.6;
  padding: 0 0 12px;
}
/* 小开关：未配置大模型时置灰不可点 */
.switch {
  flex: none;
  width: 38px;
  height: 21px;
  border-radius: 20px;
  background: #e3e1da;
  position: relative;
  transition: background 0.18s;
}
.switch .switch-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
  transition: transform 0.18s;
}
.switch.on {
  background: #534ab7;
}
.switch.on .switch-dot {
  transform: translateX(17px);
}
.switch.off {
  opacity: 0.4;
}
/* AI 配置面板 */
.ai-msg {
  font-size: 12px;
  line-height: 1.6;
  color: #534ab7;
  background: #eeedfe;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 4px 0 10px;
  word-break: break-all;
}
.ai-form {
  border-top: 0.5px solid #f1efe8;
  padding: 12px 0 14px;
}
.ai-field {
  margin-bottom: 10px;
}
.ai-field label {
  display: block;
  font-size: 11px;
  color: #888780;
  margin-bottom: 4px;
}
.ai-field input,
.ai-field select {
  width: 100%;
  box-sizing: border-box;
  font-size: 13px;
  padding: 8px 10px;
  border: 0.5px solid #e3e1da;
  border-radius: 8px;
  background: #fdfdfb;
  color: #1c1b1a;
}
.ai-field input:focus,
.ai-field select:focus {
  outline: none;
  border-color: #7f77dd;
}
.ai-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.ai-btn {
  flex: 1;
  font-size: 13px;
  padding: 9px 0;
  border-radius: 8px;
  border: 0.5px solid #e3e1da;
  background: #fff;
  color: #444441;
  cursor: pointer;
}
.ai-btn.primary {
  background: #534ab7;
  border-color: #534ab7;
  color: #fff;
  font-weight: 500;
}
.ai-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ai-note {
  font-size: 11px;
  color: #888780;
  line-height: 1.6;
  margin-top: 10px;
}
/* 隐私额度快捷档 */
.quota-chips {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.qchip {
  flex: 1;
  text-align: center;
  font-size: 13px;
  padding: 7px 0;
  border-radius: 8px;
  border: 0.5px solid #e3e1da;
  background: #fdfdfb;
  color: #444441;
  cursor: pointer;
}
.qchip.on {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #534ab7;
  font-weight: 600;
}
/* 推送：只如实列出接入状态 */
.push-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 0.5px solid #f1efe8;
  font-size: 13px;
  color: #444441;
}
.push-row em {
  font-style: normal;
  font-size: 12px;
  color: #b4b2a9;
}
</style>