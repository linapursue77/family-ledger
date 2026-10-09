/**
 * 全局轻提示。
 *
 * ★ 不能用 window.alert：内置预览 / 部分 WebView 在 sandbox 下会吞掉原生弹窗，
 *   提示没出现、流程也停了，表现成「点了没反应」。这里自绘 DOM 提示，任何环境都能显示。
 * 用法：import { toast } from '@/utils/toast'; toast('请输入金额')
 */
let el = null
let timer = null

export function toast(message, duration = 2200) {
  if (typeof document === 'undefined') return
  if (!el) {
    el = document.createElement('div')
    el.className = 'app-toast'
    document.body.appendChild(el)
  }
  el.textContent = String(message ?? '')
  // 重置动画，连续多次调用也能重新淡入
  el.classList.remove('show')
  void el.offsetWidth
  el.classList.add('show')
  clearTimeout(timer)
  timer = setTimeout(() => el.classList.remove('show'), duration)
}
