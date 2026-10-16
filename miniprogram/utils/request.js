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
          // 不再强跳登录页：未登录/登录过期只是"没有数据"，页面仍可浏览。
          // 各页面拿 err.needLogin 自行决定展示登录引导还是静默降级。
          wx.removeStorageSync('fl_token')
          return reject(makeError('请先登录', true))
        }
        if (body.code !== 0) {
          return reject(makeError(body.message || '请求失败'))
        }
        resolve(body.data)
      },
      fail(err) {
        reject(makeError(err.errMsg || '网络错误'))
      },
    })
  })
}

function makeError(message, needLogin) {
  const err = new Error(message || '请求失败')
  err.needLogin = !!needLogin
  return err
}

/**
 * 页面 catch 里统一用：是登录问题就提示并跳登录页，返回 true。
 *   catch (e) { if (requireLogin(e)) return; ... 原有错误处理 }
 */
function requireLogin(e) {
  if (e && e.needLogin) {
    wx.showToast({ title: '请先登录', icon: 'none' })
    wx.navigateTo({ url: '/pages/login/login' })
    return true
  }
  return false
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

module.exports = { request, upload, isNeedLogin, requireLogin }

function isNeedLogin(e) {
  return !!(e && e.needLogin)
}