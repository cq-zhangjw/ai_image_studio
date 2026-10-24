import { defineStore } from 'pinia'
import { api, subscribeTask } from '@/api/client'
import type { TaskDetail, TaskType } from '@/types'

interface TaskState {
  tasks: Record<string, TaskDetail>
  order: string[]
  lastResult: { taskId: string; outputs: string[] } | null
}

let pollTimer: ReturnType<typeof setInterval> | null = null

export const useTaskStore = defineStore('task', {
  state: (): TaskState => ({
    tasks: {},
    order: [],
    lastResult: null,
  }),
  getters: {
    activeCount(): number {
      return this.order.filter((id) => {
        const t = this.tasks[id]
        return t && (t.status === 'queued' || t.status === 'running')
      }).length
    },
  },
  actions: {
    /** 拉取任务历史（后端已含 moofile 恢复的记录），按创建时间倒序 */
    async loadHistory(limit = 30) {
      try {
        const data = await api.tasks(limit)
        const newIds: string[] = []
        for (const t of data.tasks) {
          const existed = this.tasks[t.id]
          // 保持对象引用：latestTask / SSE 回调持有同一对象，直接合并避免进度"不动"
          if (existed) {
            Object.assign(existed, t)
          } else {
            this.tasks[t.id] = { ...t }
          }
          if (!this.order.includes(t.id)) newIds.push(t.id)
        }
        // 历史（后端倒序）置于 order 头部，保持最新在前；已存在的保持原相对位置
        if (newIds.length) {
          const oldOrder = this.order.filter((id) => !newIds.includes(id))
          this.order = [...newIds, ...oldOrder]
        }
      } catch {
        /* 静默：历史不可用不影响主流程 */
      }
    },
    /**
     * 轮询任务进度（docs/16 §1）：进入页面即启动，刷新后自动恢复进度显示。
     * 与 SSE 双通道并存：SSE 实时 + 轮询兜底（后端每 2s 把进度落库，GET /api/tasks 返回）。
     */
    startPolling(intervalMs = 3000) {
      if (pollTimer) return
      this.loadHistory(40)
      pollTimer = setInterval(() => {
        this.loadHistory(40)
      }, intervalMs)
    },
    stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    },
    upsert(detail: TaskDetail) {
      const existed = this.tasks[detail.id]
      // 保持引用：已有对象直接合并，避免 latestTask 引用失效
      if (existed) {
        Object.assign(existed, detail)
      } else {
        this.tasks[detail.id] = { ...detail }
      }
      if (!this.order.includes(detail.id)) {
        this.order.unshift(detail.id)
      }
    },
    track(taskId: string, type: TaskType) {
      this.upsert({
        id: taskId,
        type,
        status: 'queued',
        progress: { step: 0, total: 1, percent: 0, phase: 'queued' },
        message: '排队中…',
        outputs: [],
        created_at: new Date().toISOString(),
      })
      subscribeTask(taskId, {
        onProgress: (d) => {
          const t = this.tasks[taskId]
          if (!t) return
          t.status = (d.status as TaskDetail['status']) || t.status
          t.progress = { step: d.step, total: d.total, percent: d.percent, phase: d.phase }
          t.message = d.phase
        },
        onStatus: (d) => {
          const t = this.tasks[taskId]
          if (!t) return
          t.status = d.status as TaskDetail['status']
          t.outputs = d.outputs ?? []
          t.elapsed_seconds = d.elapsed_seconds ?? undefined
          t.steps_per_second = d.steps_per_second ?? undefined
          t.model_load_seconds = d.model_load_seconds ?? undefined
          t.error = d.error ?? undefined
          if (d.status === 'succeeded') {
            this.lastResult = { taskId, outputs: d.outputs ?? [] }
          }
        },
        onDone: () => {
          /* 流结束，状态已由 onStatus 更新 */
        },
        onError: () => {
          const t = this.tasks[taskId]
          if (t && t.status === 'queued') t.status = 'failed'
        },
      })
    },
  },
})
