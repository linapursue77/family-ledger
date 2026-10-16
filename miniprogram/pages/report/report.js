const api = require('../../utils/api')
const { yuan } = require('../../utils/money')

const PRESETS = [
  { key: 'last_month', label: '本月' },
  { key: 'last_3months', label: '近3月' },
  { key: 'last_half_year', label: '近半年' },
  { key: 'this_year', label: '今年' },
]

Page({
  data: {
    presets: PRESETS,
    activePreset: 'last_month',
    ov: null,
    loading: true,
    needLogin: false,
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const ov = await api.overview({ preset: this.data.activePreset })
      this.setData({ ov, needLogin: false })
    } catch (e) {
      if (e && e.needLogin) {
        this.setData({ needLogin: true, ov: null })
        return
      }
      wx.showToast({ title: e.message, icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  goLogin() {
    wx.navigateTo({ url: '/pages/login/login' })
  },

  onPreset(e) {
    this.setData({ activePreset: e.currentTarget.dataset.key })
    this.load()
  },
})