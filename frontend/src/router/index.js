import { createRouter, createWebHashHistory } from 'vue-router'

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
  // 邀请落地页：从分享链接进入，接受后才算加入家庭，因此不挂 TabBar
  { path: '/join', name: 'join', component: () => import('@/views/Join.vue'), meta: { tab: false } },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  // ★ 每次打开页面都从顶部开始：不然会沿用上一页的滚动位置，看起来像页面往上蹿
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  const token = localStorage.getItem('fl_token')
  if (to.name !== 'login' && !token) {
    return { name: 'login' }
  }
  if (to.name === 'login' && token) {
    return { name: 'home' }
  }
})

export default router