const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

const BOOKS = [
  { value: 'husband', label: '账本一' },
  { value: 'wife', label: '账本二' },
  { value: 'shared', label: '共同账本' },
]
const ROLE_TEXT = { owner: '主账号', member: '成员' }

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

    // 邀请
    showInvite: false,
    inviteNickname: '',
    inviteContact: '',
    newToken: '',
    inviting: false,

    // 成员
    showMember: false,
    current: null,
    editNickname: '',
    editBookIndex: 0,

    // 阈值
    thresholds: null,
    th: { small: '', notify: '', approve: '' },
  },

  onShow() {
    this.load()
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
    this.setData({ showInvite: true, inviteNickname: '', inviteContact: '', newToken: '' })
  },
  closeInvite() {
    this.setData({ showInvite: false })
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
      })
      // token 只在生成这一刻返回一次，之后列表里查不到
      this.setData({ newToken: res.token || '' })
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
