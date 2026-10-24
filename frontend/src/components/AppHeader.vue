<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useModelStore } from '@/stores/model'

const route = useRoute()
const store = useModelStore()

const tabs = [
  { label: '主页', to: '/', match: (p: string) => p === '/' },
  { label: '工作台', to: '/workspace', match: (p: string) => p.startsWith('/workspace') },
]

function isActive(t: { match: (p: string) => boolean }): boolean {
  return t.match(route.path)
}

const gpuOk = computed(() => {
  const name = store.gpu.name
  return typeof name === 'string' && name.length > 0 && name !== 'CUDA 不可用'
})

let timer: number | undefined
onMounted(() => {
  store.refresh()
  timer = window.setInterval(() => store.refresh(), 5000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <header class="header">
    <div class="logo">
      <span class="logo-mark">AI</span>
      <span class="logo-text">AI 图像工作站</span>
    </div>
    <nav class="tabs">
      <RouterLink v-for="t in tabs" :key="t.to" :to="t.to" class="tab" :class="{ active: isActive(t) }">
        {{ t.label }}
      </RouterLink>
    </nav>
    <div class="header-right">
      <span class="gpu-mini" :class="{ ok: gpuOk }" title="GPU 状态">
        <span class="gpu-dot" />
        {{ gpuOk ? 'GPU 就绪' : 'GPU 不可用' }}
      </span>
      <span class="icon-btn" title="设置">⚙</span>
      <span class="icon-btn" title="帮助">?</span>
    </div>
  </header>
</template>

<style scoped>
.header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  height: var(--header-h);
  background: var(--bg-elev);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  z-index: 10;
}
.header::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, var(--primary), transparent 70%);
  opacity: 0.5;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 15px;
}
.logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35);
}
.logo-text {
  letter-spacing: 0.2px;
}
.tabs {
  display: flex;
  gap: 6px;
  flex: 1;
}
.tab {
  padding: 8px 18px;
  border-radius: 999px;
  color: var(--text-dim);
  text-decoration: none;
  font-size: 14px;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.tab:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border);
}
.tab.active {
  color: #fff;
  background: var(--gradient-brand);
  border-color: transparent;
  box-shadow: 0 3px 12px rgba(99, 102, 241, 0.35);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gpu-mini {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--text-dim);
  background: var(--panel);
  border: 1px solid var(--border);
}
.gpu-mini.ok {
  color: var(--success);
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.08);
}
.gpu-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
}
.gpu-mini.ok .gpu-dot {
  background: var(--success);
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.7);
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: var(--text-dim);
  cursor: pointer;
}
.icon-btn:hover {
  background: var(--panel);
  color: var(--text);
}
</style>
