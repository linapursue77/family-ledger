<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api'

// 密码规则：字母+数字组合，不低于 6 位。与后端 validators.LetterAndDigitValidator 保持一致；
// 后端仍是权威校验，这里只做即时提示，免去一次无谓的请求往返。
const PASSWORD_RULE = /^(?=.*[a-zA-Z])(?=.*\d).{6,}$/
const PASSWORD_HINT = '密码需同时包含字母和数字，且不低于 6 位'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref('login') // login | register | forgot
const phone = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('') // 成功提示（绿色），与 error 互斥

// 注册专用字段：确认密码、称呼（注册即建家庭，本人就是主账号，账本由后端按顺位分配）
const confirmPassword = ref('')
const nickname = ref('')

// 忘记密码：手机号 + 验证码 → 新密码
const forgotPhone = ref('')
const forgotCode = ref('')
const forgotPassword = ref('')
const forgotConfirm = ref('')
const forgotSending = ref(false)
const forgotCountdown = ref(0)
let countdownTimer = null

// 微信一键登录（公众号网页授权）：只在微信内置浏览器里可用，且后端必须配了 appid / secret
const isWechat = /micromessenger/i.test(navigator.userAgent || '')
const wxEnabled = ref(false)
const wxBusy = ref(false)

const isRegister = computed(() => mode.value === 'register')
const isForgot = computed(() => mode.value === 'forgot')

/**
 * 邀请注册：从分享链接进来会带 ?invite=xxx。
 * 带上它注册，后端就不建「自己的家庭」，而是直接加入邀请方家庭成为子账号；
 * 不带的走原逻辑（建家庭 + 主账号）。少了这一步，被邀请人注册后会变成
 * 自己家庭的主账号，之后接受邀请被「已在家庭中」挡住。
 */
const inviteToken = computed(() => String(route.query.invite || ''))

function switchMode(next) {
  if (mode.value === next) return
  mode.value = next
  error.value = ''
  notice.value = ''
  confirmPassword.value = ''
  if (next !== 'forgot') stopCountdown()
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}
onUnmounted(stopCountdown)

/** 把地址栏里的授权参数抹掉：留着的话刷新一次就会拿已用掉的 ticket 报错 */
function stripCallbackParams() {
  const params = new URLSearchParams(window.location.search)
  if (!params.has('mp_ticket') && !params.has('mp_error')) return null
  const picked = { ticket: params.get('mp_ticket'), error: params.get('mp_error') }
  params.delete('mp_ticket')
  params.delete('mp_error')
  const query = params.toString()
  history.replaceState(
    null,
    '',
    `${location.pathname}${query ? '?' + query : ''}${location.hash}`,
  )
  return picked
}

onMounted(async () => {
  const cb = stripCallbackParams()
  if (cb?.error) {
    error.value = cb.error
    return
  }
  if (cb?.ticket) {
    // 授权回来：一次性 ticket 换 token，换完即登录
    wxBusy.value = true
    try {
      const d = await authApi.wechatMpTicket(cb.ticket)
      await auth.applyLoginData(d)
      router.replace(route.query.redirect || '/')
    } catch (e) {
      error.value = e.message || '微信登录失败，请重试'
    } finally {
      wxBusy.value = false
    }
    return
  }
  if (!isWechat) return
  try {
    const d = await authApi.wechatMpConfig()
    wxEnabled.value = !!d?.enabled
  } catch {
    wxEnabled.value = false
  }
})

/** 跳公众号授权：授权完微信带 code 回后端，后端再跳回本站并带上一次性 ticket */
function wechatLogin() {
  const back = route.query.redirect
    ? `/#/login?redirect=${encodeURIComponent(String(route.query.redirect))}`
    : '/#/login'
  wxBusy.value = true
  window.location.href = authApi.wechatMpAuthorizeUrl(back)
}

async function sendCode() {
  if (!/^1[3-9]\d{9}$/.test(forgotPhone.value)) {
    error.value = '请输入正确的 11 位手机号'
    return
  }
  if (forgotCountdown.value > 0) return
  forgotSending.value = true
  error.value = ''
  notice.value = ''
  try {
    await authApi.sendSmsCode({ phone: forgotPhone.value, scene: 'reset_password' })
    // 统一成功文案：不区分手机号是否注册，防用户枚举
    notice.value = '验证码已发送，请注意查收'
    forgotCountdown.value = 60
    countdownTimer = setInterval(() => {
      if (--forgotCountdown.value <= 0) stopCountdown()
    }, 1000)
  } catch (e) {
    error.value = e.message || '发送失败，请稍后再试'
  } finally {
    forgotSending.value = false
  }
}

async function onReset() {
  if (!/^1[3-9]\d{9}$/.test(forgotPhone.value)) {
    error.value = '请输入正确的 11 位手机号'
    return
  }
  if (!forgotCode.value) {
    error.value = '请输入验证码'
    return
  }
  if (!PASSWORD_RULE.test(forgotPassword.value)) {
    error.value = PASSWORD_HINT
    return
  }
  if (forgotPassword.value !== forgotConfirm.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    await authApi.resetPassword({
      phone: forgotPhone.value,
      code: forgotCode.value,
      new_password: forgotPassword.value,
      confirm_password: forgotConfirm.value,
    })
    stopCountdown()
    // 重置成功直接带手机号回登录页，少输一次
    phone.value = forgotPhone.value
    password.value = ''
    mode.value = 'login'
    notice.value = '密码已重置，请用新密码登录'
  } catch (e) {
    error.value = e.message || '重置失败'
  } finally {
    loading.value = false
  }
}

/** 跳到登录后该去的页面：注册完成一律回首页，登录优先回 redirect 目标 */
function goHome() {
  // 邀请注册已在后端完成加入，直接进家庭页看结果；
  // 登录态下仍需回 join 让用户确认，所以只有注册这条路跳过 join
  if (isRegister.value && inviteToken.value) {
    router.replace('/family')
    return
  }
  router.replace(isRegister.value ? '/' : route.query.redirect || '/')
}

async function onLogin() {
  if (!phone.value || !password.value) {
    error.value = '请输入手机号和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login({ phone: phone.value, password: password.value })
    goHome()
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  if (!/^1[3-9]\d{9}$/.test(phone.value)) {
    error.value = '请输入正确的 11 位手机号'
    return
  }
  if (!PASSWORD_RULE.test(password.value)) {
    error.value = PASSWORD_HINT
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.register({
      phone: phone.value,
      password: password.value,
      nickname: nickname.value.trim(),
      // 带邀请码注册 → 后端直接加入邀请方家庭，不建自己的家庭
      invite_token: inviteToken.value,
    })
    goHome()
  } catch (e) {
    error.value = e.message || '注册失败'
  } finally {
    loading.value = false
  }
}

function onSubmit() {
  isRegister.value ? onRegister() : onLogin()
}
</script>

<template>
  <div class="login-page">
    <div class="brand">
      <div class="brand-icon">💰</div>
      <div class="brand-name">钱来钱往记账</div>
      <div class="brand-sub">一起记账 · 平衡透明与隐私</div>
    </div>
    <div class="form card">
      <div class="tabs">
        <span :class="{ on: !isRegister && !isForgot }" @click="switchMode('login')">登录</span>
        <span :class="{ on: isRegister }" @click="switchMode('register')">注册</span>
        <span :class="{ on: isForgot }" @click="switchMode('forgot')">忘记密码</span>
      </div>

      <!-- 忘记密码：手机号 + 验证码 → 新密码 -->
      <template v-if="isForgot">
        <div class="field">
          <label>手机号</label>
          <input v-model="forgotPhone" type="tel" maxlength="11" placeholder="请输入注册时用的手机号" />
        </div>
        <div class="field">
          <label>验证码</label>
          <div class="code-row">
            <input v-model="forgotCode" type="text" inputmode="numeric" maxlength="6" placeholder="6 位验证码" />
            <button
              class="code-btn"
              :disabled="forgotCountdown > 0 || forgotSending"
              @click="sendCode"
            >
              {{ forgotCountdown > 0 ? `${forgotCountdown}s` : forgotSending ? '发送中…' : '获取验证码' }}
            </button>
          </div>
        </div>
        <div class="field">
          <label>新密码</label>
          <input v-model="forgotPassword" type="password" placeholder="字母+数字，至少 6 位" />
        </div>
        <div class="field">
          <label>确认新密码</label>
          <input v-model="forgotConfirm" type="password" placeholder="再输入一次新密码" />
        </div>
        <p v-if="notice" class="notice">{{ notice }}</p>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn btn-primary" :disabled="loading" @click="onReset">
          {{ loading ? '重置中…' : '重置密码' }}
        </button>
        <p class="hint" @click="switchMode('login')">想起来了？去登录</p>
        <p class="note">
          验证码 5 分钟内有效；若未收到，请检查手机号是否为注册时使用的号码。
        </p>
      </template>

      <template v-if="!isForgot">
      <div class="field">
        <label>手机号</label>
        <input v-model="phone" type="tel" maxlength="11" placeholder="请输入手机号" />
      </div>
      <div class="field">
        <label>密码</label>
        <input
          v-model="password"
          type="password"
          :placeholder="isRegister ? '请设置密码（字母+数字，至少 6 位）' : '请输入密码'"
          @keyup.enter="onSubmit"
        />
      </div>
      <template v-if="isRegister">
        <div class="field">
          <label>确认密码</label>
          <input
            v-model="confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            @keyup.enter="onSubmit"
          />
        </div>
        <div class="field">
          <label>称呼<span class="opt">选填</span></label>
          <input v-model="nickname" maxlength="20" placeholder="家人看到的称呼，如：小林" />
        </div>
      </template>

      <p v-if="notice" class="notice">{{ notice }}</p>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? (isRegister ? '注册中…' : '登录中…') : isRegister ? '注册并进入' : '登 录' }}
      </button>
      <p class="hint" @click="switchMode(isRegister ? 'login' : 'register')">
        {{ isRegister ? '已有账号？去登录' : '还没有账号？去注册' }}
      </p>
      <p v-if="!isRegister" class="hint forgot-link" @click="switchMode('forgot')">
        忘记密码？
      </p>

      <!-- 微信一键登录：公众号网页授权，仅在微信内打开且后端已配置时显示 -->
      <template v-if="wxEnabled">
        <div class="wx-entry">
          <div class="divider"><span>或</span></div>
          <button v-if="isWechat" class="btn btn-wechat" :disabled="wxBusy" @click="wechatLogin">
            <span class="wx-icon">💬</span>{{ wxBusy ? '微信登录中…' : '微信一键登录' }}
          </button>
          <p v-else class="wx-tip">请在微信中打开本页，即可使用微信一键登录</p>
        </div>
      </template>
      </template>
      <!-- 邀请注册与普通注册的结果完全不同，提示要分开写，否则用户以为自己是主账号 -->
      <p v-if="isRegister && inviteToken" class="note note-invite">
        🔑 你正在接受家庭邀请：注册后会直接加入对方的家庭，成为子账号，不会创建你自己的家庭。
      </p>
      <p v-else-if="isRegister" class="note">
        注册后会自动建一个家庭，你就是主账号；之后可在「我的 → 主账号设置」里把它转让给对方。
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 32px;
  background: linear-gradient(160deg, #eeedfe 0%, #f1efe8 60%);
}
.brand {
  text-align: center;
  margin-bottom: 48px;
}
.brand-icon {
  font-size: 56px;
}
.brand-name {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-main);
  margin-top: 10px;
}
.brand-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 8px;
}
.form {
  padding: 28px 24px;
}
.field {
  margin-bottom: 20px;
}
.field label {
  display: block;
  font-size: 13px;
  color: var(--text-sub);
  margin-bottom: 8px;
}
.field input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-btn);
  padding: 14px;
  font-size: 15px;
  background: #fafaf8;
}
.error {
  color: var(--expense);
  font-size: 13px;
  margin-bottom: 12px;
}
.notice {
  color: var(--income, #1d9e75);
  font-size: 13px;
  margin-bottom: 12px;
}
/* 验证码行：输入框 + 获取按钮 */
.code-row {
  display: flex;
  gap: 10px;
}
.code-row input {
  flex: 1;
  min-width: 0;
}
.code-btn {
  flex: none;
  padding: 0 14px;
  font-size: 13px;
  color: #534ab7;
  background: #eeedfe;
  border: 1px solid #d5d0f5;
  border-radius: var(--radius-btn);
  white-space: nowrap;
}
.code-btn:disabled {
  color: var(--text-muted);
  background: #f1efe8;
  border-color: var(--border);
}
.hint {
  text-align: center;
  font-size: 13px;
  color: var(--primary, #534ab7);
  margin-top: 20px;
  cursor: pointer;
}
.forgot-link {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-muted);
}
.note {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.6;
  margin-top: 10px;
  text-align: center;
}
/* 邀请注册提示：用主色底突出，和普通说明区分开 */
.note-invite {
  color: #534ab7;
  background: #eeedfe;
  padding: 8px 10px;
  border-radius: 8px;
}
/* 登录 / 注册切换 */
.tabs {
  display: flex;
  gap: 20px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--border);
}
.tabs span {
  position: relative;
  padding: 0 2px 10px;
  font-size: 15px;
  color: var(--text-muted);
  cursor: pointer;
}
.tabs span.on {
  color: var(--text-main);
  font-weight: 600;
}
.tabs span.on::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: #534ab7;
}
.opt {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: 6px;
}
/* 微信一键登录：分隔线 + 微信绿按钮 */
.wx-entry {
  margin-top: 24px;
}
.divider {
  display: flex;
  align-items: center;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 18px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.divider span {
  padding: 0 12px;
}
.btn-wechat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  background: #07c160;
  color: #fff;
}
.btn-wechat:disabled {
  opacity: 0.6;
}
.wx-icon {
  font-size: 17px;
  line-height: 1;
}
.wx-tip {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.6;
}

</style>