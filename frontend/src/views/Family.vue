<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { familyApi } from '@/api'
import ConfirmSheet from '@/components/ConfirmSheet.vue'
import { useAuthStore } from '@/stores/auth'
import { inviteSharePayload, share } from '@/utils/share'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const errorText = ref('')
const fam = ref(null)
const invites = ref({ items: [], member_limit: 5, member_count: 0 })
const thr = reactive({ small_limit: 50000, notify_limit: 200000, approve_limit: 500000 })
const toast = ref('')
let toastTimer = null

// 弹层：邀请 / 授权 / 成员资料 / 阈值
const showInvite = ref(false)
const showPerm = ref(false)
const showMember = ref(false)
const showThreshold = ref(false)

const saving = ref(false)

// ★ 确认弹层：不能用 window.confirm —— 内置预览/部分 WebView 的 sandbox 会吞掉原生弹窗，
//   调用方拿到 false 直接 return，表现成「点了没反应」。自绘弹层在任何环境都能显示。
const confirmState = reactive({ show: false, title: '', lines: [], okText: '确认', danger: false })
let confirmResolve = null

function ask({ title, lines = [], okText = '确认', danger = false }) {
  confirmState.title = title
  confirmState.lines = lines
  confirmState.okText = okText
  confirmState.danger = danger
  confirmState.show = true
  return new Promise((resolve) => {
    confirmResolve = resolve
  })
}

function answerConfirm(ok) {
  confirmState.show = false
  const fn = confirmResolve
  confirmResolve = null
  if (fn) fn(ok)
}

// 内置默认名保持中性（不预设成员关系），家庭可在账本名称里改成任意叫法
const DEFAULT_BOOK = { shared: '共同账本', husband: '账本一', wife: '账本二' }
const BOOK_LIST = [
  { code: 'shared', label: '共同账本' },
  { code: 'husband', label: '账本一' },
  { code: 'wife', label: '账本二' },
]

// ★ 授权项：中文说明 + 控件类型，授权弹层与邀请预设共用同一份配置
const PERM_CONFIG = [
  {
    key: 'report_view',
    label: '查看账单报表',
    desc: '对方能看到哪些账单与统计',
    type: 'choice',
    options: [
      { v: 'all', l: '全家庭' },
      { v: 'own', l: '仅自己' },
    ],
  },
  {
    key: 'account_view',
    label: '查看账户资产',
    desc: '对方能看到哪些账户与余额',
    type: 'choice',
    options: [
      { v: 'all', l: '全家庭' },
      { v: 'own', l: '仅自己' },
    ],
  },
  { key: 'allow_record', label: '允许记账', desc: '关闭后只能查看，不能新增账单', type: 'switch' },
  { key: 'show_private', label: '可见私密账目', desc: '是否包含标记为「私密」的账目', type: 'switch' },
  {
    key: 'settings_level',
    label: '家庭设置权限',
    desc: '能否邀请成员、调整阈值与授权',
    type: 'choice',
    options: [
      { v: 'full', l: '可管理' },
      { v: 'basic', l: '仅查看' },
    ],
  },
]

const DEFAULT_PERMS = {
  report_view: 'all',
  account_view: 'all',
  allow_record: true,
  show_private: false,
  settings_level: 'basic',
}

const THRESHOLD_FIELDS = [
  { key: 'small_limit', f: 'small', icon: '✅', label: '小额自主', desc: '≤ 该金额可直接记，无需告知对方' },
  { key: 'notify_limit', f: 'notify', icon: '🔔', label: '事后知会', desc: '超过后照常记账，并知会对方' },
  { key: 'approve_limit', f: 'approve', icon: '🤝', label: '事前申请', desc: '超过后需对方确认再支出' },
]

const members = computed(() => fam.value?.members || [])
// 后端限制：邀请 / 授权 / 移除 / 阈值 = 主账号或 settings_level=full
const isOwner = computed(() => fam.value?.my_role === 'owner')
const canManage = computed(
  () => isOwner.value || fam.value?.my_permissions?.settings_level === 'full',
)
const myId = computed(() => fam.value?.my_id || '')
const myRoleText = computed(() => (isOwner.value ? '主账号' : '成员'))
// 成员上限由后端下发（当前 5 人：1 主账号 + 4 子账号）
const memberLimit = computed(() => fam.value?.member_limit || 5)
const familyFull = computed(() => members.value.length >= memberLimit.value)

const inviteResult = ref(null)
const inviteForm = reactive({ nickname: '', contact: '' })
const invitePerms = reactive({ ...DEFAULT_PERMS })

const permTarget = ref(null)
const permForm = reactive({ ...DEFAULT_PERMS })

const memberTarget = ref(null)
const memberForm = reactive({ nickname: '', book_type: 'wife' })

// 从 Mine 的「主账号设置」跳转过来时，滚到成员区（转让入口就在那里）
const memberSec = ref(null)

const thrForm = reactive({ small: 500, notify: 2000, approve: 5000 })

function showToast(msg) {
  toast.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = ''
  }, 2600)
}

function avatar(m) {
  return (m.nickname || m.username || '?')[0]
}

function bookName(type) {
  return fam.value?.book_labels?.[type] || DEFAULT_BOOK[type] || type
}

/** 权限摘要：只显示「实际生效」的那一条，避免全排列刷屏 */
function permChips(p = {}) {
  const c = []
  c.push(p.report_view === 'own' ? '只看自己报表' : '看全家庭报表')
  c.push(p.account_view === 'own' ? '只看自己账户' : '看全部账户')
  c.push(p.allow_record === false ? '不可记账' : '可记账')
  if (p.show_private) c.push('含私密账目')
  if (p.settings_level === 'full') c.push('可管家庭设置')
  return c
}

const STATUS_TEXT = { pending: '待接受', accepted: '已接受', expired: '已过期', revoked: '已撤销' }

const inviteKeywordUrl = computed(() =>
  inviteResult.value ? `${location.origin}${location.pathname}#/join?token=${inviteResult.value.token}` : ''
)

function yuan(cents) {
  return Number(Math.round((Number(cents || 0) / 100) * 100) / 100)
}

async function load() {
  loading.value = true
  errorText.value = ''
  try {
    fam.value = await familyApi.me()
    // 非主账号也能读 /families/me/，但邀请列表要求主账号，失败不影响主流程
    if (fam.value.my_role === 'owner') {
      try {
        invites.value = (await familyApi.invitations()) || { items: [] }
      } catch (e) {
        invites.value = { items: [] }
      }
    }
  } catch (e) {
    errorText.value = e.message || '加载失败'
    fam.value = null
  } finally {
    loading.value = false
  }
}

async function loadThresholds() {
  try {
    const d = await familyApi.thresholds()
    thr.small_limit = d.small_limit
    thr.notify_limit = d.notify_limit
    thr.approve_limit = d.approve_limit
  } catch (e) {
    showToast(e.message || '阈值加载失败')
  }
}

async function reloadInvites() {
  if (!canManage.value) return
  invites.value = (await familyApi.invitations()) || { items: [] }
}

// ---------------------------------------------------------------- 邀请
function openInvite() {
  if (familyFull.value) {
    showToast(`一个家庭最多 ${memberLimit.value} 位成员，请先移除一位再邀请`)
    return
  }
  inviteResult.value = null
  inviteForm.nickname = ''
  inviteForm.contact = ''
  Object.assign(invitePerms, DEFAULT_PERMS)
  showInvite.value = true
}

async function submitInvite() {
  if (!inviteForm.nickname.trim()) return showToast('请填写对方的称呼')
  saving.value = true
  try {
    const d = await familyApi.invite({
      nickname: inviteForm.nickname.trim(),
      contact: inviteForm.contact.trim(),
      permissions: { ...invitePerms },
    })
    inviteResult.value = d
    await Promise.all([reloadInvites(), load()])
  } catch (e) {
    showToast(e.message || '生成失败')
  } finally {
    saving.value = false
  }
}

async function copyInvite() {
  if (!inviteResult.value) return
  await copyText(inviteKeywordUrl.value, '邀请链接已复制')
}

// 分享邀请给微信好友：微信内无法自定义卡片，降级为引导点右上角
const showShareGuide = ref(false)
async function shareInvite() {
  if (!inviteResult.value) return
  const r = await share(
    inviteSharePayload(inviteResult.value.token, auth.user?.nickname || auth.user?.username),
  )
  if (r === 'guide') showShareGuide.value = true
}

async function revoke(id) {
  const ok = await ask({
    title: '撤销这条邀请？',
    lines: ['撤销后邀请码立即失效，对方无法再用它加入家庭'],
    okText: '撤销',
    danger: true,
  })
  if (!ok) return
  try {
    await familyApi.revokeInvite(id)
    showToast('邀请已撤销')
    await reloadInvites()
  } catch (e) {
    showToast(e.message || '撤销失败')
  }
}

async function copyText(text, tip) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    showToast(tip)
  } catch (e) {
    showToast('复制失败，请手动选中复制')
  }
}

// ---------------------------------------------------------------- 授权
function openPerm(m) {
  permTarget.value = m
  Object.assign(permForm, {
    report_view: 'all',
    account_view: 'all',
    allow_record: true,
    show_private: false,
    settings_level: 'basic',
  })
  Object.assign(permForm, m.permissions || {})
  showPerm.value = true
}

async function savePerm() {
  saving.value = true
  try {
    await familyApi.setPermissions(permTarget.value.id, { ...permForm })
    showToast('授权已更新，立即生效')
    showPerm.value = false
    await load()
    await auth.fetchMe()
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- 成员资料
function openMember(m) {
  memberTarget.value = m
  memberForm.nickname = m.nickname || ''
  memberForm.book_type = m.book_type || 'wife'
  showMember.value = true
}

async function saveMember() {
  const payload = { nickname: memberForm.nickname.trim() }
  // 改账本仅主账号可用，避免子账号提交后被 403
  if (isOwner.value) payload.book_type = memberForm.book_type
  saving.value = true
  try {
    await familyApi.updateMember(memberTarget.value.id, payload)
    showToast('已保存')
    showMember.value = false
    await load()
    if (memberTarget.value.id === fam.value?.my_id) await auth.fetchMe()
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

/** 转让主账号：转让方会降级为普通成员，必须二次确认 */
async function transferOwner(m) {
  const name = m.nickname || m.username
  const ok = await ask({
    title: `把主账号转让给「${name}」？`,
    lines: [
      '对方将可以邀请成员、调整授权与协商阈值',
      '你将降为普通成员：仍能记账、看账，但不能再管理家庭设置',
      '双方的历史账单都不受影响',
    ],
    okText: '确认转让',
  })
  if (!ok) return
  saving.value = true
  try {
    await familyApi.transferOwner(m.id)
    showToast(`主账号已转让给「${name}」`)
    await auth.fetchMe()
    await load()
  } catch (e) {
    showToast(e.message || '转让失败')
  } finally {
    saving.value = false
  }
}

async function onRemove(m) {
  const name = m.nickname || m.username
  const ok = await ask({
    title: `移除「${name}」？`,
    lines: ['对方将退出家庭，不能再查看家庭账单', '其历史账单仍完整保留在家庭账本中'],
    okText: '移除',
    danger: true,
  })
  if (!ok) return
  try {
    await familyApi.removeMember(m.id)
    showToast('成员已移除')
    await load()
  } catch (e) {
    showToast(e.message || '移除失败')
  }
}

// ---------------------------------------------------------------- 阈值
function openThreshold() {
  thrForm.small = yuan(thr.small_limit)
  thrForm.notify = yuan(thr.notify_limit)
  thrForm.approve = yuan(thr.approve_limit)
  showThreshold.value = true
}

async function saveThreshold() {
  const small = Math.round(Number(thrForm.small || 0) * 100)
  const notify = Math.round(Number(thrForm.notify || 0) * 100)
  const approve = Math.round(Number(thrForm.approve || 0) * 100)
  if (!(small < notify && notify < approve)) {
    return showToast('请保证：小额自主 < 事后知会 < 事前申请')
  }
  saving.value = true
  try {
    const d = await familyApi.saveThresholds({
      small_limit: small,
      notify_limit: notify,
      approve_limit: approve,
    })
    thr.small_limit = d.small_limit
    thr.notify_limit = d.notify_limit
    thr.approve_limit = d.approve_limit
    showToast('协商阈值已保存')
    showThreshold.value = false
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function fmtDate(v) {
  if (!v) return ''
  return String(v).slice(0, 10)
}

onMounted(async () => {
  await load()
  await loadThresholds()
  // 从 Mine 的「邀请成员 / 家庭成员 / 协商阈值」跳转过来时，直接定位到对应区块
  if (canManage.value && route.query.invite === '1') openInvite()
  if (route.query.view === 'threshold' && canManage.value) openThreshold()
  if (route.query.view === 'members') {
    nextTick(() => memberSec.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
})
</script>

<template>
  <div class="fam-page">
    <div class="top-bar">
      <span class="top-title">👨‍👩‍👧 家庭管理</span>
      <span class="top-close" @click="router.push('/mine')">×</span>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <template v-else-if="fam">
      <!-- 家庭概览 -->
      <div class="card fam-card">
        <div class="fam-name">{{ fam.name }}</div>
        <div class="fam-meta">
          {{ members.length }}/{{ fam.member_limit }} 位成员 · 我是{{ myRoleText }}
        </div>
        <div v-if="!canManage" class="fam-tip">
          仅主账号或被授权的成员可邀请成员、调整授权与协商阈值
        </div>
      </div>

      <!-- 成员与授权 -->
      <div ref="memberSec" class="card sec">
        <div class="sec-title">
          成员与授权
          <span v-if="canManage" class="sec-note">点「授权」调整可见范围</span>
        </div>

        <div v-for="m in members" :key="m.id" class="member">
          <div class="m-avatar">{{ avatar(m) }}</div>
          <div class="m-main">
            <div class="m-name">
              {{ m.nickname || m.username }}
              <span class="tag" :class="m.role">{{ m.role === 'owner' ? '主账号' : '成员' }}</span>
              <span class="tag book">{{ bookName(m.book_type) }}</span>
            </div>
            <div class="m-perms">
              <span v-for="c in permChips(m.permissions)" :key="c" class="pchip">{{ c }}</span>
            </div>
          </div>
          <div class="m-ops">
            <template v-if="m.role !== 'owner'">
              <!-- 转让主账号永远只认现任主账号 -->
              <span v-if="isOwner" class="op transfer" @click="transferOwner(m)">设为主账号</span>
              <template v-if="m.id === myId">
                <span class="op" @click="openMember(m)">改称呼</span>
              </template>
              <template v-else-if="canManage">
                <span class="op" @click="openPerm(m)">授权</span>
                <span class="op" @click="openMember(m)">编辑</span>
                <span class="op danger" @click="onRemove(m)">移除</span>
              </template>
            </template>
          </div>
        </div>

        <button v-if="canManage" class="btn btn-primary full-btn" @click="openInvite">
          {{ familyFull ? `成员已满 · 上限 ${memberLimit} 人` : '＋ 邀请家人加入' }}
        </button>
        <div v-else class="ro-note">权限由主账号管理，如需调整请联系对方</div>
      </div>

      <!-- 邀请记录 -->
      <div v-if="canManage" class="card sec">
        <div class="sec-title">邀请记录</div>
        <div v-if="!invites.items?.length" class="ro-note">暂无邀请记录</div>
        <div v-for="it in invites.items" :key="it.id" class="invite-row">
          <div class="ir-main">
            <div class="ir-name">
              {{ it.nickname || '未命名成员' }}
              <span class="tag" :class="'s-' + it.status">{{ STATUS_TEXT[it.status] }}</span>
            </div>
            <div class="ir-sub">
              <span v-for="c in permChips(it.permissions)" :key="c">{{ c }}</span>
            </div>
          </div>
          <div class="ir-right">
            <div class="ir-date">{{ fmtDate(it.expires_at) }} 前有效</div>
            <span
              v-if="it.status === 'pending'"
              class="op danger"
              @click="revoke(it.id)"
              >撤销</span
            >
          </div>
        </div>
      </div>

      <!-- 协商阈值 -->
      <div class="card sec">
        <div class="sec-title">
          协商阈值
          <span class="sec-note">超过阈值时提醒 / 需确认</span>
        </div>
        <div v-for="t in THRESHOLD_FIELDS" :key="t.key" class="th-row">
          <div class="th-info">
            <div class="th-name">{{ t.icon }} {{ t.label }}</div>
            <div class="th-desc">{{ t.desc }}</div>
          </div>
          <div class="th-val">¥{{ yuan(thr[t.key]) }}</div>
        </div>
        <button v-if="canManage" class="btn btn-ghost full-btn" @click="openThreshold">
          调整阈值
        </button>
        <div v-else class="ro-note">阈值由主账号或被授权的成员设定</div>
      </div>
    </template>
    <div v-else class="empty">{{ errorText || '暂无数据' }}</div>

    <!-- 邀请弹层：填资料 → 生成链接/邀请码 -->
    <div v-if="showInvite" class="sheet-mask" @click="showInvite = false">
      <div class="sheet f-sheet" @click.stop>
        <div class="sheet-head">
          <span class="sheet-title">邀请家人</span>
          <span class="sheet-close" @click="showInvite = false">×</span>
        </div>

        <template v-if="!inviteResult">
          <div class="fld">
            <label class="fld-label">对方称呼</label>
            <input
              v-model="inviteForm.nickname"
              class="fld-input"
              placeholder="如：小林的账 / 日常公共账"
              maxlength="50"
            />
          </div>
          <div class="fld">
            <label class="fld-label">联系方式（选填）</label>
            <input v-model="inviteForm.contact" class="fld-input" placeholder="手机号 / 微信号" maxlength="64" />
          </div>

          <div class="fld">
            <label class="fld-label">预设权限</label>
            <div class="perm-box">
              <div v-for="p in PERM_CONFIG" :key="p.key" class="perm-row">
                <div class="pr-main">
                  <div class="pr-label">{{ p.label }}</div>
                  <div class="pr-desc">{{ p.desc }}</div>
                </div>
                <div v-if="p.type === 'choice'" class="pr-opts">
                  <span
                    v-for="o in p.options"
                    :key="o.v"
                    class="pr-opt"
                    :class="{ on: invitePerms[p.key] === o.v }"
                    @click="invitePerms[p.key] = o.v"
                    >{{ o.l }}</span
                  >
                </div>
                <div
                  v-else
                  class="mini-switch"
                  :class="{ on: !!invitePerms[p.key] }"
                  @click="invitePerms[p.key] = !invitePerms[p.key]"
                >
                  <span class="ms-dot"></span>
                </div>
              </div>
            </div>
          </div>

          <div class="f-note">加入后可在「成员与授权」里随时调整，7 天内未接受自动失效。</div>
          <button class="btn btn-primary full-btn" :disabled="saving" @click="submitInvite">
            {{ saving ? '生成中…' : '生成邀请' }}
          </button>
        </template>

        <template v-else>
          <div class="inv-ok">
            <div class="inv-ok-title">✅ 邀请已生成</div>
            <div class="inv-ok-sub">把下面任意一种方式发给对方，7 天内有效</div>
          </div>
          <div class="fld">
            <label class="fld-label">邀请链接</label>
            <div class="copy-box">
              <input class="fld-input" readonly :value="inviteKeywordUrl" @focus="$event.target.select()" />
              <span class="copy-btn" @click="copyInvite">复制</span>
            </div>
          </div>
          <div class="fld">
            <label class="fld-label">邀请码</label>
            <div class="token">{{ inviteResult.token }}</div>
          </div>
          <div class="f-note">邀请码仅显示这一次，遗失后请重新生成。</div>
          <!-- 微信生态里分享按钮统一用微信绿，与「保存/完成」等主色按钮区分 -->
          <button class="btn full-btn share-btn" @click="shareInvite">↗ 分享给微信好友</button>
          <button class="btn full-btn ghost-btn" @click="showInvite = false">完成</button>
        </template>
      </div>
    </div>

    <!-- 授权弹层 -->
    <div v-if="showPerm" class="sheet-mask" @click="showPerm = false">
      <div class="sheet f-sheet" @click.stop>
        <div class="sheet-head">
          <span class="sheet-title">调整授权 · {{ permTarget?.nickname || permTarget?.username }}</span>
          <span class="sheet-close" @click="showPerm = false">×</span>
        </div>
        <div class="perm-box">
          <div v-for="p in PERM_CONFIG" :key="p.key" class="perm-row">
            <div class="pr-main">
              <div class="pr-label">{{ p.label }}</div>
              <div class="pr-desc">{{ p.desc }}</div>
            </div>
            <div v-if="p.type === 'choice'" class="pr-opts">
              <span
                v-for="o in p.options"
                :key="o.v"
                class="pr-opt"
                :class="{ on: permForm[p.key] === o.v }"
                @click="permForm[p.key] = o.v"
                >{{ o.l }}</span
              >
            </div>
            <div
              v-else
              class="mini-switch"
              :class="{ on: !!permForm[p.key] }"
              @click="permForm[p.key] = !permForm[p.key]"
            >
              <span class="ms-dot"></span>
            </div>
          </div>
        </div>
        <div class="f-note">保存后立即生效，对方下次打开 App 即可看到新范围。</div>
        <button class="btn btn-primary full-btn" :disabled="saving" @click="savePerm">
          {{ saving ? '保存中…' : '保存授权' }}
        </button>
      </div>
    </div>

    <!-- 成员资料弹层 -->
    <div v-if="showMember" class="sheet-mask" @click="showMember = false">
      <div class="sheet f-sheet" @click.stop>
        <div class="sheet-head">
          <span class="sheet-title">成员资料</span>
          <span class="sheet-close" @click="showMember = false">×</span>
        </div>
        <div class="fld">
          <label class="fld-label">家庭内称呼</label>
          <input v-model="memberForm.nickname" class="fld-input" placeholder="如：小林" maxlength="50" />
        </div>
        <div v-if="isOwner" class="fld">
          <label class="fld-label">所属账本</label>
          <div class="chip-row">
            <div
              v-for="b in BOOK_LIST"
              :key="b.code"
              class="chip"
              :class="{ on: memberForm.book_type === b.code }"
              @click="memberForm.book_type = b.code"
            >
              {{ b.label }}
            </div>
          </div>
        </div>
        <button class="btn btn-primary full-btn" :disabled="saving" @click="saveMember">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <!-- 阈值弹层 -->
    <div v-if="showThreshold" class="sheet-mask" @click="showThreshold = false">
      <div class="sheet f-sheet" @click.stop>
        <div class="sheet-head">
          <span class="sheet-title">协商阈值</span>
          <span class="sheet-close" @click="showThreshold = false">×</span>
        </div>
        <div v-for="t in THRESHOLD_FIELDS" :key="t.key" class="th-field">
          <div class="th-field-head">
            <span class="th-f-name">{{ t.icon }} {{ t.label }}</span>
            <div class="money-input">
              <span class="cur">¥</span>
              <input v-model.number="thrForm[t.f]" type="number" min="0" inputmode="decimal" />
            </div>
          </div>
          <div class="th-desc">{{ t.desc }}</div>
        </div>
        <div class="f-note">规则：小额自主 &lt; 事后知会 &lt; 事前申请。</div>
        <button class="btn btn-primary full-btn" :disabled="saving" @click="saveThreshold">
          {{ saving ? '保存中…' : '保存阈值' }}
        </button>
      </div>
    </div>

    <ConfirmSheet
      :visible="confirmState.show"
      :title="confirmState.title"
      :lines="confirmState.lines"
      :ok-text="confirmState.okText"
      :danger="confirmState.danger"
      @ok="answerConfirm(true)"
      @cancel="answerConfirm(false)"
    />

    <div v-if="toast" class="fam-toast">{{ toast }}</div>

    <!-- 微信内分享邀请引导：自定义卡片要认证服务号，这里如实引导点右上角 -->
    <div v-if="showShareGuide" class="share-guide" @click="showShareGuide = false">
      <div class="sg-box" @click.stop>
        <div class="sg-arrow">↗</div>
        <div class="sg-title">点击右上角 ⋯ 分享</div>
        <div class="sg-step">
          自定义邀请卡片需要已认证的公众号，当前还没有接。你可以在弹出菜单里选「发送给朋友」，或先复制链接再发给对方。
        </div>
        <div class="sg-ok" @click="showShareGuide = false">知道了</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ★ 与全局 .page 同一套底部留白：内容永远不会被底部 TabBar 盖住 */
.fam-page {
  padding-bottom: calc(var(--nav-h, 60px) + env(safe-area-inset-bottom) + 16px);
  min-height: 100vh;
  background: #faf9f6;
}
.top-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: #faf9f6;
  padding: 14px 16px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.top-title {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}
.top-close {
  font-size: 22px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 4px;
}
.empty,
.ro-note {
  padding: 24px 16px;
  text-align: center;
  font-size: var(--font-sm);
  color: var(--text-muted);
}
.ro-note {
  padding: 10px 0 0;
  text-align: left;
}
.card {
  margin: 0 16px 12px;
  padding: 14px 16px;
}
.fam-name {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}
.fam-meta {
  margin-top: 4px;
  font-size: var(--font-sm);
  color: var(--text-sub);
}
.fam-tip {
  margin-top: 8px;
  font-size: var(--font-xs);
  color: var(--text-muted);
  line-height: 1.6;
}
.sec-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: var(--font-md);
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 6px;
}
.sec-note {
  font-size: var(--font-xs);
  font-weight: 400;
  color: var(--text-muted);
}

/* 成员行 */
.member {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 0.5px solid var(--divider);
}
.m-avatar {
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--primary-light);
  color: var(--primary-dark);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.m-main {
  flex: 1;
  min-width: 0;
}
.m-name {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f1efe8;
  color: var(--text-sub);
}
.tag.owner {
  background: var(--primary-light);
  color: var(--primary-dark);
}
.tag.book {
  background: #e6f4ef;
  color: #0f6e56;
}
.m-perms {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.pchip {
  font-size: 11px;
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 4px;
  border: 0.5px solid var(--border);
}
.m-ops {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
}
.op {
  font-size: var(--font-xs);
  color: var(--primary-dark);
  cursor: pointer;
  white-space: nowrap;
}
.op.danger {
  color: var(--expense);
}
.op.transfer {
  color: #0f6e56;
  font-weight: 600;
}
.full-btn {
  margin-top: 12px;
}
.ghost-btn {
  background: #f1efe8;
  color: var(--text-sub);
}
/* 微信绿：用户对绿色按钮的预期就是「转发出去」，与主色紫的保存类按钮区分开 */
.share-btn {
  background: #07c160;
  color: #fff;
  font-weight: 600;
}

/* 微信内分享引导遮罩 */
.share-guide {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.sg-box {
  width: 82%;
  max-width: 320px;
  background: #fff;
  border-radius: 14px;
  padding: 22px 20px 16px;
  text-align: center;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
}
.sg-arrow {
  font-size: 30px;
  line-height: 1;
  margin-bottom: 6px;
  text-align: right;
  color: #26215c;
}
.sg-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
.sg-step {
  font-size: 13px;
  color: #888;
  line-height: 1.6;
  margin-bottom: 16px;
}
.sg-ok {
  padding: 10px 0;
  border-radius: 8px;
  background: #26215c;
  color: #fff;
  font-size: 14px;
}

/* 邀请记录 */
.invite-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 0.5px solid var(--divider);
}
.invite-row:last-child {
  border-bottom: none;
}
.ir-name {
  font-size: var(--font-md);
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 6px;
}
.ir-sub {
  margin-top: 3px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.ir-right {
  flex: none;
  text-align: right;
}
.ir-date {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.s-pending {
  background: #faeeda;
  color: #854f0b;
}
.s-accepted {
  background: #e6f4ef;
  color: #0f6e56;
}
.s-expired,
.s-revoked {
  background: #f1efe8;
  color: var(--text-muted);
}

/* 协商阈值 */
.th-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 0.5px solid var(--divider);
}
.th-row:last-of-type {
  border-bottom: none;
}
.th-name {
  font-size: var(--font-md);
  color: var(--text-main);
  font-weight: 600;
}
.th-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.th-val {
  font-size: var(--font-num);
  font-weight: 700;
  color: var(--text-main);
  font-variant-numeric: tabular-nums;
}

/* 弹层 */
.f-sheet {
  max-height: 90vh;
  overflow-y: auto;
}
.fld {
  margin-bottom: 14px;
}
.fld-label {
  display: block;
  font-size: var(--font-sm);
  color: var(--text-sub);
  margin-bottom: 6px;
}
.fld-input {
  width: 100%;
  padding: 10px 12px;
  border: 0.5px solid var(--border);
  border-radius: var(--radius-btn);
  font-size: var(--font-md);
  color: var(--text-main);
  background: #fff;
  outline: none;
}
.fld-input:focus {
  border-color: var(--primary);
}
.f-note {
  font-size: var(--font-xs);
  color: var(--text-muted);
  line-height: 1.6;
  margin: 6px 0 12px;
}
.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip.on {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
/* 权限行：胶囊组 + 迷你开关 */
.perm-box {
  border: 0.5px solid var(--border);
  border-radius: var(--radius-btn);
  overflow: hidden;
}
.perm-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 0.5px solid var(--divider);
}
.perm-row:last-child {
  border-bottom: none;
}
.pr-main {
  flex: 1;
  min-width: 0;
}
.pr-label {
  font-size: var(--font-md);
  color: var(--text-main);
}
.pr-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.pr-opts {
  flex: none;
  display: flex;
  gap: 4px;
}
.pr-opt {
  font-size: var(--font-xs);
  padding: 4px 10px;
  border-radius: 999px;
  background: #f1efe8;
  color: var(--text-sub);
  cursor: pointer;
  white-space: nowrap;
}
.pr-opt.on {
  background: var(--primary);
  color: #fff;
}
.mini-switch {
  flex: none;
  width: 40px;
  height: 22px;
  border-radius: 20px;
  background: #e3e1da;
  position: relative;
  transition: background 0.18s;
  cursor: pointer;
}
.mini-switch .ms-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
  transition: transform 0.18s;
}
.mini-switch.on {
  background: var(--primary);
}
.mini-switch.on .ms-dot {
  transform: translateX(18px);
}
/* 邀请结果 */
.inv-ok {
  text-align: center;
  padding: 4px 0 14px;
}
.inv-ok-title {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}
.inv-ok-sub {
  margin-top: 4px;
  font-size: var(--font-xs);
  color: var(--text-muted);
}
.copy-box {
  display: flex;
  align-items: center;
  gap: 8px;
}
.copy-btn {
  flex: none;
  font-size: var(--font-xs);
  color: var(--primary-dark);
  background: var(--primary-light);
  padding: 8px 12px;
  border-radius: var(--radius-btn);
  cursor: pointer;
}
.token {
  font-size: var(--font-sm);
  word-break: break-all;
  background: #f1efe8;
  border-radius: var(--radius-btn);
  padding: 10px 12px;
  color: var(--text-body);
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
/* 阈值表单 */
.th-field {
  padding: 10px 0;
  border-bottom: 0.5px solid var(--divider);
}
.th-field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.th-f-name {
  font-size: var(--font-md);
  color: var(--text-main);
  font-weight: 600;
}
.money-input {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
  border: 0.5px solid var(--border);
  border-radius: var(--radius-btn);
  padding: 4px 10px;
  width: 120px;
}
.money-input .cur {
  color: var(--text-muted);
}
.money-input input {
  width: 100%;
  border: none;
  outline: none;
  font-size: var(--font-md);
  color: var(--text-main);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* 轻提示 */
.fam-toast {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(var(--nav-h, 60px) + 24px);
  max-width: 300px;
  z-index: 200;
  background: rgba(38, 33, 92, 0.92);
  color: #fff;
  font-size: var(--font-sm);
  padding: 10px 16px;
  border-radius: var(--radius-btn);
  box-shadow: 0 4px 16px rgba(38, 33, 92, 0.24);
}
</style>
