<script setup>
import { ref, onMounted } from 'vue'
import { consoleApi } from '@/api'
import { toast } from '@/utils/toast'

const loading = ref(true)
const schedules = ref([])
const recurring = ref({ items: [], total: 0, active: 0, has_error: 0 })
const acting = ref('')

async function load() {
  loading.value = true
  try {
    const [s, r] = await Promise.all([consoleApi.schedules(), consoleApi.recurring()])
    schedules.value = s || []
    recurring.value = r || { items: [], total: 0, active: 0, has_error: 0 }
  } catch (e) {
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function runNow(s) {
  acting.value = `run-${s.id}`
  try {
    await consoleApi.runSchedule(s.id)
    toast('已提交执行，3 秒后自动刷新')
    setTimeout(load, 3000)
  } catch (e) {
    toast(e.message || '执行失败')
  } finally {
    acting.value = ''
  }
}

async function toggle(s) {
  acting.value = `toggle-${s.id}`
  try {
    const res = await consoleApi.toggleSchedule(s.id, !s.enabled)
    toast(s.enabled ? '已停用' : `已启用，下次 ${res.next_run}`)
    await load()
  } catch (e) {
    toast(e.message || '操作失败')
  } finally {
    acting.value = ''
  }
}

function typeText(t) {
  return { D: '每天', H: '每小时', W: '每周', M: '每月', C: 'Cron', O: '仅一次' }[t] || t
}

onMounted(load)
</script>

<template>
  <div class="console-page">
    <div class="sec-title">
      服务端定时任务
      <span class="sub">由 qcluster 进程驱动，停掉它任务就不会执行</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <template v-else>
      <div v-for="s in schedules" :key="s.id" class="task-card">
        <div class="task-head">
          <span class="task-name">{{ s.name }}</span>
          <span class="tag info">{{ typeText(s.schedule_type) }}</span>
          <span class="tag" :class="s.enabled ? 'ok' : 'off'">
            {{ s.enabled ? '启用中' : '已停用' }}
          </span>
          <span v-if="s.last_task && !s.last_task.success" class="tag err">上次失败</span>
          <div style="margin-left: auto" class="row-ops">
            <button class="btn ghost" :disabled="acting === 'run-' + s.id" @click="runNow(s)">
              {{ acting === 'run-' + s.id ? '提交中…' : '立即执行' }}
            </button>
            <button
              class="btn"
              :class="{ danger: s.enabled }"
              :disabled="acting === 'toggle-' + s.id"
              @click="toggle(s)"
            >
              {{ s.enabled ? '停用' : '启用' }}
            </button>
          </div>
        </div>

        <div class="task-func">{{ s.func }}</div>

        <div class="task-meta">
          <span>下次执行：<b>{{ s.enabled ? s.next_run : '—' }}</b></span>
          <span v-if="s.last_task">
            上次执行：{{ s.last_task.started }}
            <span :style="{ color: s.last_task.success ? 'var(--income)' : 'var(--expense)' }">
              {{ s.last_task.success ? '成功' : '失败' }}
            </span>
          </span>
          <span v-else>还没有执行记录</span>
        </div>

        <div v-if="s.last_task && s.last_task.result" class="task-result">
          结果：{{ s.last_task.result }}
        </div>
      </div>

      <div v-if="!schedules.length" class="empty">
        没有注册定时任务。执行 <code>python manage.py setup_schedules</code> 后再刷新。
      </div>

      <div class="tip-line">
        「立即执行」只是把任务投递到队列，真正的执行者仍是 qcluster。若点了没反应，
        先确认服务器上 qcluster 容器 / 进程在运行。
      </div>

      <!-- ---------------------------------------------------- 周期记账规则 -->
      <div class="sec-title" style="margin-top: 30px">
        用户定时记账规则
        <span class="sub">
          共 {{ recurring.total }} 条 · 启用 {{ recurring.active }} 条
          <span v-if="recurring.has_error" style="color: var(--expense)">
            · {{ recurring.has_error }} 条有错误
          </span>
        </span>
      </div>

      <div v-if="!recurring.items.length" class="empty">还没有用户创建定时记账规则</div>

      <div v-else class="table-wrap">
        <table class="dt">
          <thead>
            <tr>
              <th>规则</th>
              <th>用户 / 家庭</th>
              <th>频率</th>
              <th>金额</th>
              <th>下次执行</th>
              <th>已生成</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recurring.items" :key="r.id">
              <td>
                <div class="cell-main">{{ r.name }}</div>
                <div v-if="r.last_error" class="cell-sub" style="color: var(--expense)">
                  {{ r.last_error }}
                </div>
              </td>
              <td>
                <div>{{ r.user }}</div>
                <div class="cell-sub">{{ r.family }}</div>
              </td>
              <td>{{ r.schedule_text }}</td>
              <td :style="{ color: r.type === 'income' ? 'var(--income)' : 'var(--expense)' }">
                {{ r.type === 'income' ? '+' : '-' }}¥{{ r.amount.toFixed(2) }}
              </td>
              <td>{{ r.next_run }}</td>
              <td>
                {{ r.run_count }} 笔
                <div v-if="r.last_run_at" class="cell-sub">{{ r.last_run_at }}</div>
              </td>
              <td>
                <span class="tag" :class="r.is_active ? 'ok' : 'off'">
                  {{ r.is_active ? '启用' : '停用' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
