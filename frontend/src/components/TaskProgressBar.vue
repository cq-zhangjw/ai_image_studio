<script setup lang="ts">
import { computed } from 'vue'
import type { TaskDetail } from '@/types'

const props = defineProps<{ task: TaskDetail }>()

const percent = computed(() => props.task.progress.percent ?? 0)

const statusMeta = computed(() => {
  switch (props.task.status) {
    case 'succeeded':
      return { cls: 'badge-ok', label: '完成' }
    case 'failed':
      return { cls: 'badge-danger', label: '失败' }
    case 'cancelled':
      return { cls: 'badge-idle', label: '已取消' }
    case 'running':
      return { cls: 'badge-warn', label: '运行中' }
    default:
      return { cls: 'badge-idle', label: '排队中' }
  }
})

const typeLabel: Record<string, string> = {
  'text-to-image': '文生图',
  edit: '图像编辑',
  outpaint: '图像扩图',
  upscale: '图像放大',
  'upscale-folder': '批量放大',
}
</script>

<template>
  <div class="task-card card">
    <div class="task-head">
      <span class="task-type">{{ typeLabel[task.type] ?? task.type }}</span>
      <span class="badge" :class="statusMeta.cls">{{ statusMeta.label }}</span>
    </div>
    <div class="task-id mono">{{ task.id }}</div>
    <div class="task-phase">{{ task.message || task.progress.phase }}</div>
    <div class="bar-wrap">
      <div class="bar" :style="{ width: percent + '%' }"></div>
    </div>
    <div class="task-meta">
      <span class="mono">{{ task.progress.step }}/{{ task.progress.total }} · {{ percent }}%</span>
      <span v-if="task.elapsed_seconds != null" class="mono">{{ task.elapsed_seconds.toFixed(1) }}s</span>
    </div>
    <div v-if="task.error" class="task-error">{{ task.error }}</div>
    <div v-if="task.outputs.length" class="task-outputs">
      <a
        v-for="(o, i) in task.outputs"
        :key="o"
        :href="o"
        target="_blank"
        class="out-link"
      >结果 {{ i + 1 }}</a>
    </div>
  </div>
</template>

<style scoped>
.task-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.task-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.task-type {
  font-size: 13px;
  font-weight: 600;
}
.task-id {
  font-size: 11px;
  color: var(--text-faint);
}
.task-phase {
  font-size: 12px;
  color: var(--text-dim);
}
.bar-wrap {
  height: 6px;
  border-radius: 3px;
  background: var(--bg-elev);
  overflow: hidden;
}
.bar {
  height: 100%;
  background: var(--primary);
  transition: width 0.4s;
}
.task-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-faint);
}
.task-error {
  font-size: 12px;
  color: var(--danger);
  word-break: break-all;
}
.task-outputs {
  display: flex;
  gap: 8px;
}
.out-link {
  font-size: 12px;
  color: var(--primary);
}
</style>
