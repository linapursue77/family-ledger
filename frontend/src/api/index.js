import client from './client'

// 统一解包 { code, message, data }
function unwrap(promise) {
  return promise.then(
    (res) => {
      if (res && res.code !== 0) {
        const err = new Error(res.message || '请求失败')
        err.code = res.code
        throw err
      }
      return res ? res.data : null
    },
    (error) => {
      // 后端对 400/403/404/405 保留了真实 HTTP 状态码（只把 5xx 压成 200），
      // axios 见到非 2xx 直接 reject，信封躺在 error.response.data 里没人捞，
      // 用户就只能看到 "Request failed with status code 405" 这种英文兜底文案
      const body = error && error.response && error.response.data
      if (body && typeof body === 'object') {
        const raw = body.message || body.detail || (Array.isArray(body) ? body[0] : '')
        if (raw) {
          const err = new Error(typeof raw === 'string' ? raw : JSON.stringify(raw))
          err.code = body.code
          err.status = error.response.status
          return Promise.reject(err)
        }
      }
      return Promise.reject(error)
    },
  )
}

export const authApi = {
  login: (payload) => unwrap(client.post('/auth/login/', payload)),
  // 注册：后端会自动建一个新家庭并把注册人设为主账号，返回 token 直接进首页
  register: (payload) => unwrap(client.post('/auth/register/', payload)),
  me: () => unwrap(client.get('/auth/me/')),
  // 个人资料：昵称 / 头像 / 隐私额度（每人一份，保存即生效）
  updateProfile: (payload) => unwrap(client.patch('/auth/profile/', payload)),
}

export const accountApi = {
  list: () => unwrap(client.get('/accounts/')),
  netvalue: () => unwrap(client.get('/accounts/netvalue/')),
  create: (payload) => unwrap(client.post('/accounts/', payload)),
  update: (id, payload) => unwrap(client.patch(`/accounts/${id}/`, payload)),
  adjust: (id, payload) => unwrap(client.post(`/accounts/${id}/adjust/`, payload)),
  remove: (id) => unwrap(client.delete(`/accounts/${id}/`)),
  renameBook: (payload) => unwrap(client.post('/accounts/book-label/', payload)),
}

export const familyApi = {
  me: () => unwrap(client.get('/families/me/')),
  // 邀请：列表 / 生成（token 只回传一次）/ 撤销 / 预览 / 接受
  invitations: () => unwrap(client.get('/families/invitations/')),
  invite: (payload) => unwrap(client.post('/families/invitations/', payload)),
  revokeInvite: (id) => unwrap(client.post(`/families/invitations/${id}/revoke/`)),
  previewInvite: (token) => unwrap(client.get('/families/invitations/preview/', { params: { token } })),
  acceptInvite: (token) => unwrap(client.post('/families/invitations/accept/', { token })),
  // 成员：改称呼/账本、移除、授权
  updateMember: (id, payload) => unwrap(client.patch(`/families/members/${id}/`, payload)),
  removeMember: (id) => unwrap(client.delete(`/families/members/${id}/`)),
  setPermissions: (id, payload) => unwrap(client.patch(`/families/members/${id}/permissions/`, payload)),
  // 转让主账号：谁管钱谁当主账号，转让后自己降级为普通成员
  transferOwner: (id) => unwrap(client.post(`/families/members/${id}/transfer-owner/`)),
  // 协商阈值
  thresholds: () => unwrap(client.get('/families/thresholds/')),
  saveThresholds: (payload) => unwrap(client.put('/families/thresholds/', payload)),
}

export const ledgerApi = {
  categories: (kind) => unwrap(client.get('/ledger/categories/', { params: { kind } })),
  createCategory: (payload) => unwrap(client.post('/ledger/categories/', payload)),
  overview: (params) => unwrap(client.get('/ledger/overview/', { params })),
  report: (params) => unwrap(client.get('/ledger/report/', { params })),
  reportInsight: (params) => unwrap(client.get('/ledger/report/insight/', { params })),
  aiConfig: () => unwrap(client.get('/ledger/ai/config/')),
  saveAiConfig: (payload) => unwrap(client.put('/ledger/ai/config/', payload)),
  testAiConfig: (payload) => unwrap(client.post('/ledger/ai/config/test/', payload)),
  transactions: (params) => unwrap(client.get('/ledger/transactions/', { params })),
  txDetail: (id) => unwrap(client.get(`/ledger/transactions/${id}/`)),
  createTx: (payload) => unwrap(client.post('/ledger/transactions/', payload)),
}

/** 导出账单：响应是 CSV 文件流，不能走 unwrap 解包 */
export async function exportTransactions(params, filename) {
  const blob = await client.get('/ledger/transactions/export/', {
    params,
    responseType: 'blob',
  })
  // 出错时后端返回的是 JSON 包装，被 blob 包住，需要先还原成异常
  if (blob && blob.type && blob.type.indexOf('json') >= 0) {
    let msg = '导出失败'
    try {
      msg = JSON.parse(await blob.text()).message || msg
    } catch (e) {
      /* ignore */
    }
    throw new Error(msg)
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || '家庭账单.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return blob.size
}

export const loanApi = {
  // 一次返回 items + summary，列表页不再单独请求总览
  list: (params) => unwrap(client.get('/loans/', { params })),
  create: (payload) => unwrap(client.post('/loans/', payload)),
  detail: (id) => unwrap(client.get(`/loans/${id}/`)),
  update: (id, payload) => unwrap(client.patch(`/loans/${id}/`, payload)),
  remove: (id) => unwrap(client.delete(`/loans/${id}/`)),
  repay: (id, payload) => unwrap(client.post(`/loans/${id}/repayments/`, payload)),
  removeRepayment: (id) => unwrap(client.delete(`/loans/repayments/${id}/`)),
}

export const importApi = {
  upload: (formData) =>
    unwrap(
      client.post('/ledger/imports/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    ),
  detail: (id) => unwrap(client.get(`/ledger/imports/${id}/`)),
  confirm: (id, payload) => unwrap(client.post(`/ledger/imports/${id}/confirm/`, payload)),
  remove: (id) => unwrap(client.delete(`/ledger/imports/${id}/`)),
}