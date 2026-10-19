<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { familyApi } from '@/api'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const token = ref(String(route.query.token || ''))
const loading = ref(true)
const errorText = ref('')
const info = ref(null)
const submitting = ref(false)

// 自绘确认弹层：window.confirm 在预览环境会被吞掉
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

// 邀请里预设的权限，逐条翻译成人话，接受前先看清楚
const PERM_TEXT = {
  report_view: (v) => (v === 'all' ? '查看全家庭的账单与报表' : '仅查看自己账本的报表'),
  account_view: (v) => (v === 'all' ? '查看全部账户与资产' : '仅查看自己的账户'),
  allow_record: (v) => (v ? '可以新增、编辑账单' : '只能看，不能记账'),
  show_private: (v) => (v ? '可以看到标记为私密的账目' : '看不到私密账目'),
  settings_level: (v) => (v === 'full' ? '可管理家庭设置与成员' : '不可管理家庭设置'),
}

const permList = computed(() => {
  const p = info.value?.permissions || {}
  return Object.keys(PERM_TEXT).map((k) => PERM_TEXT[k](p[k]))
})

function fmtDate(v) {
  return String(v || '').slice(0, 10)
}

async function load() {
  loading.value = true
  errorText.value = ''
  try {
    info.value = await familyApi.previewInvite(token.value)
  } catch (e) {
    info.value = null
    errorText.value = e.message || '邀请无效'
  } finally {
    loading.value = false
  }
}

async function accept() {
  const ok = await ask({
    title: `加入「${info.value.family_name}」？`,
    lines: ['加入后你的账单会记在自己的账本里', '权限由主账号设定，之后可以调整'],
    okText: '确认加入',
  })
  if (!ok) return
  submitting.value = true
  try {
    await familyApi.acceptInvite(token.value)
    await auth.fetchMe()
    router.replace('/mine')
  } catch (e) {
    errorText.value = e.message || '接受失败'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  if (!token.value) {
    errorText.value = '缺少邀请码'
    loading.value = false
    return
  }
  if (auth.isLogin) load()
  else loading.value = false
})
</script>

<template>
  <div class="join-page">
    <div v-if="loading" class="empty">正在读取邀请…</div>

    <div v-else-if="!auth.isLogin" class="card j-card">
      <div class="j-icon">🔑</div>
      <div class="j-title">需要登录后接受邀请</div>
      <!-- 带上 invite：登录页据此把「注册」也接到邀请上，
           否则新用户点注册会自己建家庭变成主账号，反过来卡住加入流程 -->
      <div class="j-desc">已有账号可直接登录；没有账号点注册，注册后会自动加入这个家庭。</div>
      <button class="btn btn-primary" @click="router.push(`/login?invite=${encodeURIComponent(token)}`)">
        去登录 / 注册
      </button>
      <button class="btn j-decline" @click="router.replace('/')">返回首页</button>
    </div>

    <div v-else-if="errorText" class="card j-card">
      <div class="j-icon">⚠️</div>
      <div class="j-title">无法加入</div>
      <div class="j-desc">{{ errorText }}</div>
      <button class="btn btn-primary" @click="router.replace('/')">返回首页</button>
    </div>

    <div v-else-if="info" class="card j-card">
      <div class="j-icon">👨‍👩‍👧</div>
      <div class="j-title">{{ info.inviter }} 邀请你加入</div>
      <div class="j-family">「{{ info.family_name }}」</div>
      <div class="j-meta">
        {{ fmtDate(info.expires_at) }} 前有效 · 当前 {{ info.member_count }}/{{ info.member_limit }} 位成员
      </div>

      <div class="j-sec">加入后你可以</div>
      <div class="j-perms">
        <div v-for="t in permList" :key="t" class="j-perm">
          <span class="j-dot"></span>{{ t }}
        </div>
      </div>
      <div class="j-note">权限可在家庭管理中随时调整；加入后你的账单会记在独立账本里。</div>

      <button class="btn btn-primary" :disabled="submitting" @click="accept">
        {{ submitting ? '加入中…' : '接受邀请并加入' }}
      </button>
      <button class="btn j-decline" @click="router.replace('/')">暂不加入</button>
    </div>

    <ConfirmSheet
      :visible="confirmState.show"
      :title="confirmState.title"
      :lines="confirmState.lines"
      :ok-text="confirmState.okText"
      @ok="answerConfirm(true)"
      @cancel="answerConfirm(false)"
    />
  </div>
</template>

<style scoped>
.join-page {
  min-height: 100vh;
  padding: 48px 16px calc(var(--nav-h, 60px) + env(safe-area-inset-bottom) + 16px);
  background: #faf9f6;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}
.j-card {
  width: 100%;
  padding: 26px 20px 20px;
  text-align: center;
}
.j-icon {
  font-size: 40px;
  margin-bottom: 10px;
}
.j-title {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}
.j-family {
  margin-top: 6px;
  font-size: var(--font-num);
  font-weight: 700;
  color: var(--primary-dark);
}
.j-desc {
  margin-top: 10px;
  font-size: var(--font-sm);
  color: var(--text-sub);
  line-height: 1.7;
}
.j-meta {
  margin-top: 8px;
  font-size: var(--font-xs);
  color: var(--text-muted);
}
.j-sec {
  margin: 18px 0 8px;
  text-align: left;
  font-size: var(--font-sm);
  font-weight: 700;
  color: var(--text-main);
}
.j-perms {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.j-perm {
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  font-size: var(--font-sm);
  color: var(--text-body);
  background: #f7f6f2;
  border-radius: var(--radius-btn);
  padding: 9px 12px;
}
.j-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
}
.j-note {
  margin: 10px 0 16px;
  text-align: left;
  font-size: var(--font-xs);
  color: var(--text-muted);
  line-height: 1.6;
}
.j-decline {
  margin-top: 8px;
  background: transparent;
  color: var(--text-muted);
  font-weight: 500;
}
.empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted);
  font-size: var(--font-sm);
}
</style>
