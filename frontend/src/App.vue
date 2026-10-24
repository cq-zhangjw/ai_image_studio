<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import { useTaskStore } from '@/stores/task'

// 全局任务进度轮询：进入页面即启动，刷新浏览器后自动恢复（docs/16 §1）
const taskStore = useTaskStore()
onMounted(() => taskStore.startPolling())
onUnmounted(() => taskStore.stopPolling())
</script>

<template>
  <div class="app">
    <AppHeader />
    <div class="body">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.body {
  display: flex;
  flex: 1;
  min-height: 0;
}
</style>
