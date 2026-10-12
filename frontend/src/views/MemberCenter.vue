<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { membershipApi } from '@/api'
import { toast } from '@/utils/toast'
import { payScene, poll, requestPayment } from '@/utils/wxpay'

// 授权 / H5 收银台跳走再回来时的续接凭据
const PENDING_PLAN_KEY = 'vipPendingPlan'
const PAYING_ORDER_KEY = 'vipPayingOrder'

const router = useRouter()
const data = ref(null)
const loading = ref(true)
const acting = ref('')

const mine = computed(() => data.value?.mine || null)
const isVip = computed(() => !!mine.value?.is_vip)
const freeBenefits = computed(() => (data.value?.benefits || []).filter((b) => !b.vip))
const vipBenefits = computed(() => (data.value?.benefits || []).filter((b) => b.vip))
const plans = computed(() => data.value?.plans || [])

function yuan(cents) {
  const n = Number(cents || 0) / 100
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

const statusText = computed(() => {
  const m = mine.value
  if (!m) return ''
  if (!m.is_vip) return m.trial_used ? '试用已用完' : '未开通'
  if (m.is_trial) return `试用中 · 剩 ${m.remain_days} 天`
  return m.expire_at ? `${m.expire_at.slice(0, 10)} 到期 · 剩 ${m.remain_days} 天` : '会员'
})

async function load() {
  loading.value = true
  try {
    data.value = await membershipApi.home()
  } catch (e) {
    toast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function takeTrial() {
  acting.value = 'trial'
  try {
    const res = await membershipApi.trial()
    toast(res?.message || '试用已开通')
    await load()
  } catch (e) {
    toast(e.message || '领取失败')
  } finally {
    acting.value = ''
  }
}

/** 轮询订单直到支付成功（后端会顺带向微信查单，回调丢了也能补上） */
async function waitPaid(orderNo, silent = false) {
  const paid = await poll(
    async () => {
      const order = await membershipApi.orderStatus(orderNo)
      return order?.status === 'paid' ? order : null
    },
    { interval: 1500, timeout: 60000 }
  )
  if (paid) {
    await load()
    toast('支付成功，会员已开通')
    return true
  }
  if (!silent) toast('支付结果确认中，稍后可在「我的」查看会员状态')
  return false
}

async function buy(plan) {
  if (!plan?.id) return
  acting.value = plan.id
  try {
    const res = await membershipApi.createOrder(plan.id, payScene(), window.location.href)
    // 本地联调模式（后端未配置支付）：直接开通
    if (res?.mode === 'mock') {
      toast('已开通（联调模式，未真实扣款）')
      await load()
      return
    }
    // 还没绑微信：去授权，回来自动继续这笔支付
    if (res?.need_openid) {
      if (!res.auth_url) {
        toast(res.message || '请先在小程序内登录微信')
        return
      }
      sessionStorage.setItem(PENDING_PLAN_KEY, plan.id)
      window.location.href = res.auth_url
      return
    }
    if (!res?.order_no) throw new Error('下单失败，请重试')
    if (res.status === 'paid') {
      await load()
      toast('支付成功，会员已开通')
      return
    }
    // 微信外浏览器：跳微信 H5 收银台，支付完跳回来再确认
    if (res.mweb_url) {
      sessionStorage.setItem(PAYING_ORDER_KEY, res.order_no)
      window.location.href = res.mweb_url
      return
    }
    await requestPayment(res.pay_params, res.scene || payScene())
    await waitPaid(res.order_no)
  } catch (e) {
    toast(e?.code === 'CANCEL' ? '已取消支付' : e?.message || '支付失败')
  } finally {
    acting.value = ''
  }
}

onMounted(async () => {
  await load()
  // 公众号网页授权回来：继续刚才那笔订单
  const pendingPlan = sessionStorage.getItem(PENDING_PLAN_KEY)
  if (pendingPlan) {
    sessionStorage.removeItem(PENDING_PLAN_KEY)
    const plan = plans.value.find((p) => p.id === pendingPlan)
    if (plan) {
      buy(plan)
      return
    }
  }
  // H5 收银台跳回来：确认支付结果
  const payingOrder = sessionStorage.getItem(PAYING_ORDER_KEY)
  if (payingOrder) {
    sessionStorage.removeItem(PAYING_ORDER_KEY)
    await waitPaid(payingOrder, true)
  }
})
</script>

<template>
  <div class="mc-page">
    <div class="top-bar">
      <span class="top-title">👑 会员中心</span>
      <span class="top-close" @click="router.back()">×</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <template v-else>
      <!-- 会员卡 -->
      <div class="vip-card" :class="{ plain: !isVip }">
        <div class="vc-head">
          <span class="vc-badge">{{ isVip ? '👑 VIP 会员' : '普通用户' }}</span>
          <span v-if="mine && mine.is_vip" class="vc-expire">{{ statusText }}</span>
        </div>
        <div class="vc-title">
          {{ isVip ? '全部 8 项 VIP 权益已解锁' : `解锁 ${vipBenefits.length} 项 VIP 权益` }}
        </div>
        <div v-if="!isVip && data.trial_enabled && !mine?.trial_used" class="vc-trial">
          新用户可免费试用 {{ data.trial_days }} 天，到期自动恢复，不会扣费
        </div>
        <div v-else-if="!isVip" class="vc-trial">试用机会已使用，开通后享受全部权益</div>
      </div>

      <!-- 试用 / 开通入口 -->
      <div v-if="!isVip" class="trial-row">
        <button
          v-if="data.trial_enabled && !mine?.trial_used"
          class="btn btn-ghost"
          :disabled="acting === 'trial'"
          @click="takeTrial"
        >
          {{ acting === 'trial' ? '开通中…' : `免费试用 ${data.trial_days} 天` }}
        </button>
        <span v-else class="trial-used">试用已用完</span>
      </div>

      <!-- 套餐 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">开通会员</span>
          <span class="card-tag">家庭共享，主账号开通全家用</span>
        </div>
        <div
          v-for="p in plans"
          :key="p.id"
          class="plan"
          :class="{ recommend: p.is_recommend }"
        >
          <div class="plan-main">
            <div class="plan-name">
              {{ p.name }}
              <em v-if="p.is_recommend" class="plan-flag">推荐</em>
            </div>
            <div class="plan-price">
              <span class="pp-now">¥{{ yuan(p.price_cents) }}</span>
              <span v-if="p.original_price_cents > p.price_cents" class="pp-old">
                ¥{{ yuan(p.original_price_cents) }}
              </span>
              <span class="pp-unit">/ {{ p.duration_days }} 天</span>
            </div>
            <ul class="plan-perks">
              <li v-for="s in p.perks || []" :key="s">{{ s }}</li>
            </ul>
          </div>
          <button class="btn btn-primary plan-btn" :disabled="acting === p.id" @click="buy(p)">
            {{ acting === p.id ? '处理中…' : isVip ? '续费' : '开通' }}
          </button>
        </div>
        <div v-if="!plans.length" class="empty sm">暂无在售套餐</div>
      </div>

      <!-- 权益对比 -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">权益对比</span>
        </div>
        <div class="cmp-head">
          <span class="cmp-name">权益</span>
          <span class="cmp-col">普通</span>
          <span class="cmp-col vip">VIP</span>
        </div>
        <div v-for="b in freeBenefits" :key="b.key" class="cmp-row">
          <div class="cmp-name">
            <div class="cmp-title">{{ b.name }}</div>
            <div class="cmp-desc">{{ b.desc }}</div>
          </div>
          <span class="cmp-col">✓</span>
          <span class="cmp-col vip">✓</span>
        </div>
        <div v-for="b in vipBenefits" :key="b.key" class="cmp-row vip-row">
          <div class="cmp-name">
            <div class="cmp-title">{{ b.name }}<em class="vip-tag">VIP</em></div>
            <div class="cmp-desc">{{ b.desc }}</div>
          </div>
          <span class="cmp-col">—</span>
          <span class="cmp-col vip">✓</span>
        </div>
      </div>

      <!-- 说明 -->
      <div class="card">
        <div class="card-head"><span class="card-title">会员说明</span></div>
        <ul class="notes">
          <li>会员权益按<b>家庭</b>生效：主账号开通后，家庭成员一起享受（人数上限、报表周期等）。</li>
          <li>试用期内权益与正式会员一致，到期自动恢复普通用户，不自动扣费。</li>
          <li>续费在原有到期时间上顺延，不会缩短已购时长。</li>
          <li>开通 / 续费通过微信支付完成，支付成功后会员立即生效。</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.mc-page {
  padding-bottom: calc(var(--nav-h, 60px) + env(safe-area-inset-bottom) + 16px);
  min-height: 100vh;
  background: #faf9f6;
}
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px 12px;
}
.top-title {
  font-size: 18px;
  font-weight: 700;
  color: #26215c;
}
.top-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f1efe8;
  color: #888780;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
/* 会员卡 */
.vip-card {
  margin: 0 16px 16px;
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, #3d2f7a 0%, #26215c 55%, #1d1a45 100%);
  color: #fff;
  box-shadow: 0 8px 20px rgba(38, 33, 92, 0.18);
}
.vip-card.plain {
  background: linear-gradient(135deg, #6f6c86 0%, #555268 100%);
  box-shadow: none;
}
.vc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.vc-badge {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.vc-expire {
  font-size: 11px;
  opacity: 0.85;
}
.vc-title {
  margin-top: 8px;
  font-size: 13px;
  opacity: 0.92;
}
.vc-trial {
  margin-top: 6px;
  font-size: 11px;
  opacity: 0.75;
}
.trial-row {
  margin: 0 16px 16px;
  display: flex;
  align-items: center;
}
.btn-ghost {
  border: 1px solid #26215c;
  background: #fff;
  color: #26215c;
  font-weight: 600;
}
.trial-used {
  font-size: 12px;
  color: #b8b6ae;
}
/* 卡片 */
.card {
  margin: 0 16px 16px;
  padding: 16px;
  background: #fff;
  border: 0.5px solid #e8e8e8;
  border-radius: 14px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
}
.card-tag {
  font-size: 11px;
  color: #b8b6ae;
}
/* 套餐 */
.plan {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 0.5px solid #e8e8e8;
  border-radius: 12px;
  margin-bottom: 10px;
}
.plan.recommend {
  border-color: #7f77dd;
  background: #fbfbff;
}
.plan-main {
  flex: 1;
  min-width: 0;
}
.plan-name {
  font-size: 14px;
  font-weight: 600;
  color: #26215c;
}
.plan-flag {
  font-style: normal;
  font-size: 10px;
  color: #fff;
  background: #534ab7;
  border-radius: 4px;
  padding: 1px 5px;
  margin-left: 6px;
  vertical-align: 1px;
}
.plan-price {
  margin-top: 4px;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.pp-now {
  font-size: 20px;
  font-weight: 700;
  color: #26215c;
  font-variant-numeric: tabular-nums;
}
.pp-old {
  font-size: 12px;
  color: #b8b6ae;
  text-decoration: line-through;
}
.pp-unit {
  font-size: 11px;
  color: #888780;
}
.plan-perks {
  margin: 6px 0 0;
  padding-left: 16px;
}
.plan-perks li {
  font-size: 11px;
  color: #888780;
  line-height: 1.7;
}
.plan-btn {
  flex: none;
  width: auto; /* 覆盖全局 .btn-primary 的 width:100%，避免撑满整行挤掉套餐信息 */
  padding: 9px 16px;
  font-size: 13px;
}
/* 权益对比 */
.cmp-head,
.cmp-row {
  display: grid;
  grid-template-columns: 1fr 52px 52px;
  align-items: center;
  gap: 4px;
  padding: 8px 0;
}
.cmp-head {
  font-size: 11px;
  color: #b8b6ae;
  border-bottom: 0.5px solid #f1efe8;
}
.cmp-row {
  border-bottom: 0.5px solid #faf9f6;
}
.cmp-col {
  text-align: center;
  font-size: 13px;
  color: #888780;
}
.cmp-col.vip {
  color: #1d9e75;
  font-weight: 700;
}
.cmp-title {
  font-size: 13px;
  color: #26215c;
  font-weight: 500;
}
.cmp-desc {
  font-size: 11px;
  color: #b8b6ae;
  margin-top: 2px;
  line-height: 1.5;
}
.vip-tag {
  font-style: normal;
  font-size: 9px;
  color: #534ab7;
  background: #eeedfe;
  border-radius: 4px;
  padding: 1px 4px;
  margin-left: 5px;
  vertical-align: 1px;
}
.vip-row .cmp-title {
  color: #26215c;
}
/* 说明 */
.notes {
  margin: 0;
  padding-left: 16px;
}
.notes li {
  font-size: 12px;
  color: #888780;
  line-height: 1.8;
}
.empty {
  text-align: center;
  color: #b8b6ae;
  font-size: 13px;
  padding: 40px 0;
}
.empty.sm {
  padding: 20px 0;
  font-size: 12px;
}
</style>
