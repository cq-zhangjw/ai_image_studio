import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { GpuInfo, LastStats, ModelInfo, StatRecord } from '@/types'

interface ModelState {
  models: ModelInfo[]
  gpu: GpuInfo
  lastStats: LastStats
  stats: StatRecord[]
  loading: boolean
}

export const useModelStore = defineStore('model', {
  state: (): ModelState => ({
    models: [],
    gpu: { available: false },
    lastStats: {},
    stats: [],
    loading: false,
  }),
  actions: {
    async refresh() {
      try {
        this.loading = true
        const data = await api.models()
        this.models = data.models
        this.gpu = data.gpu
        this.lastStats = data.last_stats
      } finally {
        this.loading = false
      }
    },
    async refreshStats(limit = 50) {
      try {
        const data = await api.stats(limit)
        this.stats = data.stats ?? []
      } catch {
        /* 统计接口不可用时静默 */
      }
    },
  },
})
