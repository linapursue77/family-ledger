const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')
const { appPayload, toAppMessage, toTimeline } = require('../../utils/share')

const ACCOUNT_TYPES = [
  { key: 'personal', label: '个人账户' },
  { key: 'joint', label: '共同账户' },
  { key: 'private', label: '隐私空间' },
]
const BOOK_TYPES = [
  { key: 'husband', label: '账本一' },
  { key: 'wife', label: '账本二' },
  { key: 'shared', label: '共同账本' },
]

Page({
  data: {
    user: null,
    family: null,
    isLoggedIn: false,
    accounts: [],
    accountTypes: ACCOUNT_TYPES,
    bookTypes: BOOK_TYPES,
    showAdd: false,
    newName: '',
    newIcon: '💰',
    newTypeIndex: 0,
    newBookIndex: 0,
    newBalance: '',
    saving: false,
    // 登录密码
    showPwd: false,
    pwdOld: '',
    pwdNew: '',
    pwdConfirm: '',
    pwdSaving: false,
    hasPassword: false,
    pwdTitle: '设置密码',
    pwdText: '未设置',
    // 定时记账：菜单显示启用中的规则数
    recText: '',
  },

  onShow() {
    this.load()
  },

  /** 只取启用中的规则数，失败就留空，不影响「我的」页其它数据 */
  async loadRecurring() {
    try {
      const list = await api.recurringList()
      const n = (list || []).filter((r) => r.is_active).length
      this.setData({ recText: n ? `${n} 条运行中` : '' })
    } catch (e) {
      this.setData({ recText: '' })
    }
  },

  async load() {
    try {
      const [me, accounts] = await Promise.all([api.me(), api.accounts()])
      const hasPwd = !!me.user.has_password
      this.setData({
        isLoggedIn: true,
        user: me.user,
        family: me.family,
        hasPassword: hasPwd,
        pwdTitle: hasPwd ? '修改密码' : '设置密码',
        pwdText: hasPwd ? '已设置' : '未设置',
        accounts: (accounts.items || accounts || []).map((a) => ({
          ...a,
          balanceText: yuan(a.balance_cents).toFixed(2),
        })),
      })
      this.loadRecurring()
    } catch (e) {
      // 未登录：页面照常展示，用户卡变成「点击登录」，数据区显示引导
      if (requireLogin(e)) {
        this.setData({ isLoggedIn: false, user: null, family: null, accounts: [] })
        return
      }
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },

  goLogin() {
    wx.navigateTo({ url: '/pages/login/login' })
  },

  /** 用户卡点击：未登录 → 登录页 */
  onUserTap() {
    if (!this.data.isLoggedIn) this.goLogin()
  },

  /** 功能入口统一拦一道：未登录先去登录 */
  _guardLogin() {
    if (!this.data.isLoggedIn) {
      this.goLogin()
      return true
    }
    return false
  },

  openAdd() {
    if (this._guardLogin()) return
    this.setData({ showAdd: true, newName: '', newBalance: '' })
  },
  closeAdd() {
    this.setData({ showAdd: false })
  },
  onName(e) {
    this.setData({ newName: e.detail.value })
  },
  onBalance(e) {
    this.setData({ newBalance: e.detail.value })
  },
  onType(e) {
    this.setData({ newTypeIndex: Number(e.detail.value) })
  },
  onBook(e) {
    this.setData({ newBookIndex: Number(e.detail.value) })
  },

  async onSaveAccount() {
    if (!this.data.newName) {
      wx.showToast({ title: '请输入账户名称', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    try {
      await api.createAccount({
        name: this.data.newName,
        icon: this.data.newIcon,
        type: this.data.accountTypes[this.data.newTypeIndex].key,
        book_type: this.data.bookTypes[this.data.newBookIndex].key,
        balance: this.data.newBalance || '0.00',
        bank_name: this.data.newName,
      })
      wx.showToast({ title: '已创建', icon: 'success' })
      this.setData({ showAdd: false })
      this.load()
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    } finally {
      this.setData({ saving: false })
    }
  },

  // —— 登录密码 ——
  openPwd() {
    this.setData({
      showPwd: !this.data.showPwd,
      pwdOld: '',
      pwdNew: '',
      pwdConfirm: '',
    })
  },
  onPwdOld(e) {
    this.setData({ pwdOld: e.detail.value })
  },
  onPwdNew(e) {
    this.setData({ pwdNew: e.detail.value })
  },
  onPwdConfirm(e) {
    this.setData({ pwdConfirm: e.detail.value })
  },

  async onSavePwd() {
    const { hasPassword, pwdOld, pwdNew, pwdConfirm } = this.data
    if (hasPassword && !pwdOld) {
      wx.showToast({ title: '请先填写当前密码', icon: 'none' })
      return
    }
    // 密码规则：字母+数字，不低于 6 位（与后端 validators.LetterAndDigitValidator 一致）
    if (!/^(?=.*[a-zA-Z])(?=.*\d).{6,}$/.test(pwdNew)) {
      wx.showToast({ title: '密码需字母+数字，至少 6 位', icon: 'none' })
      return
    }
    if (pwdNew !== pwdConfirm) {
      wx.showToast({ title: '两次输入的新密码不一致', icon: 'none' })
      return
    }
    this.setData({ pwdSaving: true })
    try {
      await api.updatePassword({
        old_password: pwdOld,
        new_password: pwdNew,
        confirm_password: pwdConfirm,
      })
      wx.showToast({
        title: hasPassword ? '密码已修改' : `已设置，可用手机号登录网页版`,
        icon: 'success',
      })
      this.setData({
        showPwd: false,
        pwdOld: '',
        pwdNew: '',
        pwdConfirm: '',
        hasPassword: true,
        pwdTitle: '修改密码',
        pwdText: '已设置',
      })
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' })
    } finally {
      this.setData({ pwdSaving: false })
    }
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync('fl_token')
          wx.reLaunch({ url: '/pages/login/login' })
        }
      },
    })
  },

  goAccounts() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/accounts/accounts' })
  },
  goLoans() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/loans/loans' })
  },
  goReturns() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/returns/returns' })
  },
  goRecurring() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/recurring/recurring' })
  },

  // ---- 分享：右上角菜单和列表里的「分享给好友」按钮都会走到这里
  onShareAppMessage() {
    return toAppMessage(appPayload())
  },
  onShareTimeline() {
    return toTimeline(appPayload())
  },
  goFamily() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/family/family' })
  },
  goImport() {
    // 与 H5 一致：导入是低频功能，入口放在「我的」里，不占底部 tab
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/import/import' })
  },
})