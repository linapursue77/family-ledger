<script setup>
import { computed, onUnmounted, ref } from 'vue'
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

const isRegister = computed(() => mode.value === 'register')
const isForgot = computed(() => mode.value === 'forgot')

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
      </template>
      <p v-if="isRegister" class="note">
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

</style>