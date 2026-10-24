<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, assetUrl } from '@/api/client'
import { downloadImage } from '@/utils/download'
import { useTaskStore } from '@/stores/task'
import type { OutputRun, TaskDetail } from '@/types'

const emit = defineEmits<{
  (e: 'select', payload: { url: string; stamp: string; image: string; prompt: string; pinned: boolean; source?: string; category?: string; params?: Record<string, unknown> | null }): void
  (e: 'goto', payload: { stamp: string; image: string; action: 'upscale' | 'edit' }): void
  (e: 'loaded', runs: OutputRun[]): void
}>()

const props = withDefaults(
  defineProps<{
    type?: string
    title?: string
  }>(),
  { type: '', title: '生成历史' },
)

const runs = ref<OutputRun[]>([])
const loading = ref(false)
const selectedKey = ref('')
const confirmDel = ref<Record<string, boolean>>({})
const busyKey = ref('')

const taskStore = useTaskStore()

// 进行中任务（匹配当前类型）→ 顶部占位卡片；刷新后由 taskStore 轮询恢复
const activeTasks = computed<TaskDetail[]>(() =>
  Object.values(taskStore.tasks)
    .filter(
      (t) =>
        t.type === (props.type || 'text-to-image') &&
        (t.status === 'queued' || t.status === 'running'),
    )
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
)

const isPlaceholder = (run: OutputRun) => run.stamp.startsWith('task:')

function toPlaceholder(t: TaskDetail): OutputRun {
  return {
    stamp: `task:${t.id}`,
    path: '',
    images: [],
    created_at: t.created_at,
    prompt: t.prompt ?? '',
    params: { model: t.model ?? '' },
    pinned: [],
    category: null,
    task: t,
  }
}

// 占位卡片状态文案 / 进度
function phStatusText(run: OutputRun): string {
  const t = run.task
  if (!t) return '处理中'
  if (t.status === 'queued') return '排队中'
  if (t.status === 'running') {
    const p = t.progress?.percent ?? 0
    return p > 0 ? `生成中 ${p}%` : '生成中'
  }
  return '处理中'
}
function phPercent(run: OutputRun): number {
  return run.task?.progress?.percent ?? 0
}
function phMeta(run: OutputRun): string {
  const model = String(run.task?.model ?? '').replace(/^.*[\\/]/, '').slice(0, 26)
  return model ? `${model} · 进行中` : '进行中'
}

const mergedRuns = computed<OutputRun[]>(() => [
  ...activeTasks.value.map(toPlaceholder),
  ...runs.value,
])

// 进行中任务全部进入终态（完成/失败）→ 刷新已完成作品，替换占位
// 立即刷一次 + 延迟 1.5s 兜底（等后端收编落库）
let reloadTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => activeTasks.value.map((t) => t.id).join(','),
  (ids, prev) => {
    if (!prev || ids === prev) return
    load()
    if (reloadTimer) clearTimeout(reloadTimer)
    reloadTimer = setTimeout(() => load(), 1500)
  },
)

async function load() {
  loading.value = true
  try {
    const data = await api.outputs(30, 0, undefined, props.type || undefined)
    runs.value = data.runs
    emit('loaded', runs.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function isPinned(run: OutputRun, i: number): boolean {
  return run.pinned?.[i] ?? false
}

async function togglePin(run: OutputRun, image: string, i: number) {
  const pinned = isPinned(run, i)
  busyKey.value = `${run.stamp}:${image}:pin`
  try {
    if (pinned) await api.unpinImage(run.stamp, image)
    else await api.pinImage(run.stamp, image)
    if (run.pinned) run.pinned[i] = !pinned
  } finally {
    busyKey.value = ''
  }
}

async function remove(run: OutputRun, image: string) {
  const key = `${run.stamp}:${image}`
  if (!confirmDel.value[key]) {
    confirmDel.value[key] = true
    window.setTimeout(() => {
      confirmDel.value[key] = false
    }, 2500)
    return
  }
  busyKey.value = key
  try {
    await api.deleteImage(run.stamp, image)
    const idx = run.images.indexOf(image)
    if (idx >= 0) {
      run.images.splice(idx, 1)
      if (run.pinned) run.pinned.splice(idx, 1)
    }
  } finally {
    busyKey.value = ''
    confirmDel.value[key] = false
  }
}

function select(run: OutputRun, image: string) {
  const idx = run.images.indexOf(image)
  selectedKey.value = `${run.stamp}:${image}`
  emit('select', {
    url: assetUrl(`${run.path}/${image}`),
    stamp: run.stamp,
    image,
    prompt: run.prompt,
    pinned: isPinned(run, idx >= 0 ? idx : 0),
    source: run.source,
    category: run.category ?? '',
    params: (run.params ?? {}) as Record<string, unknown>,
  })
}

// 编辑历史双图缩略：before 原图 URL（source）+ after 结果
function beforeUrl(run: OutputRun): string {
  return run.source ? assetUrl(`${run.path}/${run.source}`) : ''
}

function goto(action: 'upscale' | 'edit', run: OutputRun, image: string) {
  emit('goto', { stamp: run.stamp, image, action })
}

// 父组件历史导航（←/→ 切前后历史）调用：按 stamp 定位并选中该批次的图，触发 select 事件
defineExpose({
  selectRun(stamp: string, image?: string) {
    const run = runs.value.find((r) => r.stamp === stamp)
    if (!run || !run.images.length) return false
    const img = image && run.images.includes(image) ? image : run.images[0]
    select(run, img)
    return true
  },
})

// 日期格式化：YYYY/MM/DD hh:mm:ss
function fmtDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// 耗时格式化：<60s → "12.3s"；≥60s → "1m23s"
function fmtDur(sec: unknown): string {
  const s = Number(sec)
  if (!sec || Number.isNaN(s)) return ''
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
}

// 参数摘要：模型（取路径末段）/ 尺寸（input → output）/ seed
function metaParts(run: OutputRun): string[] {
  const p = (run.params ?? {}) as Record<string, unknown>
  const parts: string[] = []
  const model = String(p.model ?? '')
  if (model) parts.push(model.replace(/^.*[\\/]/, '').slice(0, 26))
  if (p.input_size && p.output_size) parts.push(`${p.input_size} → ${p.output_size}`)
  else if (p.output_size) parts.push(String(p.output_size))
  else if (p.height && p.width) parts.push(`${p.width}x${p.height}`)
  if (p.seed != null && String(p.seed) !== '') parts.push(`seed ${p.seed}`)
  return parts
}

// 引擎单独一行（放大任务）：Real-ESRGAN + 倍数
function engineParts(run: OutputRun): string[] {
  const p = (run.params ?? {}) as Record<string, unknown>
  const parts: string[] = []
  if (p.engine) parts.push(p.engine === 'realesrgan' ? 'Real-ESRGAN' : String(p.engine))
  if (p.scale) parts.push(`${p.scale}x`)
  return parts
}

async function onDownload(run: OutputRun, image: string) {
  await downloadImage(assetUrl(`${run.path}/${image}`), `${run.stamp}_${image}`)
}

// caption 提取：prompt 可能是 JSON（{"summary":{"caption":"..."}}），取 caption 展示
function captionText(prompt: string): string {
  if (!prompt) return ''
  const s = prompt.trim()
  if (s.startsWith('{')) {
    try {
      const j = JSON.parse(s)
      const c = j?.summary?.caption ?? j?.caption
      if (typeof c === 'string') return c
      return s
    } catch {
      return s
    }
  }
  return s
}
</script>

<template>
  <div class="history-gallery">
    <div class="hg-head">
      <span class="hg-title">{{ title }}</span>
      <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="!mergedRuns.length" class="hg-empty">暂无历史产物</div>

    <div v-else class="hg-list">
      <div v-for="run in mergedRuns" :key="run.stamp" class="hg-run">
        <!-- 进行中任务占位卡片 -->
        <div v-if="isPlaceholder(run)" class="hg-item hg-item-live">
          <div class="hg-thumb">
            <div class="hg-thumb-ph">
              <div class="ph-status">{{ phStatusText(run) }}</div>
              <div class="ph-bar">
                <div class="ph-bar-fill" :style="{ width: `${phPercent(run)}%` }"></div>
              </div>
            </div>
          </div>
          <div class="hg-info">
            <div class="hg-info-top">
              <span class="hg-date">{{ fmtDate(run.created_at) }}</span>
            </div>
            <div class="hg-meta">
              <span class="hg-meta-parts">{{ phMeta(run) }}</span>
              <span class="hg-dur">-</span>
            </div>
            <div v-if="captionText(run.prompt)" class="hg-caption" :title="captionText(run.prompt)">{{ captionText(run.prompt) }}</div>
            <div class="hg-ops">
              <span class="hg-live-badge">● {{ phStatusText(run) }}</span>
            </div>
          </div>
        </div>
        <!-- 已完成批次：每张图一行 -->
        <div
          v-for="(img, i) in run.images"
          :key="img"
          class="hg-item"
          :class="{ selected: selectedKey === `${run.stamp}:${img}` }"
          @click="select(run, img)"
        >
          <!-- 左：缩略图（编辑/放大历史含原图副本时双图并列：原图 | 结果） -->
          <div class="hg-thumb" :class="{ dual: !!beforeUrl(run) }">
            <template v-if="beforeUrl(run)">
              <img :src="beforeUrl(run)" :alt="`原图 ${img}`" loading="lazy" decoding="async" />
              <span class="hg-thumb-sep"></span>
              <img
                :src="`${assetUrl(`${run.path}/${img}`)}?t=${run.stamp}`"
                :alt="img"
                loading="lazy"
                decoding="async"
              />
            </template>
            <img
              v-else
              :src="`${assetUrl(`${run.path}/${img}`)}?t=${run.stamp}`"
              :alt="img"
              loading="lazy"
              decoding="async"
            />
          </div>
          <!-- 右：信息区（撑满剩余宽度） -->
          <div class="hg-info">
            <div class="hg-info-top">
              <span class="hg-date">{{ fmtDate(run.created_at) }}</span>
            </div>
            <div class="hg-meta">
              <span class="hg-meta-parts">{{ metaParts(run).join(' · ') }}</span>
              <span v-if="fmtDur(run.params?.elapsed_seconds)" class="hg-dur">⏱ {{ fmtDur(run.params?.elapsed_seconds) }}</span>
            </div>
            <div v-if="engineParts(run).length" class="hg-engine">
              <span class="hg-engine-badge">{{ engineParts(run).join(' · ') }}</span>
            </div>
            <div v-if="captionText(run.prompt)" class="hg-caption" :title="captionText(run.prompt)">{{ captionText(run.prompt) }}</div>
            <div class="hg-ops" @click.stop>
              <button
                class="hg-op"
                :class="{ on: isPinned(run, i) }"
                :disabled="busyKey === `${run.stamp}:${img}:pin`"
                :title="isPinned(run, i) ? '取消主页展示' : '加入主页展示'"
                @click="togglePin(run, img, i)"
              >
                {{ isPinned(run, i) ? '★' : '☆' }}
              </button>
              <button class="hg-op" title="去放大" @click="goto('upscale', run, img)">🔍</button>
              <button class="hg-op" title="去编辑" @click="goto('edit', run, img)">✂</button>
              <button class="hg-op" title="下载" @click="onDownload(run, img)">⬇</button>
              <button
                class="hg-op hg-del"
                :class="{ confirm: confirmDel[`${run.stamp}:${img}`] }"
                :title="confirmDel[`${run.stamp}:${img}`] ? '再次点击确认删除' : '删除图片'"
                @click="remove(run, img)"
              >
                {{ confirmDel[`${run.stamp}:${img}`] ? '确认?' : '🗑' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-gallery {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.hg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.hg-title {
  font-size: 14px;
  font-weight: 600;
}
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
.hg-empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}
.hg-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.hg-run {
  padding: 6px 0;
  border-top: 1px solid var(--border);
}
.hg-item {
  display: flex;
  gap: 12px;
  height: 128px;
  padding: 8px 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
  align-items: stretch;
  overflow: hidden;
  box-sizing: border-box;
}
.hg-item:hover {
  background: rgba(255, 255, 255, 0.04);
}
.hg-item.selected {
  background: var(--primary-soft);
}
.hg-thumb {
  width: 88px;
  flex-shrink: 0;
  align-self: stretch;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--bg-elev);
}
.hg-thumb.dual {
  display: flex;
}
.hg-thumb.dual img {
  flex: 1;
  width: auto;
  min-width: 0;
}
.hg-thumb-sep {
  width: 2px;
  flex-shrink: 0;
  background: var(--border-strong);
}
.hg-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hg-item-live {
  opacity: 1;
}
.hg-item-live .hg-thumb {
  border: none;
  background: transparent;
}
.hg-thumb-ph {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(160deg, rgba(59, 130, 246, 0.08), rgba(139, 92, 246, 0.1));
  border: 1px dashed var(--border-strong);
  border-radius: 8px;
  box-sizing: border-box;
}
.hg-thumb-ph .ph-status {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
  white-space: nowrap;
}
.hg-thumb-ph .ph-bar {
  width: 70%;
  height: 4px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.15);
  overflow: hidden;
}
.hg-thumb-ph .ph-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: var(--primary);
  transition: width 0.6s ease;
}
.hg-live-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: #d97706;
  font-size: 11.5px;
  font-weight: 600;
}
.hg-live-badge::first-letter {
  color: inherit;
}
.hg-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  justify-content: space-between;
}
.hg-info-top {
  display: flex;
  justify-content: flex-start;
  align-items: baseline;
  font-size: 12px;
  color: var(--text-dim);
}
.hg-stamp {
  font-size: 11px;
}
.hg-date {
  font-size: 11px;
  color: var(--text-faint);
}
.hg-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-dim);
  overflow: hidden;
}
.hg-meta-parts {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hg-dur {
  flex-shrink: 0;
  color: var(--primary);
  font-weight: 600;
}
.hg-engine {
  display: flex;
  align-items: center;
  gap: 6px;
}
.hg-engine-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  background: rgba(64, 169, 124, 0.12);
  border: 1px solid rgba(64, 169, 124, 0.35);
  color: #1F7A4D;
  font-weight: 600;
  line-height: 1.5;
}
.hg-caption {
  font-size: 11.5px;
  color: var(--text-faint);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.45;
}
.hg-ops {
  display: flex;
  gap: 6px;
  margin-top: auto;
  padding-top: 2px;
}
.hg-op {
  height: 24px;
  min-width: 24px;
  padding: 0 7px;
  border-radius: 7px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, border-color 0.15s, transform 0.1s;
}
.hg-op:hover {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  transform: scale(1.05);
}
.hg-op.on {
  color: #f59e0b;
  border-color: rgba(245, 158, 11, 0.5);
}
.hg-op:disabled {
  opacity: 0.5;
  cursor: default;
}
.hg-op.hg-del {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.4);
}
.hg-op.hg-del:hover {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
.hg-op.hg-del.confirm {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
</style>
