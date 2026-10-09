<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref('login') // login | register
const phone = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

// 注册专用字段：确认密码、称呼、账本（注册即建家庭，本人就是主账号）
const confirmPassword = ref('')
const nickname = ref('')
const bookType = ref('husband')

const isRegister = computed(() => mode.value === 'register')

function switchMode(next) {
  if (mode.value === next) return
  mode.value = next
  error.value = ''
  confirmPassword.value = ''
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
  if (password.value.length < 6) {
    error.value = '密码至少 6 位'
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
      book_type: bookType.value,
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
      <div class="brand-name">家庭财务通</div>
      <div class="brand-sub">夫妻共同记账 · 平衡透明与隐私</div>
    </div>
    <div class="form card">
      <div class="tabs">
        <span :class="{ on: !isRegister }" @click="switchMode('login')">登录</span>
        <span :class="{ on: isRegister }" @click="switchMode('register')">注册</span>
      </div>

      <div class="field">
        <label>手机号</label>
        <input v-model="phone" type="tel" maxlength="11" placeholder="请输入手机号" />
      </div>
      <div class="field">
        <label>密码</label>
        <input
          v-model="password"
          type="password"
          :placeholder="isRegister ? '请设置密码（至少 6 位）' : '请输入密码'"
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
          <input v-model="nickname" maxlength="20" placeholder="对方看到的称呼，如：老婆" />
        </div>
        <div class="field">
          <label>我的账本</label>
          <div class="book-pick">
            <span
              class="bchip"
              :class="{ on: bookType === 'husband' }"
              @click="bookType = 'husband'"
              >老公账本</span
            >
            <span class="bchip" :class="{ on: bookType === 'wife' }" @click="bookType = 'wife'"
              >老婆账本</span
            >
          </div>
        </div>
      </template>

      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn btn-primary" :disabled="loading" @click="onSubmit">
        {{ loading ? (isRegister ? '注册中…' : '登录中…') : isRegister ? '注册并进入' : '登 录' }}
      </button>
      <p class="hint" @click="switchMode(isRegister ? 'login' : 'register')">
        {{ isRegister ? '已有账号？去登录' : '还没有账号？去注册' }}
      </p>
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
.hint {
  text-align: center;
  font-size: 13px;
  color: var(--primary, #534ab7);
  margin-top: 20px;
  cursor: pointer;
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
/* 账本二选一 */
.book-pick {
  display: flex;
  gap: 10px;
}
.bchip {
  flex: 1;
  text-align: center;
  font-size: 13px;
  padding: 10px 0;
  border-radius: var(--radius-btn);
  border: 1px solid var(--border);
  background: #fdfdfb;
  color: var(--text-sub);
  cursor: pointer;
}
.bchip.on {
  background: #eeedfe;
  border-color: #7f77dd;
  color: #534ab7;
  font-weight: 600;
}
</style>