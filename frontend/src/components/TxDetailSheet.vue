<script setup>
defineProps({
  visible: Boolean,
  tx: { type: Object, default: null },
  tip: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const TYPE_TEXT = {
  expense: '支出',
  income: '收入',
  transfer: '转账',
  loan_in: '借入 / 收到还款',
  loan_out: '借出 / 归还借款',
}
const SOURCE_TEXT = { manual: '手动记账', import: '账单导入' }
</script>

<template>
  <div v-if="visible && tx" class="tx-mask" @click="emit('close')">
    <div class="tx-sheet" @click.stop>
      <div class="tx-head">
        <span class="tx-title">账单明细</span>
        <span class="tx-close" @click="emit('close')">×</span>
      </div>

      <div v-if="tip" class="tx-tip">{{ tip }}</div>

      <div class="tx-hero">
        <span class="tx-ic" :style="{ background: tx.catColor + '22', color: tx.catColor }">{{ tx.catIcon }}</span>
        <div class="tx-hero-main">
          <div class="tx-merchant">{{ tx.merchant }}</div>
          <div class="tx-cat">{{ tx.catName }}</div>
        </div>
        <span
          :class="['tx-amount', tx.isLoan ? 'text-loan' : tx.isIn ? 'text-income' : 'text-expense']"
          >{{ tx.amountText }}</span
        >
      </div>

      <div class="tx-rows">
        <div class="tx-row">
          <span class="tx-k">类型</span>
          <b class="tx-v">{{ TYPE_TEXT[tx.type] || tx.type }}</b>
        </div>
        <div class="tx-row">
          <span class="tx-k">日期</span>
          <b class="tx-v">{{ tx.dateText }}</b>
        </div>
        <div class="tx-row">
          <span class="tx-k">账户</span>
          <b class="tx-v">{{ tx.accountName || '未指定账户' }}</b>
        </div>
        <div v-if="tx.description" class="tx-row">
          <span class="tx-k">备注</span>
          <b class="tx-v">{{ tx.description }}</b>
        </div>
        <div class="tx-row">
          <span class="tx-k">来源</span>
          <b class="tx-v">{{ SOURCE_TEXT[tx.source] || tx.source || '—' }}</b>
        </div>
        <div v-if="tx.is_private" class="tx-row">
          <span class="tx-k">可见性</span>
          <b class="tx-v">🔐 私密消费</b>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tx-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 60;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.tx-sheet {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 16px 18px calc(22px + env(safe-area-inset-bottom));
}
.tx-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.tx-title {
  font-size: 15px;
  font-weight: 600;
  color: #26215c;
}
.tx-close {
  font-size: 22px;
  line-height: 1;
  color: #b8b6ae;
  cursor: pointer;
}
.tx-tip {
  font-size: 12px;
  color: #534ab7;
  background: #eeedfe;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 12px;
}
.tx-hero {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 14px;
  border-bottom: 0.5px solid #f1efe8;
}
.tx-ic {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex: none;
}
.tx-hero-main {
  flex: 1;
  min-width: 0;
}
.tx-merchant {
  font-size: 15px;
  font-weight: 600;
  color: #26215c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tx-cat {
  font-size: 11px;
  color: #888780;
  margin-top: 2px;
}
.tx-amount {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  flex: none;
}
.text-loan {
  color: #888780;
}
.tx-rows {
  padding-top: 4px;
}
.tx-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 0.5px solid #f7f6f3;
}
.tx-row:last-child {
  border-bottom: none;
}
.tx-k {
  font-size: 13px;
  color: #888780;
  flex: none;
}
.tx-v {
  font-size: 13px;
  font-weight: 500;
  color: #26215c;
  text-align: right;
  word-break: break-all;
}
</style>
