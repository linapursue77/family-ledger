<script setup>
/**
 * 页内确认弹层。
 *
 * ★ 不使用 window.confirm()：内置预览 / 部分 WebView 在 sandbox 下会直接吞掉原生弹窗，
 *   调用方拿到 false 就 return，表现成「点了没反应」。自绘弹层在任何环境都能显示。
 */
defineProps({
  visible: Boolean,
  title: { type: String, default: '确认操作' },
  // 正文要点，逐条列出后果，比一段长句更好读
  lines: { type: Array, default: () => [] },
  okText: { type: String, default: '确认' },
  danger: Boolean,
})
const emit = defineEmits(['ok', 'cancel'])
</script>

<template>
  <div v-if="visible" class="cf-mask" @click="emit('cancel')">
    <div class="cf-box" @click.stop>
      <div class="cf-title">{{ title }}</div>
      <div class="cf-body">
        <div v-for="(l, i) in lines" :key="i" class="cf-line">{{ l }}</div>
      </div>
      <div class="cf-actions">
        <button class="cf-btn" @click="emit('cancel')">取消</button>
        <button class="cf-btn primary" :class="{ danger }" @click="emit('ok')">{{ okText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cf-mask {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: rgba(38, 33, 92, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 28px;
}
.cf-box {
  width: 100%;
  max-width: 320px;
  background: #fff;
  border-radius: var(--radius-large, 16px);
  padding: 20px 18px 14px;
  box-shadow: 0 12px 40px rgba(38, 33, 92, 0.24);
  animation: cfIn 0.18s ease;
}
@keyframes cfIn {
  from {
    transform: scale(0.94);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
.cf-title {
  font-size: var(--font-lg, 16px);
  font-weight: 700;
  color: var(--text-main, #26215c);
  text-align: center;
}
.cf-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cf-line {
  font-size: var(--font-sm, 13px);
  color: var(--text-sub, #5f5e5a);
  line-height: 1.6;
  padding-left: 14px;
  position: relative;
}
.cf-line::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 8px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-muted, #888780);
}
.cf-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}
.cf-btn {
  flex: 1;
  border: none;
  border-radius: var(--radius-btn, 8px);
  padding: 11px 0;
  font-size: var(--font-md, 14px);
  font-weight: 600;
  cursor: pointer;
  background: #f1efe8;
  color: var(--text-sub, #5f5e5a);
  transition: opacity 0.15s;
}
.cf-btn:active {
  opacity: 0.8;
}
.cf-btn.primary {
  background: var(--primary, #7f77dd);
  color: #fff;
}
.cf-btn.primary.danger {
  background: var(--expense, #e24b4a);
}
</style>
