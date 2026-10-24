<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTaskStore } from '@/stores/task'
import { assetUrl } from '@/api/client'
import Badge from '@/components/Badge.vue'

const store = useTaskStore()
const visible = ref(true)

const TYPE_LABEL: Record<string, string> = {
  'text-to-image': '文生图',
  edit: '图像编辑',
  outpaint: '扩图',
  upscale: '放大',
  'upscale-folder': '批量放大',
}

function typeLabel(t: string): string {
  return TYPE_LABEL[t] ?? t
}

function statusBadgeType(status: string): 'ok' | 'warn' | 'idle' | 'danger' {
  if (status === 'succeeded') return 'ok'
  if (status === 'running' || status === 'queued') return 'warn'
  if (status === 'failed') return 'danger'
  return 'idle' // cancelled / interrupted
}

const tasks = computed(() =>
  store.order
    .map((id) => store.tasks[id])
    .filter(Boolean)
    .slice(0, 30),
)

function fmtTime(iso?: string | null): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function fmtElapsed(v?: number | null): string {
  if (v == null) return '--'
  return `${v.toFixed(1)}s`
}

async function load() {
  await store.loadHistory(30)
}

onMounted(load)
</script>

<template>
  <section class="history card">
    <div class="head">
      <h3>任务历史</h3>
      <div class="head-actions">
        <span class="count mono">{{ tasks.length }} 条</span>
        <button class="btn btn-secondary btn-sm" @click="load">刷新</button>
        <button class="btn btn-secondary btn-sm" @click="visible = !visible">
          {{ visible ? '收起' : '展开' }}
        </button>
      </div>
    </div>

    <div v-if="!tasks.length" class="empty">暂无任务记录</div>

    <div v-else-if="visible" class="task-list">
      <div v-for="t in tasks" :key="t.id" class="task">
        <div class="task-main">
          <div class="task-line1">
            <Badge :type="statusBadgeType(t.status)">{{ t.status }}</Badge>
            <span class="type">{{ typeLabel(t.type) }}</span>
            <span v-if="t.model" class="model mono">{{ t.model }}</span>
            <span class="time mono">{{ fmtTime(t.created_at) }}</span>
          </div>
          <div v-if="t.prompt" class="task-prompt" :title="t.prompt">{{ t.prompt }}</div>
          <div v-if="t.error" class="task-error" :title="t.error">{{ t.error }}</div>
          <div class="task-line2">
            <span class="meta">耗时 {{ fmtElapsed(t.elapsed_seconds) }}</span>
            <span v-if="t.steps_per_second != null" class="meta">
              {{ t.steps_per_second.toFixed(2) }} steps/s
            </span>
            <span v-if="t.model_load_seconds != null" class="meta">
              加载 {{ t.model_load_seconds.toFixed(1) }}s
            </span>
          </div>
        </div>
        <div v-if="t.outputs && t.outputs.length" class="task-thumbs">
          <a
            v-for="img in t.outputs.slice(0, 3)"
            :key="img"
            :href="assetUrl(img)"
            target="_blank"
            class="thumb"
          >
            <img :src="assetUrl(img)" :alt="img" loading="lazy" />
          </a>
          <span v-if="t.outputs.length > 3" class="more mono">+{{ t.outputs.length - 3 }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.history {
  max-height: 480px;
  overflow-y: auto;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.head h3 {
  margin: 0;
  font-size: 14px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.count {
  font-size: 11px;
  color: var(--text-faint);
}
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
.empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}
.task {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 0;
  border-top: 1px solid var(--border);
}
.task:first-of-type {
  border-top: none;
}
.task-main {
  flex: 1;
  min-width: 0;
}
.task-line1 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.type {
  color: var(--text);
  font-weight: 600;
}
.model {
  font-size: 11px;
  color: var(--text-dim);
}
.time {
  font-size: 11px;
  color: var(--text-faint);
  margin-left: auto;
}
.task-prompt {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-error {
  margin-top: 4px;
  font-size: 11px;
  color: var(--danger, #ef4444);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-line2 {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-faint);
}
.task-thumbs {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}
.thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border);
  display: block;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.more {
  font-size: 11px;
  color: var(--text-faint);
}
</style>
