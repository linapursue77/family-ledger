const { request, upload } = require('./request')

module.exports = {
  // 认证
  login: (data) => request('POST', '/auth/login/', data),
  // 微信一键登录：code 必填；phone_code 来自手机号快速验证组件，可为空（静默登录）
  wechatLogin: (data) => request('POST', '/auth/wechat/login/', data),
  me: () => request('GET', '/auth/me/'),
  // 设置 / 修改登录密码：无密码（纯微信登录）时不用传 old_password
  updatePassword: (data) => request('POST', '/auth/password/', data),
  // 账号打通：给微信账号补手机号（可顺带设密码），之后 H5 也能登录
  bindPhone: (data) => request('POST', '/auth/bind-phone/', data),
  // 账号打通：把当前微信绑到已登录账号（手机号注册的老用户走这条）
  bindWechat: (data) => request('POST', '/auth/wechat/openid/', data),
  // 改个人资料：「我的」页的隐私额度走这里，只传 privacy_limit_cents
  updateProfile: (data) => request('PATCH', '/auth/profile/', data),

  // 账户
  accounts: () => request('GET', '/accounts/'),
  createAccount: (data) => request('POST', '/accounts/', data),
  // 编辑账户：打开「纳入收益管理」用同一个接口，本金单独走 principal
  updateAccount: (id, data) => request('PATCH', `/accounts/${id}/`, data),
  deleteAccount: (id) => request('DELETE', `/accounts/${id}/`),
  adjustAccount: (id, data) => request('POST', `/accounts/${id}/adjust/`, data),
  setPrincipal: (id, data) => request('POST', `/accounts/${id}/principal/`, data),
  // 投资收益管理：?book=husband 只看某个账本
  returns: (params) => request('GET', '/accounts/returns/', params),
  // 家庭总资产明细与净值曲线：首页资产卡下钻
  netValue: () => request('GET', '/accounts/netvalue/'),

  // AI 大模型配置：「我的 → 智能分析」开关展开的配置表单用
  aiConfig: () => request('GET', '/ledger/ai/config/'),
  saveAiConfig: (data) => request('PUT', '/ledger/ai/config/', data),
  testAi: (data) => request('POST', '/ledger/ai/config/test/', data),

  // 借贷
  loans: (params) => request('GET', '/loans/', params),
  createLoan: (data) => request('POST', '/loans/', data),
  deleteLoan: (id) => request('DELETE', `/loans/${id}/`),
  createRepayment: (id, data) => request('POST', `/loans/${id}/repayments/`, data),
  deleteRepayment: (id) => request('DELETE', `/loans/repayments/${id}/`),

  // 家庭
  familyMe: () => request('GET', '/families/me/'),
  invites: () => request('GET', '/families/invitations/'),
  createInvite: (data) => request('POST', '/families/invitations/', data),
  revokeInvite: (id) => request('DELETE', `/families/invitations/${id}/revoke/`),
  // 被邀请人视角：join 落地页用，登录即可，不需要是本家庭成员
  invitePreview: (token) => request('GET', '/families/invitations/preview/', { token }),
  acceptInvite: (token) => request('POST', '/families/invitations/accept/', { token }),
  updateMember: (id, data) => request('PATCH', `/families/members/${id}/`, data),
  // 授权调整：扁平字段（report_view/account_view/allow_record/show_private/settings_level）
  updateMemberPerms: (id, data) =>
    request('PATCH', `/families/members/${id}/permissions/`, data),
  removeMember: (id) => request('DELETE', `/families/members/${id}/`),
  transferOwner: (id) => request('POST', `/families/members/${id}/transfer-owner/`),
  thresholds: () => request('GET', '/families/thresholds/'),
  saveThresholds: (data) => request('PUT', '/families/thresholds/', data),

  // 账本
  categories: (kind) => request('GET', '/ledger/categories/', { kind }),
  // 定时记账：周期规则自动生成流水
  recurringList: () => request('GET', '/ledger/recurring/'),
  recurringCreate: (data) => request('POST', '/ledger/recurring/', data),
  recurringUpdate: (id, data) => request('PATCH', `/ledger/recurring/${id}/`, data),
  recurringRemove: (id) => request('DELETE', `/ledger/recurring/${id}/`),
  recurringRun: (id) => request('POST', `/ledger/recurring/${id}/run/`, {}),
  // 记账页的「＋」新增自定义分类：kind 为 expense / income
  createCategory: (data) => request('POST', '/ledger/categories/', data),
  overview: (params) => request('GET', '/ledger/overview/', params),
  // 报告接口：与 H5 Report.vue 同源同口径
  report: (params) => request('GET', '/ledger/report/', params),
  reportInsight: (params) => request('GET', '/ledger/report/insight/', params),
  transactions: (params) => request('GET', '/ledger/transactions/', params),
  createTx: (data) => request('POST', '/ledger/transactions/', data),
  // 流水详情 / 改一笔 / 删一笔。
  // 注意：借贷流水（loan_in / loan_out）后端会拒绝改删，必须去「借钱来往」里操作。
  txDetail: (id) => request('GET', `/ledger/transactions/${id}/`),
  updateTx: (id, data) => request('PATCH', `/ledger/transactions/${id}/`, data),
  removeTx: (id) => request('DELETE', `/ledger/transactions/${id}/`),
  // 商户/备注历史：记账页的「最近用过」快捷填充
  merchantHistory: (params) => request('GET', '/ledger/merchants/history/', params),

  // 导入
  uploadImport: (filePath, platform) => upload('/ledger/imports/', filePath, { platform }),
  importDetail: (id) => request('GET', `/ledger/imports/${id}/`),
  confirmImport: (id, data) => request('POST', `/ledger/imports/${id}/confirm/`, data),
}