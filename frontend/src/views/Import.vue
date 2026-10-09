<script setup>
import { ref, onMounted } from 'vue'
import { importApi, accountApi } from '@/api'
import { toast } from '@/utils/toast'
import { yuan } from '@/utils/money'

const platform = ref('wechat')
const file = ref(null)
const uploading = ref(false)
const taskId = ref('')
const rows = ref([])
const stats = ref(null)
const accounts = ref([])
const accountId = ref('')
const confirmed = ref(false)

const steps = {
  wechat: [
    { title: '打开微信记账本', desc: '微信搜索"微信记账本"小程序并打开' },
    { title: '导出账单', desc: '进入「我的」→「账单明细」→「导出」' },
    { title: '选择时间范围', desc: '建议选择最近3个月' },
  ],
  alipay: [
    { title: '打开支付宝', desc: '进入「账单」页面' },
    { title: '导出账单', desc: '点击右上角「···」→「开具交易流水证明」' },
    { title: '选择时间范围', desc: '建议选择最近3个月' },
  ],
}

async function loadAccounts() {
  try {
    const d = await accountApi.list()
    accounts.value = d.items || d || []
  } catch (e) {
    /* ignore */
  }
}
function onFile(e) {
  file.value = e.target.files[0]
}
async function onUpload() {
  if (!file.value) return toast('请先选择账单文件')
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('platform', platform.value)
  uploading.value = true
  try {
    const d = await importApi.upload(fd)
    if (d.async) {
      toast('文件较大，已转入后台解析')
      return
    }
    rows.value = (d.rows || []).map((r) => ({
      ...r,
      amountText: yuan(r.amount_cents).toFixed(2),
      statusText: r.status === 'new' ? '新增' : r.status === 'duplicate' ? '重复' : '文件内重复',
    }))
    taskId.value = d.task.id
    stats.value = d.stats
    confirmed.value = false
  } catch (e) {
    toast(e.message || '解析失败')
  } finally {
    uploading.value = false
  }
}
async function onConfirm() {
  if (!taskId.value) return
  try {
    const res = await importApi.confirm(taskId.value, { account_id: accountId.value || null })
    toast(`已导入 ${res.created} 笔`)
    confirmed.value = true
  } catch (e) {
    toast(e.message || '导入失败')
  }
}
onMounted(loadAccounts)
</script>

<template>
  <div class="page import-page">
    <h2 class="page-title">从其他平台导入账单</h2>

    <!-- 平台选择 -->
    <div class="import-tabs">
      <div class="import-tab" :class="{ active: platform === 'wechat' }" @click="platform = 'wechat'">
        <div class="icon">💚</div>
        <div class="name">微信</div>
      </div>
      <div class="import-tab" :class="{ active: platform === 'alipay' }" @click="platform = 'alipay'">
        <div class="icon">🔵</div>
        <div class="name">支付宝</div>
      </div>
    </div>

    <!-- 步骤说明 -->
    <div class="card">
      <div class="section-title">{{ platform === 'wechat' ? '微信' : '支付宝' }}账单导入步骤</div>
      <div class="import-steps">
        <div v-for="s in steps[platform]" :key="s.title" class="step">
          <div class="step-num">{{ s.title[0] }}</div>
          <div class="step-content">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传区 -->
    <div v-if="!stats" class="upload-zone" @click="$refs.fileInput.click()">
      <div class="icon">📄</div>
      <div class="text">点击上传 CSV 文件</div>
      <div class="sub">支持 .csv 格式</div>
      <input ref="fileInput" type="file" accept=".csv,.txt" style="display: none" @change="onFile" />
    </div>

    <!-- 上传后预览 -->
    <template v-if="stats">
      <div class="card">
        <div class="section-title">解析结果</div>
        <div class="stat-row">
          <div class="stat"><span class="stat-num">{{ stats.total }}</span><span>总记录</span></div>
          <div class="stat"><span class="stat-num text-income">{{ stats.new }}</span><span>新增</span></div>
          <div class="stat"><span class="stat-num text-muted">{{ stats.duplicate + stats.internal_duplicate }}</span><span>重复</span></div>
          <div class="stat"><span class="stat-num" style="color:#f5a623">{{ stats.uncategorized }}</span><span>待确认</span></div>
        </div>
      </div>
      <div class="card">
        <div class="section-title">预览（前 {{ rows.length }} 条）</div>
        <div v-for="r in rows" :key="r.i" class="list-item">
          <div class="tx-info">
            <span class="tx-merchant">{{ r.merchant }}</span>
            <span class="tx-date text-muted">{{ r.date }} · {{ r.category }}</span>
          </div>
          <div class="tx-right">
            <span :class="['tx-amount', r.type === 'income' ? 'text-income' : 'text-expense']">
              {{ r.type === 'income' ? '+' : '-' }}{{ r.amountText }}
            </span>
            <span :class="['tx-status', r.status === 'new' ? 's-new' : 's-dup']">{{ r.statusText }}</span>
          </div>
        </div>
      </div>
      <div v-if="!confirmed" class="card">
        <div class="field-row">
          <span class="field-label">导入到账户</span>
          <select v-model="accountId" class="field-value">
            <option value="">不关联账户</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <button class="btn btn-primary btn-full" @click="onConfirm">确认导入</button>
      </div>
      <div v-else class="empty">✅ 已导入完成</div>
    </template>

    <!-- 支持说明 -->
    <div v-if="!stats" class="card support-card">
      <div class="support-row">✅ 支持自动：去重、智能分类、隐私标记</div>
      <div class="support-row">🕐 支持时间：2024年1月至今</div>
    </div>

    <button v-if="!stats" class="btn btn-primary btn-full" :disabled="uploading" @click="onUpload">
      {{ uploading ? '解析中…' : '开始导入' }}
    </button>
  </div>
</template>

<style scoped>
.import-page {
  padding: 16px;
  padding-bottom: 80px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #26215c;
  margin-bottom: 16px;
}
.import-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.import-tab {
  flex: 1;
  padding: 12px;
  border: 0.5px solid #e8e8e8;
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  background: #fff;
}
.import-tab.active {
  background: #eeedfe;
  border-color: #7f77dd;
}
.import-tab .icon {
  font-size: 24px;
  margin-bottom: 8px;
}
.import-tab .name {
  font-size: 13px;
  font-weight: 500;
}
.card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  border: 0.5px solid #e8e8e8;
}
.section-title {
  font-size: 14px;
  font-weight: 500;
  color: #2c2c2a;
  margin-bottom: 12px;
}
.step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}
.step:last-child {
  margin-bottom: 0;
}
.step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #7f77dd;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}
.step-content {
  flex: 1;
}
.step-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
}
.step-desc {
  font-size: 12px;
  color: #888780;
}
.upload-zone {
  border: 2px dashed #d3d1c7;
  border-radius: 12px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 16px;
  background: #fff;
}
.upload-zone .icon {
  font-size: 40px;
  color: #888780;
  margin-bottom: 8px;
}
.upload-zone .text {
  font-size: 13px;
  color: #5f5e5a;
}
.upload-zone .sub {
  font-size: 11px;
  color: #888780;
  margin-top: 4px;
}
.stat-row {
  display: flex;
  justify-content: space-around;
  text-align: center;
}
.stat {
  display: flex;
  flex-direction: column;
}
.stat-num {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-main);
}
.tx-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.tx-merchant {
  font-weight: 600;
}
.tx-date {
  font-size: 12px;
}
.tx-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.tx-amount {
  font-weight: 700;
}
.tx-status {
  font-size: 11px;
  margin-top: 4px;
  padding: 1px 8px;
  border-radius: 6px;
}
.s-new {
  color: var(--income);
  background: rgba(29, 158, 117, 0.12);
}
.s-dup {
  color: var(--text-muted);
  background: rgba(136, 135, 128, 0.12);
}
.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 16px;
}
.field-value {
  border: none;
  background: transparent;
  font-size: 14px;
}
.support-card {
  background: #f7f6f3;
  border: none;
}
.support-row {
  font-size: 13px;
  color: #5f5e5a;
  padding: 6px 0;
}
.btn-full {
  width: 100%;
}
</style>