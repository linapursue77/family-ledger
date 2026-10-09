// 统一请求封装：注入 token、解包 {code, message, data}
const app = getApp()

function request(method, path, data = {}) {
  const token = wx.getStorageSync('fl_token')
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + path,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success(res) {
        const body = res.data || {}
        if (res.statusCode === 401) {
          wx.removeStorageSync('fl_token')
          wx.reLaunch({ url: '/pages/login/login' })
          return reject(new Error('未登录'))
        }
        if (body.code !== 0) {
          return reject(new Error(body.message || '请求失败'))
        }
        resolve(body.data)
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络错误'))
      },
    })
  })
}

// 文件上传（导入）
function upload(path, filePath, formData = {}) {
  const token = wx.getStorageSync('fl_token')
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: app.globalData.apiBase + path,
      filePath,
      name: 'file',
      formData,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          body = { code: -1, message: '响应解析失败' }
        }
        if (body.code !== 0) return reject(new Error(body.message || '上传失败'))
        resolve(body.data)
      },
      fail(err) {
        reject(new Error(err.errMsg || '上传失败'))
      },
    })
  })
}

module.exports = { request, upload }