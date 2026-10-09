// 金额工具：后端返回「分」，前端展示「元」
function yuan(cents) {
  return Math.round((Number(cents || 0) / 100) * 100) / 100
}

function formatCents(cents) {
  return '¥' + yuan(cents).toFixed(2)
}

module.exports = { yuan, formatCents }