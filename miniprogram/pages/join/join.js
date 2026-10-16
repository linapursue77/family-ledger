const api = require('../../utils/api')
const { requireLogin } = require('../../utils/request')

// 邀请里预设的权限，逐条翻译成人话，接受前先看清楚（与 H5 Join.vue 文案一致）
const PERM_TEXT = {
  report_view: (v) => (v === 'all' ? '查看全家庭的账单与报表' : '仅查看自己账本的报表'),
  account_view: (v) => (v === 'all' ? '查看全部账户与资产' : '仅查看自己的账户'),
  allow_record: (v) => (v ? '可以新增、编辑账单' : '只能看，不能记账'),
  show_private: (v) => (v ? '可以看到标记为私密的账目' : '看不到私密账目'),
  settings_level: (v) => (v === 'full' ? '可管理家庭设置与成员' : '不可管理家庭设置'),
}

function buildPermList(p) {
  const perms = p || {}
  return Object.keys(PERM_TEXT).map((k) => PERM_TEXT[k](perms[k]))
}

function fmtDate(v) {
  return String(v || '').slice(0, 10)
}

Page({
  data: {
    loading: true,
    errorText: '',
    info: null,
    permList: [],
    expireText: '',
    submitting: false,
    isLoggedIn: false,
  },

  token: '',

  onLoad(options) {
    const app = getApp()
    // 从「去登录」过来时 token 存在 globalData；navigateTo 带 query 时优先用 query
    const t = String(options.token || app.globalData.joinToken || '')
    if (app.globalData.joinToken) app.globalData.joinToken = ''
    this.token = t

    if (!t) {
      this.setData({ errorText: '缺少邀请码', loading: false })
      return
    }

    const isLoggedIn = !!wx.getStorageSync('fl_token')
    this.setData({ isLoggedIn })
    if (isLoggedIn) this.load()
    else this.setData({ loading: false })
  },

  onShow() {
    // 从 login 页跳转回来会重新 onLoad；这里兜底登录态变化的情况
    const isLoggedIn = !!wx.getStorageSync('fl_token')
    if (isLoggedIn && !this.data.isLoggedIn && this.token && !this.data.info) {
      this.setData({ isLoggedIn })
      this.load()
    }
  },

  async load() {
    this.setData({ loading: true, errorText: '' })
    try {
      const info = await api.invitePreview(this.token)
      this.setData({
        info,
        permList: buildPermList(info.permissions),
        expireText: fmtDate(info.expires_at),
      })
    } catch (e) {
      if (requireLogin(e)) {
        this.setData({ isLoggedIn: false, loading: false })
        return
      }
      this.setData({ info: null, errorText: e.message || '邀请无效' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onAccept() {
    const info = this.data.info
    if (!info || this.data.submitting) return
    // 自绘确认：wx.showModal 与 H5 的 ConfirmSheet 对等
    wx.showModal({
      title: `加入「${info.family_name}」？`,
      content: '加入后你的账单会记在自己的账本里，权限由主账号设定，之后可以调整',
      confirmText: '确认加入',
      success: async (res) => {
        if (!res.confirm) return
        this.setData({ submitting: true })
        try {
          const r = await api.acceptInvite(this.token)
          wx.showToast({ title: (r && r.message) || '已加入', icon: 'success' })
          setTimeout(() => wx.switchTab({ url: '/pages/family/family' }), 800)
        } catch (e) {
          this.setData({ errorText: e.message || '接受失败' })
        } finally {
          this.setData({ submitting: false })
        }
      },
    })
  },

  goLogin() {
    // 存到 globalData，login 页登录后自动带着它跳回本页
    getApp().globalData.joinToken = this.token
    wx.navigateTo({ url: '/pages/login/login' })
  },

  goHome() {
    wx.switchTab({ url: '/pages/home/home' })
  },
})
