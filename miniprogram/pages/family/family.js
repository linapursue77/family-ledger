const api = require('../../utils/api')
const { requireLogin } = require('../../utils/request')
const { yuan } = require('../../utils/money')
const { appPayload, invitePayload, toAppMessage, toTimeline } = require('../../utils/share')

const BOOKS = [
  { value: 'husband', label: '账本一' },
  { value: 'wife', label: '账本二' },
  { value: 'shared', label: '共同账本' },
]
const ROLE_TEXT = { owner: '主账号', member: '成员' }

// 授权项：与 H5 Family.vue 的 PERM_CONFIG 一一对应，改一端记得同步另一端
// choice 为二选一，switch 为开关
const PERM_CONFIG = [
  {
    key: 'report_view',
    label: '查看账单报表',
    desc: '对方能看到哪些账单与统计',
    type: 'choice',
    options: [
      { v: 'all', l: '全家庭' },
      { v: 'own', l: '仅自己' },
    ],
  },
  {
    key: 'account_view',
    label: '查看账户资产',
    desc: '对方能看到哪些账户与余额',
    type: 'choice',
    options: [
      { v: 'all', l: '全家庭' },
      { v: 'own', l: '仅自己' },
    ],
  },
  { key: 'allow_record', label: '允许记账', desc: '关闭后只能查看，不能新增账单', type: 'switch' },
  { key: 'show_private', label: '可见私密账目', desc: '是否包含标记为「私密」的账目', type: 'switch' },
  {
    key: 'settings_level',
    label: '家庭设置权限',
    desc: '能否邀请成员、调整阈值与授权',
    type: 'choice',
    options: [
      { v: 'full', l: '可管理' },
      { v: 'basic', l: '仅查看' },
    ],
  },
]

// 默认权限：新成员可看全家庭、能记账、看不到私密、不能改家庭设置
const DEFAULT_PERMS = {
  report_view: 'all',
  account_view: 'all',
  allow_record: true,
  show_private: false,
  settings_level: 'basic',
}

function centsToYuanText(cents) {
  return String(yuan(cents || 0))
}

Page({
  data: {
    loading: true,
    family: null,
    members: [],
    invites: [],
    myRole: '',
    isOwner: false,
    limitText: '',
    books: BOOKS,

    // 邀请：perms 是预设权限，随邀请一起提交；permList 供模板渲染
    showInvite: false,
    inviteNickname: '',
    inviteContact: '',
    newToken: '',
    inviting: false,
    permList: PERM_CONFIG,
    perms: { ...DEFAULT_PERMS },

    // 授权调整（主账号对已有成员）
    showPerm: false,
    permForm: { ...DEFAULT_PERMS },
    permTarget: null,

    // 成员
    showMember: false,
    current: null,
    editNickname: '',
    editBookIndex: 0,

    // 阈值
    thresholds: null,
    th: { small: '', notify: '', approve: '' },
  },

  // 分享载荷：平时是应用分享，生成邀请后临时替换成邀请卡片
  _sharePayload: null,

  onShow() {
    this.load()
  },

  /*
   * 分享：小程序里邀请靠「转发小程序卡片」实现，行业通用做法是
   *   - 页面 onShareAppMessage 返回带 token 的 path
   *   - 按钮用 <button open-type="share"> 拉起转发面板
   * 另外要把「转发」入口显式打开（默认只开转发给朋友，朋友圈要单独开），
   * 否则用户从右上角菜单找不到分享朋友圈。
   */
  onLoad() {
    wx.showShareMenu({
      withShareTicket: true,
      menus: ['shareAppMessage', 'shareTimeline'],
    })
  },

  onShareAppMessage() {
    return toAppMessage(this._sharePayload || appPayload())
  },
  onShareTimeline() {
    return toTimeline(this._sharePayload || appPayload())
  },

  async load() {
    this.setData({ loading: true })
    try {
      const [fam, inv, th] = await Promise.all([
        api.familyMe(),
        api.invites().catch(() => null),
        api.thresholds().catch(() => null),
      ])
      const labels = fam.book_labels || {}

      const members = (fam.members || []).map((m) => ({
        ...m,
        roleText: ROLE_TEXT[m.role] || m.role,
        // 昵称优先，没设就退回用户名
        display: m.nickname || m.username || '成员',
        initial: (m.nickname || m.username || '成')[0],
        bookLabel: labels[m.book_type] || (BOOKS.find((b) => b.value === m.book_type) || {}).label || '—',
        permText: this.permText(m.permissions || {}),
      }))

      this.setData({
        family: fam,
        members,
        myRole: fam.my_role,
        isOwner: fam.my_role === 'owner',
        limitText: `${members.length} / ${fam.member_limit} 人`,
        invites: ((inv && inv.items) || []).map((i) => ({
          ...i,
          statusText: { pending: '待接受', accepted: '已加入', revoked: '已撤销', expired: '已过期' }[i.status] || i.status,
          dateText: (i.created_at || '').slice(0, 10),
        })),
        thresholds: th,
        th: {
          small: centsToYuanText(th && th.small_limit),
          notify: centsToYuanText(th && th.notify_limit),
          approve: centsToYuanText(th && th.approve_limit),
        },
      })
    } catch (e) {
      if (requireLogin(e)) {
        // 未登录进不了本页：提示后回上一页（各 tab 首页已有登录引导）
        wx.navigateBack({ delta: 1 })
        return
      }
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  permText(p) {
    const parts = []
    if (p.report_view === 'own') parts.push('只看自己报表')
    if (p.account_view === 'own') parts.push('只看自己账户')
    if (p.allow_record === false) parts.push('不可记账')
    if (p.show_private === false) parts.push('不看私密')
    if (p.settings_level === 'full') parts.push('可管设置')
    return parts.length ? parts.join(' · ') : '默认权限'
  },

  // ---- 邀请
  openInvite() {
    // 每次打开都重置成默认权限，避免沿用上次的选择造成误授权
    this.setData({
      showInvite: true,
      inviteNickname: '',
      inviteContact: '',
      newToken: '',
      perms: { ...DEFAULT_PERMS },
    })
    this._sharePayload = null
  },

  /** 权限项切换：choice 直接覆盖，switch 取反 */
  onPermTap(e) {
    const { key, val } = e.currentTarget.dataset
    const cur = this.data.perms
    // dataset 里拿到的 val 只有 choice 才有；switch 走取反
    this.setData({
      perms: { ...cur, [key]: val === undefined ? !cur[key] : val },
    })
  },
  closeInvite() {
    this.setData({ showInvite: false })
    // 邀请框关掉后，右上角分享恢复成「分享应用」
    this._sharePayload = null
  },
  onInviteNickname(e) {
    this.setData({ inviteNickname: e.detail.value })
  },
  onInviteContact(e) {
    this.setData({ inviteContact: e.detail.value })
  },
  async onCreateInvite() {
    if (this.data.inviting) return
    const nickname = (this.data.inviteNickname || '').trim()
    if (!nickname) return wx.showToast({ title: '请填写称呼', icon: 'none' })
    this.setData({ inviting: true })
    try {
      const res = await api.createInvite({
        nickname,
        contact: (this.data.inviteContact || '').trim(),
        // 预设权限：接受邀请时由后端写入成员权限
        permissions: { ...this.data.perms },
      })
      // token 只在生成这一刻返回一次，之后列表里查不到
      const token = res.token || ''
      this.setData({ newToken: token })
      // 有 token 时把分享对象换成邀请卡片，对方点开直落 join 页
      const owner = (this.data.members || []).find((m) => m.role === 'owner')
      this._sharePayload = token
        ? invitePayload(token, (owner && (owner.display || owner.nickname)) || '')
        : null
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      this.setData({ inviting: false })
    }
  },
  copyToken() {
    wx.setClipboardData({
      data: this.data.newToken,
      success: () => wx.showToast({ title: '已复制', icon: 'success' }),
    })
  },
  onRevokeInvite(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '撤销这条邀请',
      content: '撤销后对方不能再用它加入。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.revokeInvite(id)
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '撤销失败', icon: 'none' })
        }
      },
    })
  },

  // ---- 成员
  openMember(e) {
    const m = this.data.members.find((i) => i.id === e.currentTarget.dataset.id)
    if (!m) return
    this.setData({
      showMember: true,
      current: m,
      editNickname: m.nickname || '',
      editBookIndex: Math.max(0, BOOKS.findIndex((b) => b.value === m.book_type)),
    })
  },
  closeMember() {
    this.setData({ showMember: false })
  },
  onEditNickname(e) {
    this.setData({ editNickname: e.detail.value })
  },
  onEditBook(e) {
    this.setData({ editBookIndex: Number(e.detail.value) })
  },
  async onSaveMember() {
    const m = this.data.current
    if (!m) return
    try {
      await api.updateMember(m.id, {
        nickname: (this.data.editNickname || '').trim(),
        book_type: BOOKS[this.data.editBookIndex].value,
      })
      wx.showToast({ title: '已保存', icon: 'success' })
      this.setData({ showMember: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    }
  },
  /** 打开授权调整弹层：回填该成员当前权限 */
  openPerm() {
    const m = this.data.current
    if (!m) return
    this.setData({
      showPerm: true,
      permTarget: m,
      permForm: { ...DEFAULT_PERMS, ...(m.permissions || {}) },
    })
  },
  closePerm() {
    this.setData({ showPerm: false })
  },
  onPermFormTap(e) {
    const { key, val } = e.currentTarget.dataset
    const cur = this.data.permForm
    this.setData({
      permForm: { ...cur, [key]: val === undefined ? !cur[key] : val },
    })
  },
  async onSavePerm() {
    const m = this.data.permTarget
    if (!m) return
    try {
      // 后端 MemberPermissionSerializer 收扁平字段（partial=True 合并到原权限上）
      await api.updateMemberPerms(m.id, { ...this.data.permForm })
      wx.showToast({ title: '授权已更新', icon: 'success' })
      this.setData({ showPerm: false, showMember: false })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    }
  },

  onRemoveMember() {
    const m = this.data.current
    if (!m) return
    wx.showModal({
      title: `移除「${m.display}」`,
      content: '移除后 TA 不能再记账，历史账单仍留在家庭里。',
      confirmColor: '#e24b4a',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.removeMember(m.id)
          this.setData({ showMember: false })
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '移除失败', icon: 'none' })
        }
      },
    })
  },
  onTransferOwner() {
    const m = this.data.current
    if (!m) return
    wx.showModal({
      title: `把主账号转给「${m.display}」`,
      content: '转让后你将变为普通成员，家庭设置权一并交出。',
      success: async (res) => {
        if (!res.confirm) return
        try {
          await api.transferOwner(m.id)
          this.setData({ showMember: false })
          wx.showToast({ title: '已转让', icon: 'success' })
          await this.load()
        } catch (err) {
          wx.showToast({ title: err.message || '转让失败', icon: 'none' })
        }
      },
    })
  },

  // ---- 协商阈值
  onTh(e) {
    this.setData({ [`th.${e.currentTarget.dataset.field}`]: e.detail.value })
  },
  async onSaveThresholds() {
    const toCents = (v) => Math.round(Number(v || 0) * 100)
    const payload = {
      small_limit: toCents(this.data.th.small),
      notify_limit: toCents(this.data.th.notify),
      approve_limit: toCents(this.data.th.approve),
    }
    if (!(payload.small_limit < payload.notify_limit)) {
      return wx.showToast({ title: '小额需小于知会', icon: 'none' })
    }
    if (!(payload.notify_limit < payload.approve_limit)) {
      return wx.showToast({ title: '知会需小于申请', icon: 'none' })
    }
    try {
      await api.saveThresholds(payload)
      wx.showToast({ title: '已保存', icon: 'success' })
      await this.load()
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    }
  },
})
