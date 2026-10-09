const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

Page({
  data: {
    platforms: [
      { key: '', label: '自动识别' },
      { key: 'wechat', label: '微信' },
      { key: 'alipay', label: '支付宝' },
    ],
    platform: '',
    filePath: '',
    fileName: '',
    uploading: false,
    taskId: '',
    rows: [],
    stats: null,
    accounts: [],
    accountIndex: 0,
    confirmed: false,
  },

  onShow() {
    this.loadAccounts()
  },

  async loadAccounts() {
    try {
      const d = await api.accounts()
      this.setData({ accounts: d.items || d || [] })
    } catch (e) {
      /* 忽略 */
    }
  },

  onPlatform(e) {
    this.setData({ platform: e.currentTarget.dataset.key })
  },

  onChooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['csv', 'txt'],
      success: (res) => {
        const f = res.tempFiles[0]
        this.setData({ filePath: f.path, fileName: f.name })
      },
    })
  },

  async onUpload() {
    if (!this.data.filePath) {
      wx.showToast({ title: '请先选择账单文件', icon: 'none' })
      return
    }
    this.setData({ uploading: true })
    try {
      const d = await api.uploadImport(this.data.filePath, this.data.platform)
      if (d.async) {
        wx.showToast({ title: '文件较大，已转入后台解析', icon: 'none' })
        return
      }
      const rows = (d.rows || []).map((r) => ({
        ...r,
        amountText: yuan(r.amount_cents).toFixed(2),
        statusText:
          r.status === 'new'
            ? '新增'
            : r.status === 'duplicate'
            ? '重复'
            : '文件内重复',
      }))
      this.setData({ taskId: d.task.id, rows, stats: d.stats, confirmed: false })
    } catch (e) {
      wx.showToast({ title: e.message || '解析失败', icon: 'none' })
    } finally {
      this.setData({ uploading: false })
    }
  },

  onAccount(e) {
    this.setData({ accountIndex: Number(e.detail.value) })
  },

  async onConfirm() {
    if (!this.data.taskId) return
    const account_id = this.data.accounts.length
      ? this.data.accounts[this.data.accountIndex].id
      : null
    try {
      const res = await api.confirmImport(this.data.taskId, { account_id })
      wx.showToast({ title: `已导入 ${res.created} 笔`, icon: 'success' })
      this.setData({ confirmed: true })
    } catch (e) {
      wx.showToast({ title: e.message || '导入失败', icon: 'none' })
    }
  },
})