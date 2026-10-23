import { createRouter, createWebHashHistory } from 'vue-router'
import { VIP_ENABLED } from '@/utils/flags'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { tab: false } },
  { path: '/', name: 'home', component: () => import('@/views/Home.vue') },
  { path: '/add', name: 'add', component: () => import('@/views/Add.vue') },
  { path: '/import', name: 'import', component: () => import('@/views/Import.vue') },
  { path: '/report', name: 'report', component: () => import('@/views/Report.vue') },
  { path: '/mine', name: 'mine', component: () => import('@/views/Mine.vue') },
  // 账户管理是二级页：保留底部 TabBar，顶部关闭按钮返回「我的」
  { path: '/accounts', name: 'accounts', component: () => import('@/views/Accounts.vue') },
  // 家庭管理：成员、授权、邀请、协商阈值
  { path: '/family', name: 'family', component: () => import('@/views/Family.vue') },
  // 借钱来往：借出/借入台账，二级页保留底部 TabBar
  { path: '/loans', name: 'loans', component: () => import('@/views/Loans.vue') },
  // 收益管理：一年收益变化 + 今年收益对家庭总资产的影响
  { path: '/returns', name: 'returns', component: () => import('@/views/Returns.vue') },
  // 定时记账：周期规则自动生成流水，二级页保留底部 TabBar
  { path: '/recurring', name: 'recurring', component: () => import('@/views/Recurring.vue') },
  // 会员中心：权益介绍、套餐开通、免费试用
  { path: '/member', name: 'member', component: () => import('@/views/MemberCenter.vue') },
  // 邀请落地页：从分享链接进入，接受后才算加入家庭，因此不挂 TabBar
  { path: '/join', name: 'join', component: () => import('@/views/Join.vue'), meta: { tab: false } },
  // 管理后台：宽屏布局、不挂 TabBar，仅 is_staff 可见
  {
    path: '/console',
    component: () => import('@/views/console/ConsoleLayout.vue'),
    meta: { tab: false, wide: true, admin: true },
    children: [
      { path: '', name: 'console', component: () => import('@/views/console/Dashboard.vue') },
      {
        path: 'users',
        name: 'console-users',
        component: () => import('@/views/console/Users.vue'),
      },
      {
        path: 'members',
        name: 'console-members',
        component: () => import('@/views/console/Members.vue'),
      },
      {
        path: 'tasks',
        name: 'console-tasks',
        component: () => import('@/views/console/Tasks.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  // ★ 每次打开页面都从顶部开始：不然会沿用上一页的滚动位置，看起来像页面往上蹿
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  // 会员入口未开放：直接输 /#/member 也进不去，回到「我的」
  if (!VIP_ENABLED && to.name === 'member') {
    return { name: 'mine' }
  }
  const token = localStorage.getItem('fl_token')
  if (to.name !== 'login' && !token) {
    return { name: 'login' }
  }
  if (to.name === 'login' && token) {
    return { name: 'home' }
  }

  // 管理后台：只认 is_staff。刷新页面时 store 是空的，要先补一次 /auth/me，
  // 否则合法管理员会被自己的守卫挡在门外。
  if (to.meta.admin) {
    const auth = useAuthStore()
    if (!auth.user) {
      try {
        await auth.fetchMe()
      } catch (e) {
        return { name: 'login' }
      }
    }
    if (!auth.user || !auth.user.is_staff) {
      return { name: 'mine' }
    }
  }
})

export default router