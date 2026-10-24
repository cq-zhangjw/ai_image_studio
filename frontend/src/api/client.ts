// API 客户端：fetch 封装 + SSE 订阅

import type { ModelsResponse, OutputsResponse, StatsResponse, TaskDetail } from '@/types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export function assetUrl(path: string): string {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `${API_BASE}${path}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = body?.detail?.message ?? body?.detail ?? JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export function getJSON<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function postForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form })
}

// ---- 具体接口 ----

export const api = {
  health: () => getJSON<{ status: string }>('/api/health'),
  models: () => getJSON<ModelsResponse>('/api/models'),
  stats: (limit = 50) => getJSON<StatsResponse>(`/api/models/stats?limit=${limit}`),
  outputs: (limit = 30, pinned?: 0 | 1, category?: string, type?: string) =>
    getJSON<OutputsResponse>(
      `/api/outputs?limit=${limit}${pinned != null ? `&pinned=${pinned}` : ''}${category ? `&category=${category}` : ''}${type ? `&type=${type}` : ''}`,
    ),
  task: (id: string) => getJSON<TaskDetail>(`/api/tasks/${id}`),
  tasks: (limit = 20) => getJSON<{ tasks: TaskDetail[] }>(`/api/tasks?limit=${limit}`),
  submitTextToImage: (body: {
    prompt: string
    negative_prompt?: string
    model?: string
    category?: string
    width: number
    height: number
    num_inference_steps: number
    seed?: number | null
  }) => postJSON<{ task_id: string }>('/api/tasks/text-to-image', body),
  submitEdit: (form: FormData) => postForm<{ task_id: string }>('/api/tasks/edit', form),
  submitOutpaint: (form: FormData) => postForm<{ task_id: string }>('/api/tasks/outpaint', form),
  submitUpscale: (form: FormData) => postForm<{ task_id: string }>('/api/tasks/upscale', form),
  optimizePrompt: (body: { prompt: string; target_model?: string; layout?: boolean }) =>
    postJSON<{
      original: string
      optimized: string
      elapsed_seconds: number
      model: string
      model_load_seconds?: number
      layout?: boolean
    }>('/api/prompt/optimize', body),
  randomPrompt: (body: { category?: string; style?: string; with_text?: boolean; count?: number }) =>
    postJSON<{
      items: { prompt: string; elapsed_seconds: number; category: string; with_text: boolean; model: string }[]
    }>('/api/prompt/random', body),
  pinImage: (stamp: string, image: string) => postJSON<{ ok: boolean }>('/api/gallery/pin', { stamp, image }),
  unpinImage: (stamp: string, image: string) =>
    postJSON<{ ok: boolean }>('/api/gallery/unpin', { stamp, image }),
  setCategory: (stamp: string, category: string) =>
    postJSON<{ ok: boolean }>('/api/gallery/category', { stamp, category }),
  deleteImage: (stamp: string, image: string) =>
    request<{ ok: boolean }>(`/api/gallery/${stamp}/${encodeURIComponent(image)}`, { method: 'DELETE' }),
}

// ---- SSE ----

export type SseHandlers = {
  onProgress?: (d: { step: number; total: number; percent: number; phase: string; status: string }) => void
  onStatus?: (d: {
    status: string
    outputs: string[]
    elapsed_seconds?: number | null
    steps_per_second?: number | null
    model_load_seconds?: number | null
    error?: string | null
  }) => void
  onDone?: (d: { task_id: string }) => void
  onError?: (e: Event) => void
}

export function subscribeTask(taskId: string, handlers: SseHandlers): EventSource {
  const es = new EventSource(`${API_BASE}/api/tasks/${taskId}/events`)
  if (handlers.onProgress) es.addEventListener('progress', (e) => handlers.onProgress!(JSON.parse((e as MessageEvent).data)))
  if (handlers.onStatus) es.addEventListener('status', (e) => handlers.onStatus!(JSON.parse((e as MessageEvent).data)))
  if (handlers.onDone) es.addEventListener('done', (e) => handlers.onDone!(JSON.parse((e as MessageEvent).data)))
  if (handlers.onError) es.onerror = handlers.onError
  return es
}
