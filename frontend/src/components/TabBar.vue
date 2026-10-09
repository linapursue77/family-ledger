<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
// 账户管理、家庭管理都是「我的」的二级页：这里仍高亮「我的」，避免底部无选中态
const SUB_PAGES = ['accounts', 'family']
const activeName = computed(() => (SUB_PAGES.includes(route.name) ? 'mine' : route.name))
// 交互稿：home/add/report/mine 为 4 tab；import 页为 5 tab（导入位激活）
// icon 用 24×24 线性 path（fill:none / stroke:currentColor），风格统一、可随选中态描色
const baseTabs = [
  { name: 'home', path: '/', label: '首页', d: 'M3 9.5 12 3l9 6.5V20a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 20zM9 21.5V13h6v8.5' },
  { name: 'add', path: '/add', label: '记账', d: 'M12 5v14M5 12h14' },
  { name: 'report', path: '/report', label: '报告', d: 'M4 20.5h16M7.5 20.5v-6M12 20.5V8M16.5 20.5v-9' },
  { name: 'mine', path: '/mine', label: '我的', d: 'M20 21v-1.6a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4V21M12 11.2a4 4 0 1 0 0-8 4 4 0 0 0 0 8z' },
]
const importTab = { name: 'import', path: '/import', label: '导入', d: 'M12 3.5v11M7.5 10 12 14.5 16.5 10M5 20.5h14' }

const tabs = route.name === 'import' ? [...baseTabs.slice(0, 2), importTab, ...baseTabs.slice(2)] : baseTabs
</script>

<template>
  <div class="tabbar">
    <router-link
      v-for="t in tabs"
      :key="t.name"
      :to="t.path"
      class="tab"
      :class="{ active: activeName === t.name }"
    >
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path :d="t.d" />
      </svg>
      <span>{{ t.label }}</span>
    </router-link>
  </div>
</template>
