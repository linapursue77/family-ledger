// 微信支付调起：微信内 JSAPI、小程序 requestPayment、微信外 H5 收银台跳转。
// 后端只负责下单与回调，这里负责「把微信支付面板弹出来」。

export function isWechat() {
  const ua = (typeof navigator !== 'undefined' && navigator.userAgent) || ''
  return /micromessenger/i.test(ua)
}

export function isMiniProgram() {
  const ua = (typeof navigator !== 'undefined' && navigator.userAgent) || ''
  return (
    (typeof window !== 'undefined' && window.__wxjs_environment === 'miniprogram') ||
    /miniprogram/i.test(ua)
  )
}

/** 当前环境对应后端 VipOrder.scene */
export function payScene() {
  if (isMiniProgram()) return 'mini'
  if (isWechat()) return 'jsapi'
  return 'h5'
}

function payError(msg) {
  const cancelled = /cancel/i.test(msg || '')
  const err = new Error(cancelled ? '已取消支付' : msg || '支付失败')
  if (cancelled) err.code = 'CANCEL'
  return err
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 微信内 JSAPI：WeixinJSBridge.invoke('getBrandWCPayRequest') */
function jsapiPay(params) {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || !isWechat()) {
      reject(new Error('请在微信内完成支付'))
      return
    }
    const invoke = () => {
      window.WeixinJSBridge.invoke(
        'getBrandWCPayRequest',
        {
          appId: params.appId,
          timeStamp: params.timeStamp,
          nonceStr: params.nonceStr,
          package: params.package,
          signType: params.signType,
          paySign: params.paySign,
        },
        (res) => {
          const msg = res?.err_msg || res?.errMsg || ''
          if (msg === 'get_brand_wcpay_request:ok') resolve(res)
          else reject(payError(msg))
        }
      )
    }
    if (window.WeixinJSBridge) invoke()
    else document.addEventListener('WeixinJSBridgeReady', invoke, { once: true })
  })
}

/** 只有在真正的运行环境里才有 wx.requestPayment（小程序的 web-view 里没有） */
export function hasMiniPay() {
  const wx = typeof window !== 'undefined' ? window.wx : null
  return !!(wx && typeof wx.requestPayment === 'function')
}

/** 小程序内：wx.requestPayment */
function miniPay(params) {
  return new Promise((resolve, reject) => {
    const wx = typeof window !== 'undefined' ? window.wx : null
    if (!wx || !wx.requestPayment) {
      reject(new Error('当前环境不支持小程序支付'))
      return
    }
    wx.requestPayment({
      timeStamp: params.timeStamp,
      nonceStr: params.nonceStr,
      package: params.package,
      signType: params.signType,
      paySign: params.paySign,
      success: resolve,
      fail: (res) => reject(payError(res?.errMsg)),
    })
  })
}

/**
 * 调起微信支付。
 * @param {object} params 后端返回的 pay_params（appId/timeStamp/nonceStr/package/signType/paySign）
 * @param {string} scene mini | jsapi | h5
 */
export function requestPayment(params, scene = 'jsapi') {
  if (!params || !params.package) return Promise.reject(new Error('支付参数缺失'))
  if (scene === 'mini' && hasMiniPay()) return miniPay(params)
  // 小程序的 web-view 里没有原生支付能力，退回公众号 JSAPI
  return jsapiPay(params)
}

/**
 * 轮询直到 fn 返回真值。用于支付后确认订单状态（回调可能有延迟）。
 * @returns 最后一次结果（超时则为 falsy）
 */
export async function poll(fn, { interval = 1500, timeout = 60000 } = {}) {
  const deadline = Date.now() + timeout
  let last = null
  while (Date.now() < deadline) {
    last = await fn()
    if (last) return last
    await sleep(interval)
  }
  return last
}
