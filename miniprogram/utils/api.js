const { request, upload } = require('./request')

module.exports = {
  // 认证
  login: (data) => request('POST', '/auth/login/', data),
  // 微信一键登录：code 必填；phone_code 来自手机号快速验证组件，可为空（静默登录）
  wechatLogin: (data) => request('POST', '/auth/wechat/login/', data),
  me: () => request('GET', '/auth/me/'),
  // 设置 / 修改登录密码：无密码（纯微信登录）时不用传 old_password
  updatePassword: (data) => request('POST', '/auth/password/', data),

  // 账户
  accounts: () => request('GET', '/accounts/'),
  createAccount: (data) => request('POST', '/accounts/', data),
  adjustAccount: (id, data) => request('POST', `/accounts/${id}/adjust/`, data),

  // 账本
  categories: (kind) => request('GET', '/ledger/categories/', { kind }),
  overview: (params) => request('GET', '/ledger/overview/', params),
  transactions: (params) => request('GET', '/ledger/transactions/', params),
  createTx: (data) => request('POST', '/ledger/transactions/', data),

  // 导入
  uploadImport: (filePath, platform) => upload('/ledger/imports/', filePath, { platform }),
  importDetail: (id) => request('GET', `/ledger/imports/${id}/`),
  confirmImport: (id, data) => request('POST', `/ledger/imports/${id}/confirm/`, data),
}