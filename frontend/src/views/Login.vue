<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const phone = ref('13800138000')
const password = ref('test123456')
const loading = ref(false)
const error = ref('')

async function onLogin() {
  if (!phone.value || !password.value) {
    error.value = '请输入手机号和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login({ phone: phone.value, password: password.value })
    // 带 redirect 时回原目标页（例如从邀请链接被拦来登录）
    router.replace(route.query.redirect || '/')
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
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
      <div class="field">
        <label>手机号</label>
        <input v-model="phone" type="tel" maxlength="11" placeholder="请输入手机号" />
      </div>
      <div class="field">
        <label>密码</label>
        <input v-model="password" type="password" placeholder="请输入密码" @keyup.enter="onLogin" />
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="btn btn-primary" :disabled="loading" @click="onLogin">
        {{ loading ? '登录中…' : '登 录' }}
      </button>
      <p class="hint">演示账号：13800138000 / test123456</p>
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
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 20px;
}
</style>