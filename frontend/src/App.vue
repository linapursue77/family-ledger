<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import TabBar from '@/components/TabBar.vue'

const route = useRoute()
// 登录页不显示底部 TabBar
const showTab = computed(() => route.meta.tab !== false)
</script>

<template>
  <div class="phone-shell">
    <router-view />
  </div>
  <!-- 挂到 body 根节点：脱离任何滚动/变换容器，保证 fixed 始终钉在视口底部，不随页面滚动 -->
  <Teleport to="body">
    <TabBar v-if="showTab" />
  </Teleport>
</template>