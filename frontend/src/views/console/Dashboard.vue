<script setup>
import { ref, computed, onMounted } from 'vue'
import { consoleApi } from '@/api'

const loading = ref(true)
const data = ref(null)
const error = ref('')

function fmt(n) {
  return Number(n || 0).toLocaleString('zh-CN')
}

// 条形宽度按当期最大值归一化
const trendMax = computed(() => {
  const rows = data.value?.trend || []
  return Math.max(1, ...rows.map((r) => r.transactions))
})

function barWidth(v) {
  if (!v) return '0%'
  return `${Math.max(Math.round((Number(v) / trendMax.value) * 100), 3)}%`
}

function shortDay(d) {
  return (d || '').slice(5)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await consoleApi.overview()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="console-page">
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty">{{ error }}</div>

    <template v-else-if="data">
      <div class="sec-title">平台概览 <span class="sub">数据实时读取，刷新即最新</span></div>

      <div class="metric-grid">
        <div class="metric">
          <div class="metric-label">👥 注册用户</div>
          <div class="metric-value">{{ fmt(data.users.total) }}</div>
          <div class="metric-foot">
            今日 <span class="up">+{{ fmt(data.users.today) }}</span> · 本周 +{{ fmt(data.users.week) }}
          </div>
        </div>

        <div class="metric">
          <div class="metric-label">🏠 家庭</div>
          <div class="metric-value">{{ fmt(data.families.total) }}</div>
          <div class="metric-foot">多人家庭 {{ fmt(data.families.multi_member) }} 个</div>
        </div>

        <div class="metric">
          <div class="metric-label">⭐ 有效会员</div>
          <div class="metric-value">{{ fmt(data.vip.active) }}</div>
          <div class="metric-foot">
            试用 {{ fmt(data.vip.trial) }} · 本月新增 {{ fmt(data.vip.new_month) }}
          </div>
        </div>

        <div class="metric">
          <div class="metric-label">📒 记账流水</div>
          <div class="metric-value">{{ fmt(data.ledger.transactions) }}</div>
          <div class="metric-foot">本月 {{ fmt(data.ledger.month_transactions) }} 笔</div>
        </div>

        <div class="metric">
          <div class="metric-label">🔥 近 7 天活跃</div>
          <div class="metric-value">{{ fmt(data.users.active_week) }}</div>
          <div class="metric-foot">有记账行为的用户数</div>
        </div>

        <div class="metric">
          <div class="metric-label">⏰ 定时任务</div>
          <div class="metric-value">
            {{ fmt(data.tasks.enabled) }}<small>/ {{ fmt(data.tasks.total) }} 启用</small>
          </div>
          <div class="metric-foot">
            上次执行 {{ data.tasks.last_run_at || '—' }}
            <span v-if="data.tasks.failed_24h" class="down">
              · 24h 失败 {{ data.tasks.failed_24h }}
            </span>
          </div>
        </div>

        <div class="metric">
          <div class="metric-label">🔁 周期记账规则</div>
          <div class="metric-value">
            {{ fmt(data.ledger.recurring_active) }}<small>/ {{ fmt(data.ledger.recurring_rules) }} 启用</small>
          </div>
          <div class="metric-foot">用户自建的定时记账</div>
        </div>

        <div class="metric">
          <div class="metric-label">🚫 停用账号</div>
          <div class="metric-value">{{ fmt(data.users.disabled) }}</div>
          <div class="metric-foot">本月新增 {{ fmt(data.users.month) }} 个账号</div>
        </div>
      </div>

      <div class="sec-title" style="margin-top: 26px">
        近 14 天趋势
        <span class="sub">横条＝每天记账笔数</span>
      </div>

      <div class="panel">
        <div class="trend-list">
          <div v-for="d in data.trend" :key="d.date" class="trend-row">
            <span class="tl-date">{{ shortDay(d.date) }}</span>
            <div class="tl-track">
              <div
                class="tl-bar"
                :class="{ empty: !d.transactions }"
                :style="{ width: barWidth(d.transactions) }"
              ></div>
            </div>
            <span class="tl-val">{{ d.transactions || '—' }}</span>
            <span v-if="d.users" class="tl-new">新注册 +{{ d.users }}</span>
          </div>
        </div>
        <div class="trend-legend">
          <span><i style="background: var(--primary)"></i>当天记账笔数</span>
          <span>
            <i style="background: var(--income)"></i>
            近 14 天新注册 {{ data.trend.reduce((s, x) => s + x.users, 0) }} 人
          </span>
        </div>
        <div class="tip-line">
          横条长度＝当天记账笔数。若长期为空，说明用户没有在记账，而不是统计出错。
        </div>
      </div>
    </template>
  </div>
</template>
