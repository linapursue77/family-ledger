<script setup>
import { ref, reactive, onMounted } from 'vue'
import { consoleApi } from '@/api'
import { toast } from '@/utils/toast'

const loading = ref(true)
const items = ref([])
const pagination = ref({ count: 0, page: 1, total_pages: 1 })
const query = reactive({ q: '', status: '', vip: '', page: 1 })

// 详情抽屉
const detail = ref(null)
const detailLoading = ref(false)

async function load(page) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await consoleApi.users({ ...query })
    items.value = res.items || []
    pagination.value = res.pagination || { count: 0, page: 1, total_pages: 1 }
  } catch (e) {
    items.value = []
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  query.page = 1
  load()
}

async function openDetail(u) {
  detailLoading.value = true
  detail.value = { user: u }
  try {
    detail.value = await consoleApi.user(u.id)
  } catch (e) {
    toast(e.message || '加载详情失败')
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function toggleActive(u) {
  const next = !u.is_active
  if (!next && !window.confirm(`确定停用「${u.nickname || u.phone}」？停用后该账号无法登录。`)) return
  try {
    await consoleApi.updateUser(u.id, { is_active: next })
    toast(next ? '已启用账号' : '已停用账号')
    await load()
    if (detail.value) await openDetail({ id: u.id })
  } catch (e) {
    toast(e.message || '操作失败')
  }
}

async function toggleStaff(u) {
  const next = !u.is_staff
  const tip = next
    ? `把「${u.nickname || u.phone}」设为管理员？TA 将能看到全部用户与会员数据。`
    : `撤销「${u.nickname || u.phone}」的管理员权限？`
  if (!window.confirm(tip)) return
  try {
    await consoleApi.updateUser(u.id, { is_staff: next })
    toast(next ? '已设为管理员' : '已撤销管理员')
    await load()
  } catch (e) {
    toast(e.message || '操作失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="console-page">
    <div class="toolbar">
      <input
        v-model="query.q"
        class="field grow"
        placeholder="搜索手机号 / 昵称"
        @keyup.enter="resetAndLoad"
      />
      <select v-model="query.status" class="field" @change="resetAndLoad">
        <option value="">全部状态</option>
        <option value="active">正常</option>
        <option value="disabled">已停用</option>
      </select>
      <select v-model="query.vip" class="field" @change="resetAndLoad">
        <option value="">全部用户</option>
        <option value="1">仅会员</option>
        <option value="0">非会员</option>
      </select>
      <button class="btn" @click="resetAndLoad">查询</button>
      <span class="cell-sub" style="margin-left: auto">共 {{ pagination.count }} 个账号</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!items.length" class="empty">没有匹配的账号</div>

    <div v-else class="table-wrap">
      <table class="dt">
        <thead>
          <tr>
            <th>账号</th>
            <th>家庭</th>
            <th>会员</th>
            <th>记账</th>
            <th>注册时间</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in items" :key="u.id">
            <td>
              <div class="cell-main">
                {{ u.nickname || '未设置昵称' }}
                <span v-if="u.is_staff" class="tag info">管理员</span>
              </div>
              <div class="cell-sub">{{ u.phone || u.username }}</div>
            </td>
            <td>
              <div>{{ u.family_name || '—' }}</div>
              <div class="cell-sub">
                {{ u.family_role === 'owner' ? '主账号' : u.family_role === 'member' ? '子账号' : '' }}
              </div>
            </td>
            <td>
              <span v-if="u.is_vip" class="tag vip">会员</span>
              <span v-else class="tag off">普通</span>
              <div v-if="u.is_vip" class="cell-sub">至 {{ u.vip_expire_at }}</div>
            </td>
            <td>{{ u.tx_count }} 笔</td>
            <td>
              <div>{{ u.date_joined }}</div>
              <div class="cell-sub">最近登录 {{ u.last_login || '从未' }}</div>
            </td>
            <td>
              <span class="tag" :class="u.is_active ? 'ok' : 'err'">
                {{ u.is_active ? '正常' : '已停用' }}
              </span>
            </td>
            <td>
              <div class="row-ops">
                <span class="op" @click="openDetail(u)">详情</span>
                <span class="op" :class="{ danger: u.is_active }" @click="toggleActive(u)">
                  {{ u.is_active ? '停用' : '启用' }}
                </span>
                <span class="op" @click="toggleStaff(u)">
                  {{ u.is_staff ? '撤销管理员' : '设为管理员' }}
                </span>
              </div>
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

    <!-- ---------------------------------------------------------- 详情抽屉 -->
    <template v-if="detail">
      <div class="drawer-mask" @click="detail = null"></div>
      <div class="drawer">
        <div class="drawer-head">
          <span class="drawer-title">账号详情</span>
          <span class="drawer-close" @click="detail = null">×</span>
        </div>
        <div v-if="detailLoading" class="empty">加载中…</div>

        <template v-else>
          <div class="kv"><span class="k">昵称</span><span class="v">{{ detail.user.nickname || '—' }}</span></div>
          <div class="kv"><span class="k">手机号</span><span class="v">{{ detail.user.phone || '—（微信登录）' }}</span></div>
          <div class="kv"><span class="k">账号 ID</span><span class="v">{{ detail.user.id }}</span></div>
          <div class="kv"><span class="k">注册时间</span><span class="v">{{ detail.user.date_joined }}</span></div>
          <div class="kv"><span class="k">最近登录</span><span class="v">{{ detail.user.last_login || '从未' }}</span></div>
          <div class="kv">
            <span class="k">账号状态</span>
            <span class="v">
              <span class="tag" :class="detail.user.is_active ? 'ok' : 'err'">
                {{ detail.user.is_active ? '正常' : '已停用' }}
              </span>
              <span v-if="detail.user.is_staff" class="tag info" style="margin-left: 6px">管理员</span>
            </span>
          </div>

          <div class="sec-title" style="margin-top: 20px">家庭</div>
          <template v-if="detail.family">
            <div class="kv"><span class="k">家庭名称</span><span class="v">{{ detail.family.name }}</span></div>
            <div class="kv">
              <span class="k">身份</span>
              <span class="v">{{ detail.family.role === 'owner' ? '主账号' : '子账号' }} · 共 {{ detail.family.member_count }} 人</span>
            </div>
            <div class="kv"><span class="k">加入时间</span><span class="v">{{ detail.family.joined_at }}</span></div>
          </template>
          <div v-else class="cell-sub">未加入任何家庭</div>

          <div class="sec-title" style="margin-top: 20px">记账统计</div>
          <div class="kv"><span class="k">累计流水</span><span class="v">{{ detail.stats.tx_count }} 笔</span></div>
          <div class="kv"><span class="k">本月流水</span><span class="v">{{ detail.stats.month_tx_count }} 笔</span></div>
          <div class="kv"><span class="k">账户数</span><span class="v">{{ detail.stats.account_count }} 个</span></div>
          <div class="kv"><span class="k">定时规则</span><span class="v">{{ detail.stats.recurring_count }} 条</span></div>

          <div class="sec-title" style="margin-top: 20px">
            会员记录
            <span class="sub">{{ detail.vip.is_vip ? '当前有效至 ' + detail.vip.expire_at : '当前非会员' }}</span>
          </div>
          <div v-if="!detail.vip.history.length" class="cell-sub">没有开通记录</div>
          <table v-else class="dt" style="min-width: 0">
            <thead>
              <tr><th>套餐</th><th>来源</th><th>有效期</th><th>状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="h in detail.vip.history" :key="h.id">
                <td>{{ h.plan_name || '手动开通' }}</td>
                <td>{{ h.source }}</td>
                <td class="cell-sub">{{ h.start_at }} ~ {{ h.expire_at }}</td>
                <td>
                  <span class="tag" :class="h.is_active ? 'ok' : 'off'">
                    {{ h.is_active ? '有效' : '已过期' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="sec-title" style="margin-top: 20px">最近 10 笔流水</div>
          <div v-if="!detail.recent_transactions.length" class="cell-sub">还没有记账</div>
          <table v-else class="dt" style="min-width: 0">
            <thead>
              <tr><th>日期</th><th>分类</th><th>金额</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in detail.recent_transactions" :key="t.id">
                <td>{{ t.date }}</td>
                <td>{{ t.category || t.merchant || '—' }}</td>
                <td :style="{ color: t.type === 'income' ? 'var(--income)' : 'var(--expense)' }">
                  {{ t.type === 'income' ? '+' : '-' }}¥{{ t.amount.toFixed(2) }}
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </template>
  </div>
</template>
