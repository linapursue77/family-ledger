import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 刷新专用裸实例：不能用 client 自己，否则 refresh 请求返回 401 时会递归触发刷新
const plain = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

// 并发的多个 401 共用同一次刷新：各自去刷会把对方刚换来的 refresh 顶失效
let refreshing = null

function clearAuth() {
  localStorage.removeItem('fl_token')
  localStorage.removeItem('fl_refresh')
  if (location.hash !== '#/login') location.hash = '#/login'
}

/** 用 refresh token 换 access，成功后写回 localStorage */
function refreshAccess() {
  const refresh = localStorage.getItem('fl_refresh')
  if (!refresh) return Promise.reject(new Error('无 refresh token'))
  if (refreshing) return refreshing

  refreshing = plain
    .post('/auth/refresh/', { refresh })
    .then((r) => {
      // TokenRefreshView 是 simplejwt 原生视图，返回裸 { access, refresh }，
      // 不走统一信封，所以直接读，不经过 unwrap
      const body = r.data || {}
      const access = body.access || (body.data && body.data.access)
      if (!access) throw new Error('refresh 响应缺少 access')
      localStorage.setItem('fl_token', access)
      // 开了轮换（ROTATE_REFRESH_TOKENS）就会发新 refresh，必须存回，
      // 否则下次刷新拿的是已失效的旧 refresh，会被直接踢下线
      const next = body.refresh || (body.data && body.data.refresh)
      if (next) localStorage.setItem('fl_refresh', next)
      return access
    })
    .catch((err) => {
      clearAuth()
      throw err
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('fl_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (resp) => resp.data,
  async (error) => {
    const original = error.config
    const status = error.response && error.response.status

    // 只重试一次；refresh 端点自己 401 不许再刷，否则死循环
    if (
      status === 401 &&
      original &&
      !original.__retried &&
      original.url !== '/auth/refresh/'
    ) {
      if (localStorage.getItem('fl_refresh')) {
        original.__retried = true
        try {
          const access = await refreshAccess()
          original.headers = original.headers || {}
          original.headers.Authorization = `Bearer ${access}`
          return client(original)
        } catch (e) {
          return Promise.reject(e)
        }
      }
      // 压根没有 refresh（老版本登录、或已被清掉）→ 老老实实去登录
      clearAuth()
    }
    return Promise.reject(error)
  }
)

export default client
