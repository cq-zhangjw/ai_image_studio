<script setup lang="ts">
// 提示词优化：文本框右上角 ✨ 按钮 + 弹窗（优化结果 → 应用回填 / 复制 / 关闭）
import { ref } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  modelValue: string
  modelId?: string
  disabled?: boolean
  layout?: boolean
}>()

const emit = defineEmits<{
  (e: 'apply', text: string): void
}>()

const open = ref(false)
const loading = ref(false)
const error = ref('')
const original = ref('')
const optimized = ref('')
const elapsed = ref<number | null>(null)
const modelName = ref('')
const copied = ref(false)

async function runOptimize() {
  const text = props.modelValue.trim()
  if (!text) return
  loading.value = true
  error.value = ''
  copied.value = false
  try {
    const res = await api.optimizePrompt({
      prompt: text,
      target_model: props.modelId && props.modelId !== 'qwen-image-2.1' ? props.modelId : 'auto',
      layout: !!props.layout,
    })
    original.value = res.original
    optimized.value = res.optimized
    elapsed.value = res.elapsed_seconds
    modelName.value = res.model
    open.value = true
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function apply() {
  if (!optimized.value.trim()) return
  emit('apply', optimized.value)
  open.value = false
}

async function copy() {
  try {
    await navigator.clipboard.writeText(optimized.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <div class="optimizer-wrap">
    <button
      class="optimize-btn"
      :disabled="disabled || loading || !modelValue.trim()"
      :title="loading ? '优化中…' : 'AI 优化提示词'"
      @click="runOptimize"
    >
      <span v-if="loading" class="spinner" />
      <span v-else>✨</span>
      <span class="btn-text">{{ loading ? '优化中' : 'AI 优化' }}</span>
    </button>

    <div v-if="error" class="optimize-error">{{ error }}</div>

    <!-- 弹窗 -->
    <div v-if="open" class="modal-mask" @click.self="open = false">
      <div class="modal card">
        <div class="modal-head">
          <h3>提示词优化</h3>
          <button class="close" title="关闭" @click="open = false">×</button>
        </div>

        <div class="modal-meta">
          <span class="badge badge-ok">{{ modelName }}</span>
          <span v-if="props.layout" class="badge badge-layout">布局 JSON 模式</span>
          <span v-if="elapsed !== null" class="meta-time">耗时 {{ elapsed }}s</span>
        </div>

        <div class="cols">
          <div class="col">
            <label>原文</label>
            <textarea class="orig" :value="original" readonly></textarea>
          </div>
          <div class="col">
            <label>优化结果（可编辑）</label>
            <textarea v-model="optimized"></textarea>
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn btn-secondary" @click="copy">{{ copied ? '已复制 ✓' : '复制' }}</button>
          <button class="btn btn-secondary" @click="open = false">关闭</button>
          <button class="btn" :disabled="!optimized.trim()" @click="apply">应用回填</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.optimizer-wrap {
  position: static;
  display: inline-flex;
  align-items: center;
}
.optimize-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.optimize-btn:hover:not(:disabled) {
  background: var(--primary);
  color: #fff;
}
.optimize-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-text {
  font-weight: 600;
}
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.optimize-error {
  font-size: 12px;
  color: var(--danger);
  margin-left: 8px;
}

/* 弹窗 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}
.modal {
  width: 70vw;
  height: 70vh;
  max-height: 70vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.close {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 22px;
  line-height: 1;
}
.close:hover {
  color: var(--text);
}
.modal-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}
.meta-time {
  font-size: 12px;
  color: var(--text-dim);
}
.badge-layout {
  background: var(--primary-soft);
  color: var(--primary);
  border: 1px solid var(--primary);
}
.cols {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.col {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.col label {
  flex-shrink: 0;
  margin-bottom: 6px;
}
.col textarea {
  flex: 1;
  min-height: 0;
  width: 100%;
  resize: none;
  font-size: 13px;
  line-height: 1.6;
  overflow: auto;
}
.col .orig {
  background: var(--bg-elev);
  color: var(--text-dim);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
@media (max-width: 720px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
</style>
