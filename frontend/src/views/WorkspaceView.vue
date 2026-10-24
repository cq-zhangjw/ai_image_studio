<script setup lang="ts">
import { useRoute } from 'vue-router'
import ModelSidebar from '@/components/ModelSidebar.vue'

const route = useRoute()

const subTabs = [
  { label: '文生图', icon: '🖼', to: '/workspace/text-to-image', key: 'text-to-image' },
  { label: '图像编辑', icon: '✂', to: '/workspace/edit', key: 'edit' },
  { label: '图像放大', icon: '🔍', to: '/workspace/upscale', key: 'upscale' },
]

function activeKey(): string {
  return route.path.split('/')[2] ?? 'text-to-image'
}
</script>

<template>
  <div class="workspace">
    <!-- 工作台子 tab 条 -->
    <div class="ws-tabs">
      <RouterLink
        v-for="t in subTabs"
        :key="t.to"
        :to="t.to"
        class="ws-tab"
        :class="{ active: activeKey() === t.key }"
      >
        <span class="ws-icon">{{ t.icon }}</span>
        {{ t.label }}
      </RouterLink>
    </div>

    <div class="ws-body">
      <ModelSidebar />
      <main class="ws-main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.ws-tabs {
  position: relative;
  display: flex;
  gap: 8px;
  padding: 18px 16px 10px;
  background: var(--glass-bg);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ws-tabs::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, var(--primary), transparent 70%);
  opacity: 0.4;
}
.ws-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 16px;
  border-radius: 999px;
  color: var(--text-dim);
  text-decoration: none;
  font-size: 13px;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.ws-tab:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border);
}
.ws-tab.active {
  color: #fff;
  background: var(--gradient-brand);
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
}
.ws-icon {
  font-size: 14px;
  line-height: 1;
}
.ws-body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.ws-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
