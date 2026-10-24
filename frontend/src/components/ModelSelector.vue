<script setup lang="ts">
// 模型选择：自定义下拉（深色主题下原生 select 选项文字不清晰，改可控样式）
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useModelStore } from '@/stores/model'

const props = defineProps<{
  modelValue: string
  modelId: string // 该选择器作用于哪个后端模型（用于高亮加载状态）
  /** 可选：限定可选模型（按需过滤，如编辑页只列支持编辑的模型）；缺省显示全部 */
  options?: { value: string; name: string }[]
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
const store = useModelStore()

const DEFAULT_OPTIONS = [
  { value: 'qwen-image-2.1', name: 'Qwen-Image-2.1' },
  { value: 'ernie-image', name: 'ERNIE-Image Turbo' },
  { value: 'moss-image-sft', name: 'MOSS-Image SFT' },
  { value: 'flux2-klein-4b', name: 'FLUX.2 [klein] 4B' },
  { value: 'z-image-turbo', name: 'Z-Image Turbo' },
  { value: 'sana-sprint-1.6b', name: 'SANA-Sprint 1.6B' },
  { value: 'lumina-image-2.0', name: 'Lumina-Image 2.0' },
]

const OPTIONS = computed(() => props.options ?? DEFAULT_OPTIONS)

const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

const currentName = computed(() => OPTIONS.value.find((o) => o.value === props.modelValue)?.name ?? props.modelValue)

function stateOf(id: string): string {
  const m = store.models.find((x) => x.id === id)
  if (!m) return ''
  return m.loaded ? '已加载' : m.status === 'loading' ? '加载中…' : ''
}

function choose(value: string) {
  emit('update:modelValue', value)
  open.value = false
}

function onDocClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="model-selector">
    <div ref="menuRef" class="ms" :class="{ open }">
      <button class="ms-trigger" type="button" @click.stop="open = !open">
        <span class="ms-name">{{ currentName }}</span>
        <span class="ms-arrow" :class="{ up: open }">▾</span>
      </button>
      <div v-if="open" class="ms-menu">
        <button
          v-for="opt in OPTIONS"
          :key="opt.value"
          type="button"
          class="ms-item"
          :class="{ active: opt.value === modelValue }"
          @click="choose(opt.value)"
        >
          <span class="ms-item-name">{{ opt.name }}</span>
          <span v-if="stateOf(opt.value)" class="ms-item-state">{{ stateOf(opt.value) }}</span>
        </button>
      </div>
    </div>
    <div v-if="stateOf(modelId)" class="hint">{{ stateOf(modelId) }}</div>
  </div>
</template>

<style scoped>
.model-selector {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ms {
  position: relative;
}
.ms-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--input-bg);
  color: var(--text);
  font-size: 13.5px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.ms-trigger:hover,
.ms.open .ms-trigger {
  border-color: var(--primary);
}
.ms-name {
  font-weight: 500;
}
.ms-arrow {
  font-size: 12px;
  color: var(--text-dim);
  transition: transform 0.15s;
}
.ms-arrow.up {
  transform: rotate(180deg);
}
.ms-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 50;
  background: var(--panel);
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ms-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s;
}
.ms-item:hover {
  background: var(--bg-elev);
}
.ms-item.active {
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.35);
}
.ms-item-state {
  font-size: 11px;
  opacity: 0.75;
}
.hint {
  font-size: 11px;
  color: var(--text-faint);
}
</style>
