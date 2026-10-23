<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const NAV = [
  { name: 'console', label: '概览', path: '/console' },
  { name: 'console-users', label: '注册账号', path: '/console/users' },
  { name: 'console-members', label: '会员', path: '/console/members' },
  { name: 'console-tasks', label: '定时任务', path: '/console/tasks' },
]

const active = computed(() => route.name)
</script>

<template>
  <div class="console-shell">
    <div class="console-head">
      <div class="console-title">
        🛠 管理后台
        <span class="console-badge">仅管理员可见</span>
      </div>
      <nav class="console-nav">
        <router-link
          v-for="n in NAV"
          :key="n.name"
          :to="n.path"
          :class="{ active: active === n.name }"
          >{{ n.label }}</router-link
        >
      </nav>
      <a class="console-back" @click="router.push('/mine')">← 返回我的</a>
    </div>

    <router-view />
  </div>
</template>
