<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  accountApi,
  authApi,
  exportTransactions,
  familyApi,
  ledgerApi,
  loanApi,
  membershipApi,
  recurringApi,
} from '@/api'
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/utils/toast'
import { VIP_ENABLED } from '@/utils/flags'
import { yuan } from '@/utils/money'
import { appSharePayload, share } from '@/utils/share'

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

/*
 * 是否真的可用：以后端 has_key 为准，不拿表单字段判断。
 * ★ 之前用 !!aiForm.base_url && !!aiForm.model 判断会误判——.env 里
 *   AI_BASE_URL / AI_MODEL 有默认值，即使从没配过 Key 也算「已配置」，
 *   于是开关显示可点，点了调接口才报错，看着就是开关有 bug。
 * 表单只用于填写，判断一律看后端返回的 has_key。
 */
const aiConfigured = computed(() => !!aiCfg.value?.has_key)
/**
 * 配置来源为 .env 时界面只能看不能改：
 * 那种配置由运维在服务器上维护，网页保存会写出一条 AISettings 覆盖它，
 * 运维再改 .env 就不生效了，排查起来很费劲。
 */
const aiFromEnv = computed(() => aiCfg.value?.source === 'env' && !!aiCfg.value?.has_key)
/**
 * 开关的视觉状态 = 用户是否想用 AI。
 * ★ 不能绑 aiConfigured：没配 Key 时开关永远灰着，用户点不动，
 *   而实际上「点了就是要用 AI」，应该立刻变绿并弹出配置表单。
 *   是否真正生效由后端 enabled 决定，保存成功后才算数。
 */
const aiSwitchOn = computed(() => useAI.value)
const aiStateText = computed(() => {
  if (aiFromEnv.value) return '已开启'
  if (!useAI.value) return '已关闭'
  // 开关开着但还没存过 Key：提示还差一步，避免用户以为已经能用
  return aiConfigured.value ? '已开启' : '待配置'
})

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
    /*
     * 开关状态始终以后端为准：配置是家庭共享的，
     * 如果沿用 localStorage，换设备或对方在网页改过就会显示成旧状态，
     * 用户点一下开关反而是「取消」自己以为的开启，看着像开关失灵。
     *
     * 两种情况都采信 enabled：
     *   source=ui  → 界面保存过配置
     *   source=env → .env 里配了 AI_API_KEY，此时只读，界面不能改（见 canEditAi）
     */
    useAI.value = !!r.enabled
    localStorage.setItem('insight_use_ai', r.enabled ? '1' : '0')
  } catch (e) {
    aiCfg.value = null
  }
}
async function toggleAI() {
  // .env 配的 AI 由服务器维护，界面不提供切换，只给出说明
  if (aiFromEnv.value) {
    aiMsg.value = '当前使用服务器 .env 中配置的大模型，如需在界面修改请先移除服务器上的 AI_API_KEY'
    return
  }

  const next = !useAI.value
  // ★ 先切开关：点一下必须立刻变绿/变灰，不能等接口回来才有反馈
  useAI.value = next
  localStorage.setItem('insight_use_ai', next ? '1' : '0')
  aiMsg.value = ''

  if (!next) {
    /*
     * 关闭：收起表单 + 后端置 enabled=false，
     * 报告页随之回落本地规则分析。没保存过配置的无需调接口。
     */
    showAiForm.value = false
    if (!aiConfigured.value) return
    try {
      aiCfg.value = await ledgerApi.saveAiConfig({ enabled: false })
      aiMsg.value = '已切回本地分析'
    } catch (e) {
      // 落库失败要把开关拨回去，否则界面与配置不一致
      useAI.value = true
      localStorage.setItem('insight_use_ai', '1')
      aiMsg.value = e?.message || '切换失败'
    }
    return
  }

  // 打开：展开配置弹窗；已经配好 Key 的直接启用
  showAiForm.value = true
  if (!aiConfigured.value) {
    aiMsg.value = '还没配置大模型：填好 API Key 并保存后，报告页就会用 AI 分析'
    return
  }
  try {
    aiCfg.value = await ledgerApi.saveAiConfig({ enabled: true })
    showAiForm.value = false
    aiMsg.value = '已启用，去报告页点 AI 即可'
  } catch (e) {
    useAI.value = false
    localStorage.setItem('insight_use_ai', '0')
    aiMsg.value = e?.message || '开启失败'
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
      /*
       * 保存即启用，与小程序「保存并启用」一致。
       * 之前传 useAI.value：首次填 Key 时它还是 false，
       * 保存完就成了「已配置但未启用」，用户得再点一次开关，多一步还容易以为没生效。
       */
      enabled: true,
    })
    useAI.value = !!aiCfg.value.enabled
    localStorage.setItem('insight_use_ai', useAI.value ? '1' : '0')
    aiForm.api_key = ''
    // 保存即收起：开关重新成为唯一入口，要看配置再点一次开关即可
    showAiForm.value = false
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

// 定时记账：菜单显示启用中的规则数，没有规则时留空
const recSummary = ref(null)
const recText = computed(() => {
  const n = Number(recSummary.value?.active_count || 0)
  return n ? `${n} 条运行中` : ''
})

// 会员：菜单显示到期/试用状态
const vipInfo = ref(null)
const vipText = computed(() => {
  const m = vipInfo.value
  if (!m) return ''
  if (!m.is_vip) return m.can_trial ? `可试用 ${m.trial_days} 天` : '未开通'
  return m.is_trial ? `试用剩 ${m.remain_days} 天` : `剩 ${m.remain_days} 天`
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
  if (VIP_ENABLED) {
    try {
      vipInfo.value = await membershipApi.mine()
    } catch (e) {
      vipInfo.value = null
    }
  }
}

// —— 隐私额度：每人一份，私密支出超过额度部分自动计入共同支出 ——
const PRIVACY_MIN = 100 // 与后端 ProfileUpdateView 的 10000~500000 分对齐
const PRIVACY_MAX = 5000
const PRIVACY_PRESETS = [300, 500, 1000, 2000, 5000]
const showPrivacyForm = ref(false)
const privacySaving = ref(false)
const privacyMsg = ref('')
const privacyYuan = ref(500)

const privacyText = computed(() => {
  const c = auth.user?.privacy_limit_cents
  return c == null ? '未设置' : `每月 ¥${Math.round(Number(c) / 100)}`
})

function openPrivacy() {
  privacyYuan.value = Math.round(Number(auth.user?.privacy_limit_cents || 500000) / 100)
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

// —— 登录密码：微信一键登录的用户没有密码，在这里补一个后即可用手机号登录 H5 ——
const showPwdForm = ref(false)
const pwdSaving = ref(false)
const pwdMsg = ref('')
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const hasPassword = computed(() => auth.user?.has_password !== false)

const pwdTitle = computed(() => (hasPassword.value ? '修改密码' : '设置密码'))
const pwdText = computed(() => (hasPassword.value ? '已设置' : '未设置'))

// —— 账号打通：H5 与小程序共用一张 User 表，这里只读展示两把「钥匙」的绑定状态 ——
// H5 拿不到 wx.login，所以微信绑定只能在小程序里完成，这里只做引导。
const hasWechat = computed(() => !!auth.user?.has_wechat)
const maskedPhone = computed(() => {
  const p = String(auth.user?.phone || '')
  return p.length === 11 ? `${p.slice(0, 3)}****${p.slice(7)}` : p || '未绑定'
})

function onWechatBindTip() {
  if (hasWechat.value) {
    toast('已绑定微信，可在小程序用微信一键登录')
    return
  }
  toast('微信绑定要在小程序里完成：「我的 → 绑定微信」')
}

function openPwd() {
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm_password = ''
  pwdMsg.value = ''
  showPwdForm.value = !showPwdForm.value
}

async function savePwd() {
  // 密码规则：字母+数字，不低于 6 位（与后端 validators.LetterAndDigitValidator 一致）
  if (!/^(?=.*[a-zA-Z])(?=.*\d).{6,}$/.test(pwdForm.new_password)) {
    pwdMsg.value = '密码需同时包含字母和数字，且不低于 6 位'
    return
  }
  if (pwdForm.confirm_password !== pwdForm.new_password) {
    pwdMsg.value = '两次输入的新密码不一致'
    return
  }
  pwdSaving.value = true
  pwdMsg.value = ''
  try {
    await authApi.updatePassword({
      new_password: pwdForm.new_password,
      confirm_password: pwdForm.confirm_password,
    })
    auth.user = { ...auth.user, has_password: true }
    pwdMsg.value = hasPassword.value
      ? '密码已修改，下次登录请使用新密码'
      : `已设置，之后可用手机号 ${auth.user?.phone || ''} 登录网页版`
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch (e) {
    pwdMsg.value = e?.message || '保存失败'
  } finally {
    pwdSaving.value = false
  }
}

function onLogout() {
  auth.logout()
  router.push('/login')
}

// —— 分享：H5 在微信里不能自定义卡片，降级为「引导点右上角」，由 share() 返回 guide 决定 ——
const showShareGuide = ref(false)
async function handleShare() {
  const r = await share(appSharePayload())
  if (r === 'guide') showShareGuide.value = true
}

// 定时记账：只要启用中的条数，失败就留空，不影响「我的」页其它数据
async function loadRecurring() {
  try {
    const list = await recurringApi.list()
    recSummary.value = { active_count: (list || []).filter((r) => r.is_active).length }
  } catch (e) {
    recSummary.value = null
  }
}

onMounted(() => {
  load()
  loadAi()
  loadRecurring()
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
      <div v-if="VIP_ENABLED" class="menu-item" @click="router.push('/member')">
        <span class="menu-icon">👑</span>
        <span class="menu-text">会员中心</span>
        <span class="menu-value" :class="{ 'vip-on': vipInfo?.is_vip }">{{ vipText }}</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 智能分析：界面直接配大模型，保存即生效；不配则走本地规则引擎 -->
    <div class="menu-section">
      <div class="menu-title">智能分析</div>
      <div class="menu-item" @click="toggleAI">
        <span class="menu-icon">🤖</span>
        <span class="menu-main">
          <span class="menu-text">AI 智能分析</span>
          <!-- 服务器 .env 配置：只读，说明来源避免用户点了没反应 -->
          <span v-if="aiFromEnv" class="menu-desc">
            由服务器 .env 配置，界面不可修改
          </span>
          <!-- 未配置时说明「现在走本地」，配好就不再解释，避免和开关状态重复 -->
          <span v-else-if="!aiConfigured" class="menu-desc">
            未配置大模型，报告页自动改用本地规则分析；点右侧开关即可填写
          </span>
          <!-- 已启用且表单收起时，给一个改配置的入口；关掉开关就一并消失 -->
          <span
            v-else-if="useAI && !showAiForm"
            class="menu-desc menu-link"
            @click.stop="showAiForm = true"
          >修改配置</span>
        </span>
        <span class="menu-value">{{ aiStateText }}</span>
        <!--
          绿色只取决于「用户是否已打开」。
          之前还要求 aiConfigured，没配 Key 时开关永远灰着点不动，
          而用户点它本意就是要用 AI，应当立刻变绿并弹出配置。
        -->
        <span
          class="switch"
          :class="{ on: aiSwitchOn }"
          @click.stop="toggleAI"
        >
          <span class="switch-dot"></span>
        </span>
      </div>
      <!--
        开关即配置入口：打开开关直接展开配置表单，关闭则收起。
        不再额外放「大模型设置」行——同一件事占两个位置会让层级变乱。
      -->
      <div v-if="aiMsg" class="ai-msg">{{ aiMsg }}</div>

      <div v-if="showAiForm && !aiFromEnv" class="ai-form">
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
      <!-- 定时记账：菜单上直接显示启用中的规则数 -->
      <div class="menu-item" @click="router.push('/recurring')">
        <span class="menu-icon">⏰</span>
        <span class="menu-text">定时记账</span>
        <span class="menu-value">{{ recText }}</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 家庭管理 -->
    <div class="menu-section">
      <div class="menu-title">家庭管理</div>
      <!-- 「邀请成员」与「家庭成员」都在 family 页，合并为一行：
           邀请是成员管理里的一个操作，不必单独占入口 -->
      <div class="menu-item" @click="router.push('/family')">
        <span class="menu-icon">👥</span>
        <span class="menu-text">家庭成员与邀请</span>
        <span class="menu-value">{{ inviteText === '已满' ? '已满' : memberCountText }}</span>
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
      <!-- 分享给好友：优先调系统分享面板（可直接选微信），微信内则引导点右上角 -->
      <div class="menu-item" @click="handleShare">
        <span class="menu-icon">📢</span>
        <span class="menu-text">分享给好友</span>
        <span class="menu-arrow">›</span>
      </div>
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
      <!-- 账号打通：H5 用手机号、小程序用微信，两把钥匙绑在同一账号上才算打通 -->
      <div class="menu-item">
        <span class="menu-icon">📱</span>
        <span class="menu-main">
          <span class="menu-text">手机号</span>
          <span class="menu-desc">网页版登录账号</span>
        </span>
        <span class="menu-value">{{ maskedPhone }}</span>
      </div>
      <div class="menu-item" @click="onWechatBindTip">
        <span class="menu-icon">💬</span>
        <span class="menu-main">
          <span class="menu-text">微信</span>
          <span class="menu-desc">{{ hasWechat ? '已绑定，可微信一键登录' : '去小程序「我的」绑定' }}</span>
        </span>
        <span class="menu-value">{{ hasWechat ? '已绑定' : '未绑定' }}</span>
      </div>
      <div class="menu-item" @click="openPwd">
        <span class="menu-icon">🔑</span>
        <span class="menu-text">{{ pwdTitle }}</span>
        <span class="menu-value">{{ pwdText }}</span>
        <span class="menu-arrow">{{ showPwdForm ? '⌃' : '›' }}</span>
      </div>
      <div v-if="showPwdForm" class="ai-form">
        <!-- 已登录状态直接改密码，不再要求输入原密码：少一步，也免得用户忘了旧密码就卡住 -->
        <div class="ai-field">
          <label>新密码</label>
          <input v-model="pwdForm.new_password" type="password" placeholder="字母+数字，至少 6 位" />
        </div>
        <div class="ai-field">
          <label>确认新密码</label>
          <input v-model="pwdForm.confirm_password" type="password" placeholder="再输入一次新密码" />
        </div>
        <div v-if="pwdMsg" class="ai-msg">{{ pwdMsg }}</div>
        <div class="ai-actions">
          <button class="ai-btn primary" :disabled="pwdSaving" @click="savePwd">
            {{ pwdSaving ? '保存中…' : '保存' }}
          </button>
        </div>
        <div class="ai-note">
          密码用于「手机号 + 密码」登录。若你是在小程序用微信注册的，还需要先在小程序里绑定手机号，
          否则网页版认不出这个账号。忘记密码只能在服务器执行命令行重置。
        </div>
      </div>
      <!-- 管理后台：只有 is_staff 可见，普通用户在页面上不会看到这一行 -->
      <div v-if="auth.user?.is_staff" class="menu-item" @click="router.push('/console')">
        <span class="menu-icon">🛠</span>
        <span class="menu-main">
          <span class="menu-text">管理后台</span>
          <span class="menu-desc">账号 · 会员 · 定时任务</span>
        </span>
        <span class="menu-arrow">›</span>
      </div>
      <div class="menu-item" @click="onLogout">
        <span class="menu-icon">🚪</span>
        <span class="menu-text text-expense">退出登录</span>
        <span class="menu-arrow">›</span>
      </div>
    </div>

    <!-- 微信内分享引导：自定义卡片要认证服务号，这里如实引导点右上角 -->
    <div v-if="showShareGuide" class="share-guide" @click="showShareGuide = false">
      <div class="sg-box" @click.stop>
        <div class="sg-arrow">↗</div>
        <div class="sg-title">点击右上角 ⋯ 分享</div>
        <div class="sg-step">
          自定义分享卡片需要已认证的公众号，当前还没有接。你可以在弹出菜单里选「发送给朋友」或「分享到朋友圈」。
        </div>
        <div class="sg-ok" @click="showShareGuide = false">知道了</div>
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

/* 微信内分享引导遮罩 */
.share-guide {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.sg-box {
  width: 82%;
  max-width: 320px;
  background: #fff;
  border-radius: 14px;
  padding: 22px 20px 16px;
  text-align: center;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
}
.sg-arrow {
  font-size: 30px;
  line-height: 1;
  margin-bottom: 6px;
  text-align: right;
  color: #26215c;
}
.sg-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
.sg-step {
  font-size: 13px;
  color: #888;
  line-height: 1.6;
  margin-bottom: 16px;
}
.sg-ok {
  padding: 10px 0;
  border-radius: 8px;
  background: #26215c;
  color: #fff;
  font-size: 14px;
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
.menu-value.vip-on {
  color: #a1791b;
  font-weight: 600;
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
/* 主文案 + 次要说明的纵向容器：说明文字长，必须允许折行 */
.menu-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.menu-main .menu-text {
  flex: none;
}
.menu-desc {
  font-size: 11px;
  color: #888780;
  line-height: 1.5;
  white-space: normal;
}
/* 作为「可点」的次要链接用：主色 + 下划线点位，和纯说明文字区分 */
.menu-link {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
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
/* 打开态用绿色：绿色在此页没有其它语义占用，一眼能区分「已启用」与「已关闭」；
   复用全局 --income 色值，避免另起一个绿 */
.switch.on {
  background: var(--income);
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