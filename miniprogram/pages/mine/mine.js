const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

const ACCOUNT_TYPES = [
  { key: 'personal', label: '个人账户' },
  { key: 'joint', label: '共同账户' },
  { key: 'private', label: '隐私空间' },
]
const BOOK_TYPES = [
  { key: 'husband', label: '老公账本' },
  { key: 'wife', label: '老婆账本' },
  { key: 'shared', label: '共同账本' },
]

Page({
  data: {
    user: null,
    family: null,
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
  },

  onShow() {
    this.load()
  },

  async load() {
    try {
      const [me, accounts] = await Promise.all([api.me(), api.accounts()])
      this.setData({
        user: me.user,
        family: me.family,
        accounts: (accounts.items || accounts || []).map((a) => ({
          ...a,
          balanceText: yuan(a.balance_cents).toFixed(2),
        })),
      })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },

  openAdd() {
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
})