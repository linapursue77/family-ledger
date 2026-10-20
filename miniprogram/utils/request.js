// 统一请求封装：注入 token、解包 {code, message, data}
const app = getApp()

// 并发请求共用同一次刷新：各自去刷会互相顶掉刚换来的 refresh
let refreshing = null
// 登录失效的处理只做一次，避免多个并发 401 同时弹提示
let kicking = false

function clearAuth() {
  wx.removeStorageSync('fl_token')
  wx.removeStorageSync('fl_refresh')
}

/**
 * 用 refresh token 换新的 access。
 * 后端开了 ROTATE_REFRESH_TOKENS，每次刷新都会下发新的 refresh，
 * 必须存回去，否则下次拿失效的旧 refresh 会被直接踢下线。
 */
function refreshAccess() {
  const refresh = wx.getStorageSync('fl_refresh')
  if (!refresh) return Promise.reject(makeError('请先登录', true))
  if (refreshing) return refreshing

  refreshing = new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + '/auth/refresh/',
      method: 'POST',
      data: { refresh },
      header: { 'Content-Type': 'application/json' },
      success(res) {
        const body = res.data || {}
        // TokenRefreshView 是 simplejwt 原生视图，返回裸 { access, refresh }，不走统一信封
        const access = body.access || (body.data && body.data.access)
        if (res.statusCode !== 200 || !access) {
          clearAuth()
          return reject(makeError('登录已过期', true))
        }
        wx.setStorageSync('fl_token', access)
        const next = body.refresh || (body.data && body.data.refresh)
        if (next) wx.setStorageSync('fl_refresh', next)
        resolve(access)
      },
      fail() {
        // 网络问题不该清 token，否则断网一下就得重新登录
        reject(makeError('网络错误'))
      },
    })
  }).finally(() => {
    refreshing = null
  })

  return refreshing
}

/**
 * 发起单次请求。
 * @param {boolean} retried 已经因 401 重试过一次，不再重试，防死循环
 */
function send(method, path, data, retried) {
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
          return reject({ status: 401, path, method, data, retried: !!retried })
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

function request(method, path, data = {}) {
  return send(method, path, data, false).catch((err) => {
    // 不是 401 就原样抛出
    if (!err || err.status !== 401) throw err

    // 登录接口本身 401 = 账号密码错，不能去刷新，也别说成"请先登录"
    if (path.indexOf('/auth/') === 0) {
      throw makeError('请先登录', true)
    }

    // 有 refresh 就先静默续期再重试一次；没有就直接走登录引导
    if (!wx.getStorageSync('fl_refresh')) {
      clearAuth()
      throw makeError('请先登录', true)
    }
    if (err.retried) {
      clearAuth()
      throw makeError('登录已过期，请重新登录', true)
    }
    return refreshAccess()
      .then(() => send(method, path, data, true))
      .catch((e) => {
        // 刷新失败（refresh 也过期）才清登录态；网络错误保留 token
        throw e && e.needLogin ? e : makeError('请先登录', true)
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
 *
 * 加互斥：并发请求同时 401 时只跳一次，否则会叠出多个登录页
 */
function requireLogin(e) {
  if (e && e.needLogin) {
    if (kicking) return true
    kicking = true
    wx.showToast({ title: '请先登录', icon: 'none' })
    wx.navigateTo({
      url: '/pages/login/login',
      complete: () => {
        // 跳转完成后再解锁，留一点时间让后续 401 也走拦截
        setTimeout(() => {
          kicking = false
        }, 1500)
      },
    })
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
