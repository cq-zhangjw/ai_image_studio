// 与后端 schemas.py 对齐的 TS 类型

export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface TaskProgress {
  step: number
  total: number
  percent: number
  phase: string
}

export interface TaskDetail {
  id: string
  type: string
  status: TaskStatus
  progress: TaskProgress
  message: string
  model?: string | null
  prompt?: string | null
  params?: Record<string, any> | null
  outputs: string[]
  elapsed_seconds?: number | null
  steps_per_second?: number | null
  model_load_seconds?: number | null
  error?: string | null
  created_at: string
  finished_at?: string | null
}

export interface StatRecord {
  id: string
  model: string
  elapsed_seconds?: number | null
  steps_per_second?: number | null
  model_load_seconds?: number | null
  created_at: string
  recordType?: string
}

export interface ModelInfo {
  id: string
  name: string
  status: 'ready' | 'loading' | 'loaded'
  loaded: boolean
  load_seconds?: number | null
}

export interface GpuInfo {
  available: boolean
  name?: string | null
  total_mb?: number | null
  used_mb?: number | null
  percent?: number | null
  max_allocated_mb?: number | null
}

export interface LastStats {
  elapsed_seconds?: number | null
  steps_per_second?: number | null
  model_load_seconds?: number | null
}

export interface ModelsResponse {
  models: ModelInfo[]
  gpu: GpuInfo
  last_stats: LastStats
}

export interface StatsResponse {
  stats: StatRecord[]
}

export interface OutputRun {
  stamp: string
  path: string
  images: string[]
  pinned: boolean[]
  prompt: string
  params: Record<string, string> | null
  category: string | null
  created_at: string
  source?: string
  /** 进行中任务的占位引用（HistoryGallery 合并显示时设置） */
  task?: TaskDetail | null
}

export interface OutputsResponse {
  runs: OutputRun[]
  total?: number
}

export type TaskType = 'text-to-image' | 'edit' | 'outpaint' | 'upscale' | 'upscale-folder'

export interface GalleryItem {
  url: string
  prompt: string
  stamp: string
  created_at: string
  model?: string | null
  type?: string | null
  status?: string | null
  params?: Record<string, any> | null
  category?: string | null
}
