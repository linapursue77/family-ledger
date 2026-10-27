/**
 * 通用分享能力（小程序）
 *
 * 小程序是真·微信分享：右上角菜单和 <button open-type="share"> 都能拉起微信的
 * 「发送给朋友」面板，发出去的是一张小程序卡片。这里只负责统一文案与落地路径，
 * 页面侧再各挂一份到 onShareAppMessage / onShareTimeline。
 *
 * ★ 注意两个菜单的字段差异：
 *   - onShareAppMessage（会话/群）：传 path，query 直接拼在 path 后面
 *   - onShareTimeline（朋友圈）：传独立的 query 字段，不能拼 path
 */
const APP_NAME = '钱来钱往记账'
const HOME_PATH = '/pages/home/home'
const JOIN_PATH = '/pages/join/join'

/*
 * ★ 卡片图必须写死成本地图片，不能留空。
 *   imageUrl 为空时微信会实时截当前页面当卡片图，页面是长列表或刚渲染完时
 *   经常截出一张空白图，用户发出去看到的就是白板。固定图 5:4（500x400）最稳。
 */
const APP_SHARE_IMG = '/assets/share/share-app.png'
const INVITE_SHARE_IMG = '/assets/share/share-invite.png'

/** 分享应用本身 */
function appPayload() {
  return {
    title: `${APP_NAME}｜家庭一起记账，账本分得清`,
    desc: '账本分得清、报表看得懂，和家里人一起记账更省心。',
    path: HOME_PATH,
    token: '',
    imageUrl: APP_SHARE_IMG,
  }
}

/** 分享家庭邀请：对方点开卡片直接落到 join 页，token 已带上 */
function invitePayload(token, inviter) {
  return {
    title: `${inviter || '家人'} 邀请你加入家庭账本`,
    desc: '7 天内有效，点开卡片看清权限后再决定是否加入。',
    path: `${JOIN_PATH}?token=${encodeURIComponent(token)}`,
    token,
    imageUrl: INVITE_SHARE_IMG,
  }
}

/** 转成会话/群分享的返回结构 */
function toAppMessage(p) {
  return {
    title: p.title,
    path: p.path,
    imageUrl: p.imageUrl || APP_SHARE_IMG,
  }
}

/** 转成朋友圈分享的返回结构 */
function toTimeline(p) {
  return {
    title: p.title,
    query: p.token ? `token=${encodeURIComponent(p.token)}` : '',
    imageUrl: p.imageUrl || APP_SHARE_IMG,
  }
}

module.exports = {
  APP_NAME,
  HOME_PATH,
  JOIN_PATH,
  APP_SHARE_IMG,
  INVITE_SHARE_IMG,
  appPayload,
  invitePayload,
  toAppMessage,
  toTimeline,
}
