import { defineStore } from 'pinia'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('fl_token') || '',
    // 刷新令牌：access 只有 2 小时，靠它静默续期，不存就等于每次过期都要重新登录
    refresh: localStorage.getItem('fl_refresh') || '',
    user: null,
    family: null,
    // 我在家庭里的身份：{ id, role, nickname, book_type, permissions }
    member: null,
  }),
  getters: {
    isLogin: (s) => !!s.token,
    isOwner: (s) => s.member?.role === 'owner',
    /** 家庭设置类操作（邀请、授权、改阈值）是否可用 */
    canManageFamily: (s) =>
      s.member?.role === 'owner' || s.member?.permissions?.settings_level === 'full',
    perms: (s) => s.member?.permissions || {},
    /** 是否被授权记账；主账号恒为真 */
    canRecord: (s) => (s.member?.permissions || {}).allow_record !== false,
  },
  actions: {
    async login(payload) {
      const d = await authApi.login(payload)
      this.token = d.token.access
      this.refresh = d.token.refresh || ''
      localStorage.setItem('fl_token', this.token)
      if (this.refresh) localStorage.setItem('fl_refresh', this.refresh)
      await this.fetchMe()
    },
    /** 注册即登录：后端返回 token，存好后再拉一次家庭上下文 */
    async register(payload) {
      const d = await authApi.register(payload)
      this.token = d.token.access
      this.refresh = d.token.refresh || ''
      localStorage.setItem('fl_token', this.token)
      if (this.refresh) localStorage.setItem('fl_refresh', this.refresh)
      await this.fetchMe()
    },
    async fetchMe() {
      const d = await authApi.me()
      this.user = d.user
      this.family = d.family
      this.member = d.member
    },
    logout() {
      this.token = ''
      this.refresh = ''
      this.user = null
      this.family = null
      this.member = null
      localStorage.removeItem('fl_token')
      localStorage.removeItem('fl_refresh')
    },
  },
})
