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
    /*
     * 存 refresh：access 只有 2 小时，没有 refresh 的话过期就只能重新登录。
     * 后端开了轮换，每次刷新都会换新的 refresh，request.js 里会同步存回。
     */
    if (data.token && data.token.refresh) {
      wx.setStorageSync('fl_refresh', data.token.refresh)
    }
    if (data.profile && data.profile.user && data.profile.user.nickname) {
      wx.setStorageSync('fl_nickname', data.profile.user.nickname)
    }
    // 从邀请分享卡片进来还没登录的情况：登录完直接回 join 页继续加入流程，
    // 不能走 switchTab，那样会把 join 的返回栈清掉，白回来一趟。
    const app = getApp()
    const joinToken = app.globalData.joinToken
    app.globalData.joinToken = ''
    if (joinToken) {
      wx.navigateTo({ url: `/pages/join/join?token=${encodeURIComponent(joinToken)}` })
      return
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

  /**
   * 手机号快捷验证回调：能力入口已在 login.wxml 里注释屏蔽。
   * 该方法保留，日后主体变更为企业/个体工商户并开通该能力后，
   * 取消 wxml 里的注释即可直接复用，无需再写一遍。
   */
  onGetPhone(e) {
    const detail = e.detail || {}
    const errMsg = detail.errMsg || ''
    if (errMsg.indexOf('getPhoneNumber:ok') !== 0) {
      // 用户主动拒绝：不打扰，也不擅自登录
      if (errMsg.indexOf('deny') !== -1) return
      // 其余失败（未认证 / 未开通付费等）降级为静默登录
      wx.showToast({ title: '已改用微信一键登录', icon: 'none' })
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
