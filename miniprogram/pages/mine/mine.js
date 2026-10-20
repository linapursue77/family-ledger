const api = require('../../utils/api')
const { yuan } = require('../../utils/money')
const { requireLogin } = require('../../utils/request')
const { appPayload, toAppMessage, toTimeline } = require('../../utils/share')

// 隐私额度：与 H5 Mine.vue / 后端 ProfileUpdateView 同口径（¥100 ~ ¥5000）
const PRIVACY_MIN = 100
const PRIVACY_MAX = 5000
const PRIVACY_PRESETS = [300, 500, 1000, 2000, 5000]

Page({
  data: {
    user: null,
    family: null,
    isLoggedIn: false,

    // 资产总览
    myAssets: '0.00',
    monthExpense: '0.00',
    monthBalance: '0.00',

    // 信任规则
    thrText: '未设置',
    privacyText: '未设置',
    showPrivacy: false,
    privacyYuan: 500,
    privacyPresets: PRIVACY_PRESETS,
    privacySaving: false,
    privacyMsg: '',

    // 资金往来
    loanText: '',
    retText: '',
    recText: '',

    // 家庭管理
    memberCountText: '',
    ownerText: '未设置',
    inviteText: '›',

    // 智能分析三态分开，避免互相顶掉：
    //   aiSwitchOn  开关视觉（用户是否已打开）
    //   aiAvailable 真正可用（enabled + 有 Key）
    //   showAiForm  配置区是否展开
    aiAvailable: false,
    aiSwitchOn: false,
    showAiForm: false,
    // 配置表单（与 H5 Mine.vue 的 aiForm 字段一一对应）
    aiProviders: [
      { value: 'deepseek', label: 'DeepSeek', model: 'deepseek-chat' },
      { value: 'qwen', label: '通义千问', model: 'qwen-plus' },
      { value: 'kimi', label: 'Kimi', model: 'moonshot-v1-8k' },
      { value: 'openai', label: 'OpenAI', model: 'gpt-4o-mini' },
      { value: 'custom', label: '自定义', model: '' },
    ],
    aiProviderIndex: 0,
    aiModel: 'deepseek-chat',
    aiBaseUrl: '',
    aiApiKey: '',
    aiHasKey: false,
    aiSaving: false,
    aiTesting: false,
    aiMsg: '',

    // 登录密码
    showPwd: false,
    pwdOld: '',
    pwdNew: '',
    pwdConfirm: '',
    pwdSaving: false,
    hasPassword: false,
    pwdTitle: '设置密码',
    pwdText: '未设置',
  },

  onShow() {
    this.load()
  },

  /**
   * 下拉刷新：主信息与各模块状态一起重取。
   * load() 内部会再触发 loadExtras()，这里 await 它即可，
   * 拉完才 stop，保证转圈时间和实际耗时一致。
   */
  async onPullDownRefresh() {
    try {
      await this.load()
    } finally {
      wx.stopPullDownRefresh()
    }
  },

  async load() {
    try {
      // me / accounts / overview 一起拉，任一失败都不该拖垮整页
      const [me, accs, ov] = await Promise.all([
        api.me(),
        api.accounts(),
        api.overview({ preset: 'last_month' }).catch(() => null),
      ])
      const hasPwd = !!me.user.has_password
      const list = accs.items || accs || []
      // 我的资产 = 我名下账户余额合计；对方账户不计入
      const mine = list.filter((a) => a.is_mine !== false)
      const assets = mine.reduce((s, a) => s + (Number(a.balance_cents) || 0), 0)
      // 隐私额度回填：没设置过就按默认 ¥500 起
      const pv = Math.round(Number(me.user.privacy_limit_cents || 500000) / 100)
      this.setData({
        isLoggedIn: true,
        user: me.user,
        family: me.family,
        hasPassword: hasPwd,
        pwdTitle: hasPwd ? '修改密码' : '设置密码',
        pwdText: hasPwd ? '已设置' : '未设置',
        myAssets: yuan(assets).toFixed(2),
        monthExpense: ov ? yuan(ov.expense_cents).toFixed(2) : '0.00',
        monthBalance: ov ? yuan(ov.balance_cents).toFixed(2) : '0.00',
        privacyText: me.user.privacy_limit_cents == null ? '未设置' : `每月 ¥${pv}`,
        privacyYuan: pv,
      })
      // 下面几项各自独立拉，失败只留空，不影响主信息展示
      this.loadExtras()
    } catch (e) {
      if (requireLogin(e)) {
        this.setData({ isLoggedIn: false, user: null, family: null })
        return
      }
      wx.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  },

  /** 阈值 / 借贷 / 收益 / 定时 / 家庭 / AI 状态：都属锦上添花，失败就留空 */
  async loadExtras() {
    const tasks = [
      // 协商阈值
      api
        .thresholds()
        .then((t) => {
          if (!t) return this.setData({ thrText: '未设置' })
          const y = (c) => Math.round(Number(c) || 0) / 100
          this.setData({
            thrText: `¥${y(t.small_limit)} / ¥${y(t.notify_limit)} / ¥${y(t.approve_limit)}`,
          })
        })
        .catch(() => this.setData({ thrText: '未设置' })),

      // 借钱来往：只显示借出 / 借入
      api
        .loans()
        .then((r) => {
          const s = (r && r.summary) || null
          if (!s) return this.setData({ loanText: '' })
          const parts = []
          if (s.lend_cents) parts.push(`借出 ¥${Math.round(s.lend_cents / 100)}`)
          if (s.borrow_cents) parts.push(`借入 ¥${Math.round(s.borrow_cents / 100)}`)
          this.setData({ loanText: parts.join(' · ') })
        })
        .catch(() => this.setData({ loanText: '' })),

      // 收益管理：只汇总开了收益的账户
      api
        .returns()
        .then((s) => {
          if (!s || !s.has_invest) return this.setData({ retText: '' })
          const c = Number(s.profit_cents || 0)
          const sign = c > 0 ? '+' : c < 0 ? '-' : ''
          this.setData({ retText: `${sign}¥${Math.round(Math.abs(c) / 100)}` })
        })
        .catch(() => this.setData({ retText: '' })),

      // 定时记账：显示启用中的规则数
      api
        .recurringList()
        .then((list) => {
          const n = (list || []).filter((r) => r.is_active).length
          this.setData({ recText: n ? `${n} 条运行中` : '' })
        })
        .catch(() => this.setData({ recText: '' })),

      // 家庭成员 / 上限 / 主账号
      api
        .familyMe()
        .then((f) => {
          if (!f) return
          const members = f.members || []
          const owner = members.find((m) => m.role === 'owner')
          const full = members.length >= (f.member_limit || 5)
          this.setData({
            memberCountText: `${members.length}/${f.member_limit || 5} 人`,
            ownerText: owner ? `当前：${owner.nickname || owner.username}` : '未设置',
            inviteText: full ? '已满' : '›',
          })
        })
        .catch(() => {}),

      // AI 状态：直接读家庭配置，比借 reportInsight 更快也更准
      // （reportInsight 会顺带跑一遍分析，纯查状态没必要）
      api
        .aiConfig()
        .then((cfg) => {
          if (!cfg) return
          const idx = Math.max(
            0,
            this.data.aiProviders.findIndex((p) => p.value === cfg.provider)
          )
          this.setData({
            // 用后端的 usable（启用 + Key + 地址 + 模型齐备），
            // 只认 enabled 会出现「开关亮着但报告页其实还在跑本地规则」
            aiAvailable: !!(cfg.enabled && cfg.has_key),
            // 开关视觉跟随后端启用状态，页面重进时不会丢失
            aiSwitchOn: !!cfg.enabled,
            aiHasKey: !!cfg.has_key,
            aiProviderIndex: idx,
            aiModel: cfg.model || this.data.aiProviders[idx].model,
            aiBaseUrl: cfg.base_url || '',
          })
        })
        .catch(() => {}),
    ]
    await Promise.all(tasks)
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

  // ---------- 隐私额度 ----------
  togglePrivacy() {
    if (this._guardLogin()) return
    this.setData({ showPrivacy: !this.data.showPrivacy, privacyMsg: '' })
  },
  onPrivacyPreset(e) {
    this.setData({ privacyYuan: Number(e.currentTarget.dataset.val) })
  },
  onPrivacyInput(e) {
    this.setData({ privacyYuan: e.detail.value })
  },
  async onSavePrivacy() {
    const n = Math.round(Number(this.data.privacyYuan))
    if (!n || n < PRIVACY_MIN || n > PRIVACY_MAX) {
      this.setData({ privacyMsg: `额度需在 ¥${PRIVACY_MIN} ~ ¥${PRIVACY_MAX} 之间` })
      return
    }
    this.setData({ privacySaving: true, privacyMsg: '' })
    try {
      const user = await api.updateProfile({ privacy_limit_cents: n * 100 })
      this.setData({
        user,
        privacyText: `每月 ¥${n}`,
        privacyYuan: n,
        privacyMsg: `已保存：每月 ¥${n}，本月立即生效`,
      })
    } catch (e) {
      this.setData({ privacyMsg: e.message || '保存失败' })
    } finally {
      this.setData({ privacySaving: false })
    }
  },

  // ---------- 登录密码 ----------
  openPwd() {
    if (this._guardLogin()) return
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
        title: hasPassword ? '密码已修改' : '已设置，可用手机号登录网页版',
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

  // ---------- 页面跳转 ----------
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
  goFamily() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/family/family' })
  },
  /*
   * 家庭成员与邀请 / 主账号 / 协商阈值都落在同一个 family 页。
   * 该页是单页滚动结构（成员 → 邀请 → 阈值），不接收 view 参数，
   * 所以统一跳同一个地址，用户滑动即可到对应区块。
   */
  goOwner() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/family/family' })
  },
  goThreshold() {
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/family/family' })
  },
  /**
   * AI 开关（与 H5 一致）：点一下立刻变色，再看是否需要配置。
   *   打开 - 已配好 Key → 直接启用并收起表单；
   *   打开 - 还没配 Key → 开关保持绿色并展开表单，让用户就地填；
   *   关闭 → 变灰 + 收起配置区 + 后端 enabled=false，报告页回落本地规则。
   * aiSwitchOn 是视觉态，aiAvailable 是「真正可用」，两者分开才不会点不动。
   */
  async onAiToggle(e) {
    if (this._guardLogin()) return
    const on = !!e.detail.value
    // 先给视觉反馈，不能等接口回来才变色
    this.setData({ aiSwitchOn: on, aiMsg: '' })

    if (!on) {
      // 关闭：收起表单；没配置过的无需调接口
      this.setData({ showAiForm: false })
      if (!this.data.aiAvailable) return
      try {
        await api.saveAiConfig({ enabled: false })
        this.setData({ aiAvailable: false })
        wx.showToast({ title: '已切回本地分析', icon: 'none' })
      } catch (err) {
        // 落库失败要把开关拨回去，否则界面与配置不一致
        this.setData({ aiSwitchOn: true, aiAvailable: true, aiMsg: err.message || '切换失败' })
      }
      return
    }

    // 打开：展开配置表单；已有 Key 的直接启用
    this.setData({ showAiForm: true })
    if (!this.data.aiHasKey) {
      this.setData({ aiMsg: '请填写 API Key 并保存，保存后即启用' })
      return
    }
    try {
      await api.saveAiConfig({ enabled: true })
      this.setData({ aiAvailable: true, showAiForm: false })
      wx.showToast({ title: '已启用 AI 分析', icon: 'success' })
    } catch (err) {
      this.setData({ aiSwitchOn: false, aiAvailable: false, aiMsg: err.message || '开启失败' })
    }
  },

  onAiProvider(e) {
    const idx = Number(e.detail.value)
    const p = this.data.aiProviders[idx]
    this.setData({
      aiProviderIndex: idx,
      // 换服务商时同步带出默认模型名，省得用户手输
      aiModel: p.model || this.data.aiModel,
    })
  },
  onAiModel(e) {
    this.setData({ aiModel: e.detail.value })
  },
  onAiBaseUrl(e) {
    this.setData({ aiBaseUrl: e.detail.value })
  },
  onAiApiKey(e) {
    this.setData({ aiApiKey: e.detail.value })
  },

  /** 测试连接：只校验 Key 与地址是否通，不落库 */
  async onTestAi() {
    const key = this.data.aiApiKey.trim()
    if (!key && !this.data.aiHasKey) {
      this.setData({ aiMsg: '请先填写 API Key' })
      return
    }
    this.setData({ aiTesting: true, aiMsg: '' })
    try {
      const r = await api.testAi({
        provider: this.data.aiProviders[this.data.aiProviderIndex].value,
        model: this.data.aiModel.trim(),
        base_url: this.data.aiBaseUrl.trim(),
        api_key: key,
      })
      this.setData({ aiMsg: r && r.ok ? '连接成功' : (r && r.message) || '连接失败' })
    } catch (e) {
      this.setData({ aiMsg: e.message || '连接失败' })
    } finally {
      this.setData({ aiTesting: false })
    }
  },

  /** 保存并启用：保存成功后收起表单，开关保持打开 */
  async onSaveAi() {
    const provider = this.data.aiProviders[this.data.aiProviderIndex].value
    const model = this.data.aiModel.trim()
    const key = this.data.aiApiKey.trim()
    if (!model) {
      this.setData({ aiMsg: '请填写模型名' })
      return
    }
    if (!key && !this.data.aiHasKey) {
      this.setData({ aiMsg: '请填写 API Key' })
      return
    }
    if (provider === 'custom' && !this.data.aiBaseUrl.trim()) {
      this.setData({ aiMsg: '自定义服务商需要填写接口地址' })
      return
    }
    this.setData({ aiSaving: true, aiMsg: '' })
    try {
      const cfg = await api.saveAiConfig({
        provider,
        model,
        base_url: this.data.aiBaseUrl.trim(),
        // 留空表示沿用已保存的 Key（后端按空值跳过覆盖）
        api_key: key,
        enabled: true,
      })
      this.setData({
        aiAvailable: true,
        // 保存即启用：开关也要跟着变绿，否则用户看不出已经生效
        aiSwitchOn: true,
        aiHasKey: true,
        aiApiKey: '',
        showAiForm: false,
        aiModel: (cfg && cfg.model) || model,
      })
      wx.showToast({ title: '已启用 AI 分析', icon: 'success' })
    } catch (e) {
      this.setData({ aiMsg: e.message || '保存失败' })
    } finally {
      this.setData({ aiSaving: false })
    }
  },

  /**
   * AI 智能分析：跳到报告页看结论。
   * 配了大模型报告页自动走 AI，没配自动走本地规则，这里不拦截流程。
   */
  goReportAI() {
    if (this._guardLogin()) return
    wx.switchTab({ url: '/pages/report/report' })
  },
  goImport() {
    // 与 H5 一致：导入是低频功能，入口放在「我的」里，不占底部 tab
    if (this._guardLogin()) return
    wx.navigateTo({ url: '/pages/import/import' })
  },

  // ---------- 小程序做不到的事，如实说明 ----------
  tipExport() {
    wx.showModal({
      title: '导出账单',
      content: '小程序里没有文件下载目录，导出 CSV 请用网页版「我的 → 导出账单」。',
      showCancel: false,
      confirmText: '知道了',
    })
  },

  // ---- 分享：右上角菜单和列表里的「分享给好友」按钮都会走到这里
  onShareAppMessage() {
    return toAppMessage(appPayload())
  },
  onShareTimeline() {
    return toTimeline(appPayload())
  },
})
