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
  },

  onShow() {
    this.load()
  },

  async load() {
    this.setData({ loading: true })
    try {
      const ov = await api.overview({ preset: this.data.activePreset })
      this.setData({ ov })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onPreset(e) {
    this.setData({ activePreset: e.currentTarget.dataset.key })
    this.load()
  },
})