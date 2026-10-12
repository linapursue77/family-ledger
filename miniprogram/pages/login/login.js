const api = require('../../utils/api')

Page({
  data: {
    phone: '13800138000',
    password: 'test123456',
    loading: false,
    showPwd: false,
  },

  onPhone(e) {
    this.setData({ phone: e.detail.value })
  },
  onPassword(e) {
    this.setData({ password: e.detail.value })
  },
  togglePwd() {
    this.setData({ showPwd: !this.data.showPwd })
  },

  /** 登录成功后统一落 token 并进首页 */
  _afterLogin(data) {
    wx.setStorageSync('fl_token', data.token.access)
    if (data.profile && data.profile.user && data.profile.user.nickname) {
      wx.setStorageSync('fl_nickname', data.profile.user.nickname)
    }
    wx.switchTab({ url: '/pages/home/home' })
  },

  /** 取 wx.login 的 code（一次性，5 分钟有效） */
  _wxCode() {
    return new Promise((resolve, reject) => {
      wx.login({
        timeout: 8000,
        success: (res) => (res.code ? resolve(res.code) : reject(new Error('微信登录失败'))),
        fail: () => reject(new Error('微信登录失败')),
      })
    })
  },

  /** 调后端微信登录；手机号 code 可选，失败不影响登录 */
  async _wxLogin(phoneCode) {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      let code
      try {
        code = await this._wxCode()
      } catch (e) {
        wx.showToast({ title: e.message || '微信登录失败', icon: 'none' })
        return
      }
      const data = await api.wechatLogin({ code, phone_code: phoneCode || '' })
      this._afterLogin(data)
      if (phoneCode && !data.phone_bound) {
        wx.showToast({ title: '手机号未绑定，可在「我的」里补充', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: e.message || '登录失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  /** 静默登录：所有主体可用 */
  onWxLogin() {
    this._wxLogin('')
  },

  /** 手机号快捷验证：个人主体 / 未认证会回调 fail，自动降级为静默登录 */
  onGetPhone(e) {
    const detail = e.detail || {}
    if (detail.errMsg && detail.errMsg.indexOf('getPhoneNumber:ok') !== 0) {
      // 常见：个人主体无权限（no permission）、用户拒绝（deny）
      if (detail.errMsg.indexOf('deny') === -1) {
        wx.showToast({ title: '手机号能力不可用，已用微信登录', icon: 'none' })
      }
      this._wxLogin('')
      return
    }
    this._wxLogin(detail.code || '')
  },

  /** 手机号 + 密码（兜底） */
  async onLogin() {
    const { phone, password } = this.data
    if (!phone || !password) {
      wx.showToast({ title: '请输入手机号和密码', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    try {
      const data = await api.login({ phone, password })
      this._afterLogin(data)
    } catch (e) {
      wx.showToast({ title: e.message || '登录失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },
})
