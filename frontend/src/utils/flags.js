// 功能开关：不对外发布的功能在这里统一收口，避免入口散落各处。
// 上线时把对应开关改成 true 即可，不用再到处翻页面删 v-if。

/**
 * 会员体系（会员中心、开通/续费入口）。
 * 目前不收费：后端 settings.VIP_GATED=False，付费权益对所有人开放，
 * 所以这里不展示会员中心。等要开始收费时，后端打开 VIP_GATED、这里改成 true，
 * 入口与收费一起生效。
 */
export const VIP_ENABLED = false
