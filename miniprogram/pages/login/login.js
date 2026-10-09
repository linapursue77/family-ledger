const api = require('../../utils/api')

Page({
  data: {
    phone: '13800138000',
    password: 'test123456',
    loading: false,
  },

  onPhone(e) {
    this.setData({ phone: e.detail.value })
  },
  onPassword(e) {
    this.setData({ password: e.detail.value })
  },

  async onLogin() {
    const { phone, password } = this.data
    if (!phone || !password) {
      wx.showToast({ title: '请输入手机号和密码', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    try {
      const data = await api.login({ phone, password })
      wx.setStorageSync('fl_token', data.token.access)
      wx.switchTab({ url: '/pages/home/home' })
    } catch (e) {
      wx.showToast({ title: e.message || '登录失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },
})