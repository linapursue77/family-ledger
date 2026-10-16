/**
 * 通用分享能力（H5）
 *
 * ★ 现实约束：微信内置浏览器里要自定义分享卡片必须接微信 JS-SDK，
 *   而这需要「已认证的服务号/订阅号」+ 后端签名接口 + JS 安全域名。
 *   个人主体小程序配套公众号通常拿不到该权限，所以这里按能力逐级降级：
 *     1) navigator.share → 系统分享面板（iOS/Android 均可直接选「微信」）
 *     2) 微信内置浏览器  → 引导用户点右上角 ⋯ → 发送给朋友
 *     3) 兜底            → 复制链接
 *
 *   share() 返回 'shared' | 'cancel' | 'guide' | 'copied' | 'failed'，
 *   调用方根据返回值决定是否弹「引导遮罩」。
 */
import { toast } from './toast'

export const APP_NAME = '钱来钱往记账'

/** hash 路由下的完整地址 */
export function appUrl(hashPath = '') {
  const base = `${location.origin}${location.pathname}`
  return hashPath ? `${base}#${hashPath}` : base
}

export function isWechat() {
  return typeof navigator !== 'undefined' && /micromessenger/i.test(navigator.userAgent)
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  document.execCommand('copy')
  ta.remove()
}

/** 分享应用本身 */
export function appSharePayload() {
  return {
    title: `${APP_NAME} · 家庭一起记账`,
    text: '账本分得清、报表看得懂，和家里人一起记账更省心。',
    url: appUrl('/'),
  }
}

/** 分享家庭邀请（链接口径与 Family.vue 的邀请链接保持一致） */
export function inviteSharePayload(token, inviter) {
  return {
    title: `${inviter || '家人'} 邀请你加入家庭账本`,
    text: '一起记收支、管预算，7 天内有效，点击后可见具体权限再决定是否加入。',
    url: appUrl(`/join?token=${encodeURIComponent(token)}`),
  }
}

/**
 * 发起分享。
 * @returns {Promise<'shared'|'cancel'|'guide'|'copied'|'failed'>}
 */
export async function share(payload) {
  const data = { title: payload.title, text: payload.text, url: payload.url }

  // 1) 系统分享面板：移动端浏览器普遍支持，可直接选「微信」
  if (typeof navigator !== 'undefined' && navigator.share) {
    try {
      await navigator.share(data)
      return 'shared'
    } catch (e) {
      if (e && e.name === 'AbortError') return 'cancel' // 用户主动取消，不算失败
      // 其它异常（权限限制 / 非安全上下文等）继续降级
    }
  }

  // 2) 微信内置浏览器：无法自定义卡片，引导点右上角
  if (isWechat()) return 'guide'

  // 3) 兜底复制链接
  try {
    await copyToClipboard(payload.url)
    toast('链接已复制，去微信发给好友吧')
    return 'copied'
  } catch (e) {
    toast('分享失败，请手动复制链接')
    return 'failed'
  }
}
