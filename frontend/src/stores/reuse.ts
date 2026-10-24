import { defineStore } from 'pinia'

/**
 * 「做同款」回填 store：主页点卡片 → 携带任务参数 → 工作台表单回填。
 */
export const useReuseStore = defineStore('reuse', {
  state: () => ({
    pending: null as null | { type: string; params: Record<string, any> },
  }),
  actions: {
    setPending(type: string, params: Record<string, any>) {
      this.pending = { type, params }
    },
    /** 消费并清空；返回 null 表示无可回填 */
    consume(): { type: string; params: Record<string, any> } | null {
      const p = this.pending
      this.pending = null
      return p
    },
  },
})
