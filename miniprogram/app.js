// 后端 API 基地址。切换场景只改下面 ENV_MODE 一行，别到处手改字符串。
//
//   dev  —— 开发者工具模拟器：本机 Django（需勾「不校验合法域名」）
//   lan  —— 真机调试：手机和电脑同一 Wi-Fi，IP 换成你电脑的局域网地址
//           （查：ipconfig getifaddr en0；Django 要跑在 0.0.0.0 上）
//   prod —— 线上：备案 + HTTPS 证书就位后启用（微信后台也要配 request 合法域名）
//
// 备案期间用 dev / lan：微信的 request 合法域名必须 HTTPS 且已完成 ICP 备案，
// 备案没下来 prod 一律请求失败。
const ENV = {
  dev: 'http://127.0.0.1:8001/api/v1',
  lan: 'http://192.168.1.100:8001/api/v1',
  prod: 'https://www.qianlaiqianwang.com.cn/api/v1',
}

// 开发默认 dev；真机调试改 lan；发布前改 prod
const ENV_MODE = 'dev'

App({
  globalData: {
    apiBase: ENV[ENV_MODE],
    // 记账页是 tabBar 页，navigateTo 不能带参数过去，
    // 首页点某笔账单要编辑时把 id 放这里，记账页 onShow 取走即清空。
    editTxId: '',
    // 好友从邀请分享卡片进来但还没登录时，先把 token 存这儿，
    // login 页登录后自动带着它回到 join 页（否则 switchTab 会把返回栈清掉）
    joinToken: '',
  },
  onLaunch() {
    // 不再强制跳登录页：未登录也能浏览页面框架，只是数据区显示登录引导。
    // 登录入口在「我的」头像 和 各数据区的「立即登录」按钮。
  },
})