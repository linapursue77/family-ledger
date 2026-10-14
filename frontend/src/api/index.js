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
  // 公众号网页授权登录是否可用：后端没配 appid / secret 会返回 enabled=false，前端据此隐藏按钮
  wechatMpConfig: () => unwrap(client.get('/auth/wechat/mp/config/')),
  // 授权回来的一次性 ticket 换 token。token 不落 URL，避免经 Referer / 历史记录泄漏
  wechatMpTicket: (ticket) => unwrap(client.post('/auth/wechat/mp/ticket/', { ticket })),
  // 发起微信登录：直接跳后端授权入口，next 是授权完要回到的本站路径（可带 hash）
  wechatMpAuthorizeUrl: (next = '/') =>
    `/api/v1/auth/wechat/mp/authorize/?next=${encodeURIComponent(next)}`,
  // 注册：后端会自动建一个新家庭并把注册人设为主账号，返回 token 直接进首页
  register: (payload) => unwrap(client.post('/auth/register/', payload)),
  me: () => unwrap(client.get('/auth/me/')),
  // 个人资料：昵称 / 头像 / 隐私额度（每人一份，保存即生效）
  updateProfile: (payload) => unwrap(client.patch('/auth/profile/', payload)),
  // 设置 / 修改登录密码：无密码（纯微信登录）时不用传 old_password
  updatePassword: (payload) => unwrap(client.post('/auth/password/', payload)),
  // 忘记密码：发验证码 → 用验证码重置
  sendSmsCode: (payload) => unwrap(client.post('/auth/sms/send/', payload)),
  resetPassword: (payload) => unwrap(client.post('/auth/password/reset/', payload)),
}

export const accountApi = {
  list: () => unwrap(client.get('/accounts/')),
  netvalue: () => unwrap(client.get('/accounts/netvalue/')),
  create: (payload) => unwrap(client.post('/accounts/', payload)),
  update: (id, payload) => unwrap(client.patch(`/accounts/${id}/`, payload)),
  adjust: (id, payload) => unwrap(client.post(`/accounts/${id}/adjust/`, payload)),
  // 收益管理：总览（累计/今年收益、一年趋势、对净资产的影响），可传 { book } 只看某个账本
  returns: (params) => unwrap(client.get('/accounts/returns/', { params })),
  // 本金调整：set=盘点直接设为该值，add=定投加仓在现有本金上追加
  setPrincipal: (id, payload) => unwrap(client.post(`/accounts/${id}/principal/`, payload)),
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
  merchantHistory: (params) => unwrap(client.get('/ledger/merchants/history/', { params })),
  report: (params) => unwrap(client.get('/ledger/report/', { params })),
  reportInsight: (params) => unwrap(client.get('/ledger/report/insight/', { params })),
  aiConfig: () => unwrap(client.get('/ledger/ai/config/')),
  saveAiConfig: (payload) => unwrap(client.put('/ledger/ai/config/', payload)),
  testAiConfig: (payload) => unwrap(client.post('/ledger/ai/config/test/', payload)),
  transactions: (params) => unwrap(client.get('/ledger/transactions/', { params })),
  txDetail: (id) => unwrap(client.get(`/ledger/transactions/${id}/`)),
  createTx: (payload) => unwrap(client.post('/ledger/transactions/', payload)),
  updateTx: (id, payload) => unwrap(client.patch(`/ledger/transactions/${id}/`, payload)),
  removeTx: (id) => unwrap(client.delete(`/ledger/transactions/${id}/`)),
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

export const membershipApi = {
  // 会员中心首页：权益对比 + 在售套餐 + 我的状态 + 试用配置（游客也可访问）
  home: () => unwrap(client.get('/membership/')),
  mine: () => unwrap(client.get('/membership/mine/')),
  // 领取免费试用（每人一次）
  trial: () => unwrap(client.post('/membership/trial/')),
  // 开通 / 续费下单：scene = mini | jsapi | h5，返回调起微信支付所需参数
  createOrder: (planId, scene, nextUrl) =>
    unwrap(
      client.post('/membership/subscribe/', {
        plan_id: planId,
        scene,
        next_url: nextUrl || '',
      })
    ),
  // 订单状态：支付后轮询确认（回调延迟时后端会主动向微信查单）
  orderStatus: (orderNo) => unwrap(client.get(`/membership/orders/${orderNo}/`)),
  // 放弃支付：主动关单
  closeOrder: (orderNo) => unwrap(client.post(`/membership/orders/${orderNo}/close/`)),
  // 小程序：wx.login 的 code 绑定 openid（JSAPI 支付前必须）
  bindOpenid: (code) => unwrap(client.post('/auth/wechat/openid/', { code })),
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