<script setup>
import { ref, reactive, onMounted } from 'vue'
import { consoleApi } from '@/api'
import { toast } from '@/utils/toast'

const loading = ref(true)
const items = ref([])
const pagination = ref({ count: 0, page: 1, total_pages: 1 })
const query = reactive({ q: '', status: '', page: 1 })

const plans = ref([])
// 赠送表单
const form = reactive({ keyword: '', userId: '', userName: '', planId: '', days: 30 })
const candidates = ref([])
const searching = ref(false)
const granting = ref(false)

async function load(page) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await consoleApi.subscriptions({ ...query })
    items.value = res.items || []
    pagination.value = res.pagination || { count: 0, page: 1, total_pages: 1 }
  } catch (e) {
    items.value = []
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadPlans() {
  try {
    plans.value = (await consoleApi.plans()) || []
  } catch (e) {
    plans.value = []
  }
}

async function searchUser() {
  const kw = form.keyword.trim()
  if (!kw) return toast('请输入手机号或昵称')
  searching.value = true
  candidates.value = []
  try {
    const res = await consoleApi.users({ q: kw, page_size: 10 })
    candidates.value = res.items || []
    if (!candidates.value.length) toast('没有找到匹配的账号')
  } catch (e) {
    toast(e.message || '搜索失败')
  } finally {
    searching.value = false
  }
}

function pick(u) {
  form.userId = u.id
  form.userName = `${u.nickname || '未设置昵称'}（${u.phone || u.username}）`
  candidates.value = []
}

// 选套餐时自动带出天数，避免「选了年卡却只送 30 天」这种不一致
function onPlanChange() {
  const p = plans.value.find((x) => x.id === form.planId)
  if (p) form.days = p.duration_days
}

async function grant() {
  if (!form.userId) return toast('请先选择要开通的账号')
  const days = Number(form.days) || 0
  if (days <= 0) return toast('请填写赠送天数')
  granting.value = true
  try {
    const res = await consoleApi.grantVip({
      user_id: form.userId,
      plan_id: form.planId || null,
      days,
    })
    toast(`已开通，有效期至 ${res.expire_at}`)
    form.userId = ''
    form.userName = ''
    form.keyword = ''
    form.planId = ''
    await load(1)
  } catch (e) {
    toast(e.message || '开通失败')
  } finally {
    granting.value = false
  }
}

async function revoke(s) {
  if (!window.confirm(`撤销「${s.nickname || s.phone}」这条会员记录？此操作不可恢复。`)) return
  try {
    await consoleApi.revokeVip(s.id)
    toast('已撤销')
    await load()
  } catch (e) {
    toast(e.message || '撤销失败')
  }
}

onMounted(() => {
  load()
  loadPlans()
})
</script>

<template>
  <div class="console-page">
    <!-- 手动开通：赠送给试用用户、补偿支付异常都用这一处 -->
    <div class="sec-title">手动开通 / 续期</div>
    <div class="panel" style="margin-bottom: 22px">
      <div class="toolbar" style="margin-bottom: 10px">
        <input
          v-model="form.keyword"
          class="field grow"
          placeholder="输入手机号或昵称找到账号"
          @keyup.enter="searchUser"
        />
        <button class="btn ghost" :disabled="searching" @click="searchUser">
          {{ searching ? '搜索中…' : '查找账号' }}
        </button>
      </div>

      <div v-if="candidates.length" class="table-wrap" style="margin-bottom: 10px">
        <table class="dt" style="min-width: 0">
          <tbody>
            <tr v-for="u in candidates" :key="u.id" style="cursor: pointer" @click="pick(u)">
              <td>
                <div class="cell-main">{{ u.nickname || '未设置昵称' }}</div>
                <div class="cell-sub">{{ u.phone || u.username }}</div>
              </td>
              <td>
                <span v-if="u.is_vip" class="tag vip">已是会员，将顺延</span>
                <span v-else class="tag off">非会员</span>
              </td>
              <td class="cell-sub">点击选择</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="toolbar" style="margin-bottom: 0">
        <input
          class="field grow"
          :value="form.userName"
          placeholder="已选账号（先在上方搜索并点击选择）"
          readonly
        />
        <select v-model="form.planId" class="field" @change="onPlanChange">
          <option value="">按天数赠送</option>
          <option v-for="p in plans" :key="p.id" :value="p.id">
            {{ p.name }}（{{ p.duration_days }} 天）
          </option>
        </select>
        <input v-model="form.days" class="field" type="number" min="1" style="width: 110px" />
        <span class="cell-sub">天</span>
        <button class="btn" :disabled="granting" @click="grant">
          {{ granting ? '提交中…' : '开通' }}
        </button>
      </div>
      <div class="tip-line">
        已有有效会员时会自动顺延，不会覆盖剩余天数。赠送记录来源标记为「管理员赠送」，
        可在下方列表撤销。
      </div>
    </div>

    <div class="sec-title">会员记录 <span class="sub">共 {{ pagination.count }} 条</span></div>

    <div class="toolbar">
      <input
        v-model="query.q"
        class="field grow"
        placeholder="搜索手机号 / 昵称"
        @keyup.enter="load(1)"
      />
      <select v-model="query.status" class="field" @change="load(1)">
        <option value="">全部</option>
        <option value="active">生效中</option>
        <option value="expired">已过期</option>
      </select>
      <button class="btn" @click="load(1)">查询</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!items.length" class="empty">没有会员记录</div>

    <div v-else class="table-wrap">
      <table class="dt">
        <thead>
          <tr>
            <th>用户</th>
            <th>套餐</th>
            <th>来源</th>
            <th>有效期</th>
            <th>剩余</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in items" :key="s.id">
            <td>
              <div class="cell-main">{{ s.nickname || '未设置昵称' }}</div>
              <div class="cell-sub">{{ s.phone || s.user_id }}</div>
            </td>
            <td>{{ s.plan_name }}</td>
            <td>{{ s.source }}</td>
            <td class="cell-sub">{{ s.start_at }} ~ {{ s.expire_at }}</td>
            <td>{{ s.is_active ? s.remain_days + ' 天' : '—' }}</td>
            <td>
              <span class="tag" :class="s.is_active ? 'ok' : 'off'">
                {{ s.is_active ? '生效中' : '已过期' }}
              </span>
            </td>
            <td>
              <span class="op danger" @click="revoke(s)">撤销</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="pagination.total_pages > 1" class="pager">
      <button class="btn ghost" :disabled="query.page <= 1" @click="load(query.page - 1)">
        上一页
      </button>
      <span>{{ pagination.page }} / {{ pagination.total_pages }}</span>
      <button
        class="btn ghost"
        :disabled="query.page >= pagination.total_pages"
        @click="load(query.page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>
