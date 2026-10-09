App({
  globalData: {
    // 后端 API 基地址。开发期用本机 Django；真机/上线改为 https 域名
    apiBase: 'http://127.0.0.1:8001/api/v1',
  },
  onLaunch() {
    // 启动时校验登录态
    const token = wx.getStorageSync('fl_token')
    if (!token) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },
})