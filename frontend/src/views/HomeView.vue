<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, assetUrl } from '@/api/client'
import { useReuseStore } from '@/stores/reuse'
import type { GalleryItem, TaskDetail } from '@/types'

const router = useRouter()
const reuse = useReuseStore()

const items = ref<GalleryItem[]>([])
const loading = ref(false)
const activeFilter = ref('all')
const activeModelFilter = ref('all')
const lightboxIndex = ref<number | null>(null)
const renderedCount = ref(10) // 懒加载：当前渲染条数
const gallerySentinel = ref<HTMLElement | null>(null)

const FILTERS = [
  { id: 'all', label: '全部作品' },
  { id: 'landscape', label: '风景' },
  { id: 'portrait', label: '人物' },
  { id: 'animal', label: '动物' },
  { id: 'architecture', label: '建筑' },
  { id: 'food', label: '美食' },
  { id: 'sci-fi', label: '科幻' },
  { id: 'fantasy', label: '奇幻' },
  { id: 'retro', label: '复古' },
  { id: 'minimal', label: '极简' },
  { id: 'cyberpunk', label: '赛博朋克' },
  { id: 'design', label: '设计' },
  { id: 'work', label: '工作' },
  { id: '3d', label: '3D' },
  { id: 'anime', label: '动漫' },
]

const MODEL_FILTERS = [
  { id: 'all', label: '全部模型' },
  { id: 'qwen-image-2.1', label: 'Qwen-Image-2.1' },
  { id: 'ernie-image', label: 'ERNIE-Image Turbo' },
  { id: 'moss-image-sft', label: 'MOSS-Image' },
  { id: 'flux2-klein-4b', label: 'FLUX.2 [klein]' },
  { id: 'z-image-turbo', label: 'Z-Image Turbo' },
  { id: 'sana-sprint-1.6b', label: 'SANA-Sprint' },
  { id: 'lumina-image-2.0', label: 'Lumina-2.0' },
]

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  FILTERS.filter((f) => f.id !== 'all').map((f) => [f.id, f.label]),
)

const filtered = computed(() => {
  let list = items.value
  if (activeFilter.value !== 'all') list = list.filter((it) => it.category === activeFilter.value)
  if (activeModelFilter.value !== 'all') list = list.filter((it) => it.model === activeModelFilter.value)
  return list
})

// 懒加载窗口：初始 10 张，sentinel 进入视口追加 10 张
const visible = computed(() => filtered.value.slice(0, renderedCount.value))

function loadMore() {
  if (renderedCount.value < filtered.value.length) renderedCount.value += 10
}

function resetWindow() {
  renderedCount.value = 10
  nextTick(() => ioObserve())
}

let io: IntersectionObserver | null = null
function ioObserve() {
  if (gallerySentinel.value && !io) {
    io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore()
      },
      { rootMargin: '600px 0px' },
    )
    io.observe(gallerySentinel.value)
  }
}
// columns 瀑布流下 sentinel 位置随图片加载漂移，用 scroll 监听兜底
function onScroll() {
  if (window.scrollY + window.innerHeight >= document.body.scrollHeight - 900) loadMore()
}
watch([activeFilter, activeModelFilter], resetWindow)
watch(visible, () => ioObserve())

const stats = ref({ total: 0, models: 0, gpuName: '' })

function modelFromPath(p?: Record<string, any> | null): string | null {
  if (!p?.model) return null
  const s = String(p.model).split(/[\\/]/).pop() ?? ''
  const m = s.toLowerCase()
  if (m.includes('ernie')) return 'ernie-image'
  if (m.includes('moss')) return 'moss-image-sft'
  if (m.includes('flux')) return 'flux2-klein-4b'
  if (m.includes('z-image')) return 'z-image-turbo'
  if (m.includes('sana')) return 'sana-sprint-1.6b'
  if (m.includes('lumina')) return 'lumina-image-2.0'
  if (m.includes('qwen')) return 'qwen-image-2.1'
  return s || null
}

async function load() {
  loading.value = true
  try {
    const [outData, taskData] = await Promise.allSettled([api.outputs(100, 1), api.tasks(50)])
    const taskMap = new Map<string, TaskDetail>()
    if (taskData.status === 'fulfilled') {
      for (const t of taskData.value.tasks) {
        for (const out of t.outputs ?? []) {
          // 用输出路径中的批次时间戳（stamp）精确匹配，避免同名 output_01.png 误配
          const m = String(out).replace(/\\/g, '/').match(/(\d{8}_\d{6})/)
          if (m) taskMap.set(m[1], t)
        }
      }
    }
    const list: GalleryItem[] = []
    if (outData.status === 'fulfilled') {
      for (const run of outData.value.runs) {
        for (const img of run.images) {
          const task = taskMap.get(run.stamp)
          list.push({
            url: `${assetUrl(`${run.path}/${img}`)}?t=${run.stamp}`,
            prompt: run.prompt,
            stamp: run.stamp,
            created_at: run.created_at,
            model: task?.model ?? modelFromPath(run.params),
            type: task?.type ?? null,
            status: task?.status ?? null,
            params: task?.params ?? run.params ?? null,
            category: run.category ?? null,
          })
        }
      }
    }
    items.value = list
    // 作品总数：优先用后端完整统计（不受 limit=100 截断影响）
    stats.value.total = outData.status === 'fulfilled' && outData.value.total != null ? outData.value.total : list.length
    try {
      const m = await api.models()
      stats.value.models = m.models.length
      stats.value.gpuName = m.gpu.name ?? ''
    } catch {
      /* ignore */
    }
    ensureImages()
  } finally {
    loading.value = false
  }
}

function openLightbox(idx: number) {
  lightboxIndex.value = idx
}

function closeLightbox() {
  lightboxIndex.value = null
}

function stepLightbox(dir: 1 | -1) {
  const n = filtered.value.length
  if (!n) return
  const cur = lightboxIndex.value ?? 0
  lightboxIndex.value = (cur + dir + n) % n
}

function onKeydown(e: KeyboardEvent) {
  if (lightboxIndex.value === null) return
  if (e.key === 'Escape') closeLightbox()
  if (e.key === 'ArrowLeft') stepLightbox(-1)
  if (e.key === 'ArrowRight') stepLightbox(1)
}

function typeLabel(t?: string | null): string {
  const map: Record<string, string> = {
    'text-to-image': '文生图',
    edit: '编辑',
    outpaint: '扩图',
    upscale: '放大',
    'upscale-folder': '批量放大',
    unknown: '',
  }
  return t ? (map[t] ?? t) : ''
}

function scrollToGallery() {
  const el = document.getElementById('gallery')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function dimLabel(p?: Record<string, any> | null): string {
  if (!p) return ''
  const w = p.width
  const h = p.height
  if (w && h) return `${w}×${h}`
  if (p.target_area) return String(p.target_area)
  return ''
}

function stepsLabel(p?: Record<string, any> | null): string {
  if (!p) return ''
  const s = p.num_inference_steps ?? p.steps
  return s ? `${s}步` : ''
}

function doReuse(it: GalleryItem) {
  if (!it.params) return
  reuse.setPending(it.type ?? 'text-to-image', it.params)
  router.push(`/workspace/${it.type ?? 'text-to-image'}`)
}

function retryImg(e: Event, it: GalleryItem) {
  const el = e.target as HTMLImageElement
  const n = parseInt(el.dataset.retry ?? '0', 10) + 1
  if (n > 3) return
  el.dataset.retry = String(n)
  // 加时间戳绕过浏览器损坏缓存强制重拉
  el.src = `${it.url}?r=${Date.now()}-${n}`
}

/** 图片卡在 pending（未触发 error 也未 complete）时强制重拉，兜底 GUI 偶发空白 */
async function ensureImages() {
  for (let round = 0; round < 3; round++) {
    await new Promise((r) => setTimeout(r, 1200))
    let dirty = false
    document.querySelectorAll<HTMLImageElement>('.card-img').forEach((img) => {
      if (!img.complete) {
        const src = img.src
        img.src = src.replace(/[?&]r=\d+-\d+$/, '') + `?r=${Date.now()}-${round}`
        dirty = true
      }
    })
    if (!dirty) break
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('scroll', onScroll)
  io?.disconnect()
  io = null
})
</script>

<template>
  <div class="home">
    <!-- 沉浸式 Hero -->
    <section class="hero">
      <div class="hero-grid" aria-hidden="true" />
      <div class="hero-glow glow-a" aria-hidden="true" />
      <div class="hero-glow glow-b" aria-hidden="true" />
      <div class="hero-inner">
        <h1 class="hero-title">探索无限创意灵感</h1>
        <p class="hero-sub">每一次生成，都是一次灵感与算力的碰撞。</p>
        <div class="hero-stats">
          <div class="stat-chip glass">
            <span class="stat-num mono">{{ stats.total }}</span>
            <span class="stat-label">作品</span>
          </div>
          <div class="stat-chip glass">
            <span class="stat-num mono">{{ stats.models }}</span>
            <span class="stat-label">模型</span>
          </div>
          <div class="stat-chip glass">
            <span class="stat-num mono gpu-name">{{ stats.gpuName || '--' }}</span>
            <span class="stat-label">GPU</span>
          </div>
        </div>
        <div class="hero-actions">
          <button class="cta-btn" @click="router.push('/workspace/text-to-image')">进入工作台 →</button>
          <button class="ghost-btn" @click="scrollToGallery">浏览全部作品</button>
        </div>
      </div>
    </section>

    <!-- 分类条 -->
    <div class="filter-bar">
      <button
        v-for="f in FILTERS"
        :key="f.id"
        class="chip"
        :class="{ active: activeFilter === f.id }"
        @click="activeFilter = f.id"
      >
        {{ f.label }}
      </button>
      <button class="chip chip-refresh" :disabled="loading" @click="load">刷新</button>
    </div>

    <!-- 模型筛选条 -->
    <div class="filter-bar filter-bar-model">
      <button
        v-for="m in MODEL_FILTERS"
        :key="m.id"
        class="chip chip-model"
        :class="{ active: activeModelFilter === m.id }"
        @click="activeModelFilter = m.id"
      >
        {{ m.label }}
      </button>
      <span class="count-hint mono">{{ filtered.length }} 件作品</span>
    </div>

    <!-- 瀑布流画廊 -->
    <section id="gallery" v-if="loading && !items.length" class="masonry">
      <div v-for="i in 9" :key="i" class="card skeleton"></div>
    </section>

    <section v-else-if="!filtered.length" class="empty">
      <p>暂无作品，去工作台生成第一张吧</p>
      <button class="cta-btn" @click="router.push('/workspace/text-to-image')">开始创作</button>
    </section>

        <section v-else class="masonry" id="gallery">
      <div v-for="it in visible" :key="it.url" class="card">
        <div class="card-frame" @click="openLightbox(filtered.indexOf(it))">
          <img class="card-img" :src="it.url" :alt="it.prompt" loading="lazy" decoding="async" @error="retryImg($event, it)" />
        </div>
        <div class="card-info">
          <div class="card-prompt" :title="it.prompt">{{ it.prompt }}</div>
          <div class="card-meta">
            <span v-if="it.category && CATEGORY_LABELS[it.category]" class="meta-cat">{{ CATEGORY_LABELS[it.category] }}</span>
            <span v-if="it.type" class="meta-tag">{{ typeLabel(it.type) }}</span>
            <span v-if="it.model" class="meta-model mono">{{ it.model }}</span>
            <span class="meta-grow"></span>
            <span v-if="dimLabel(it.params)" class="meta-param mono">{{ dimLabel(it.params) }}</span>
            <span v-if="stepsLabel(it.params)" class="meta-param mono">{{ stepsLabel(it.params) }}</span>
            <button
              v-if="it.type === 'text-to-image' && it.params"
              class="reuse-mini"
              title="一键复制参数去生成同款"
              @click.stop="doReuse(it)"
            >
              ✨ 做同款
            </button>
          </div>
        </div>
      </div>
      <div v-if="renderedCount < filtered.length" ref="gallerySentinel" class="sentinel" aria-hidden="true" />
    </section>

    <!-- Lightbox -->
    <Teleport to="body">
      <div v-if="lightboxIndex !== null" class="lightbox" @click.self="closeLightbox">
        <div class="lightbox-inner">
          <img
            v-if="filtered[lightboxIndex]"
            :src="filtered[lightboxIndex].url"
            :alt="filtered[lightboxIndex].prompt"
            class="lightbox-img"
            @error="retryImg($event, filtered[lightboxIndex])"
          />
          <div class="lightbox-meta">
            <div class="lightbox-tags">
              <span v-if="filtered[lightboxIndex]?.type" class="meta-tag">
                {{ typeLabel(filtered[lightboxIndex]?.type) }}
              </span>
              <span v-if="filtered[lightboxIndex]?.model" class="meta-model mono">
                {{ filtered[lightboxIndex]?.model }}
              </span>
              <span class="mono stamp">{{ filtered[lightboxIndex]?.stamp }}</span>
            </div>
            <p class="lightbox-prompt">{{ filtered[lightboxIndex]?.prompt }}</p>
          </div>
          <button class="lb-close" @click="closeLightbox">✕</button>
          <button class="lb-prev" @click.stop="stepLightbox(-1)">‹</button>
          <button class="lb-next" @click.stop="stepLightbox(1)">›</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0;
  align-self: flex-start;
  width: 100%;
  box-sizing: border-box;
}

/* ========== Hero ========== */
.hero {
  position: relative;
  flex-shrink: 0;
  height: 360px;
  padding: 52px 48px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background:
    radial-gradient(ellipse 70% 90% at 18% 8%, rgba(59, 130, 246, 0.3), transparent 62%),
    radial-gradient(ellipse 55% 75% at 85% 92%, rgba(139, 92, 246, 0.26), transparent 60%),
    linear-gradient(160deg, #141b26 0%, #0f1419 100%);
}
/* hero 之后的兄弟元素统一左右留白（hero 本身全宽无圆角） */
.hero ~ * {
  padding: 0 20px;
}
.hero-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse 80% 70% at 50% 20%, #000 30%, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse 80% 70% at 50% 20%, #000 30%, transparent 78%);
}
.hero-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
  pointer-events: none;
}
.glow-a {
  width: 300px;
  height: 300px;
  left: -60px;
  top: -80px;
  background: rgba(59, 130, 246, 0.4);
}
.glow-b {
  width: 260px;
  height: 260px;
  right: 8%;
  bottom: -90px;
  background: rgba(139, 92, 246, 0.42);
}
.hero-inner {
  position: relative;
  z-index: 1;
  max-width: 720px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.hero-title {
  margin: 0 0 14px;
  font-size: 46px;
  font-weight: 800;
  letter-spacing: 0.5px;
  line-height: 1.15;
  color: #fff;
  text-shadow: 0 4px 22px rgba(10, 14, 32, 0.55);
}
.hero-sub {
  margin: 0 0 26px;
  font-size: 15px;
  color: var(--text-dim);
  letter-spacing: 0.3px;
}
.hero-stats {
  display: flex;
  gap: 14px;
  margin-bottom: 28px;
}
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
}
.stat-chip {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 999px;
}
.stat-num {
  font-size: 19px;
  font-weight: 700;
  color: #fff;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stat-label {
  font-size: 12px;
  color: var(--text-faint);
}
.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.cta-btn {
  padding: 11px 24px;
  border: none;
  border-radius: 999px;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
  transition: transform 0.15s, box-shadow 0.15s;
}
.cta-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 26px rgba(99, 102, 241, 0.5);
}
.ghost-btn {
  padding: 11px 22px;
  border-radius: 999px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: var(--text);
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.ghost-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

/* ========== 分类条 ========== */
.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.chip {
  padding: 7px 16px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.chip:hover {
  color: var(--text);
  border-color: rgba(99, 102, 241, 0.4);
  background: var(--card-hover);
}
.chip.active {
  color: #fff;
  background: var(--gradient-brand);
  border-color: transparent;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.35);
}
.chip-refresh {
  margin-left: auto;
}

/* ========== 模型筛选条 ========== */
.filter-bar-model {
  margin-top: -8px;
}
.chip-model {
  font-size: 12px;
  padding: 5px 13px;
  font-family: var(--font-mono, ui-monospace, monospace);
}
.count-hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-faint);
}

/* ========== 画廊（CSS columns 瀑布流） ========== */
.masonry {
  columns: 4;
  column-gap: 8px;
}
.sentinel {
  height: 4px;
  width: 100%;
}
.card {
  break-inside: avoid;
  margin-bottom: 8px;
  padding: 8px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: zoom-in;
  background: transparent;
  transition: transform 0.2s, box-shadow 0.2s;
}
.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(99, 102, 241, 0.15);
}
.card-frame {
  position: relative;
}
.card-img {
  width: 100%;
  height: auto;
  display: block;
  min-height: 220px;
  background: var(--panel);
  border-radius: 10px;
  transition: transform 0.35s ease;
  cursor: zoom-in;
}
.card:hover .card-img {
  transform: scale(1.045);
}
.reuse-mini {
  margin-left: 4px;
  padding: 4px 12px;
  border: none;
  border-radius: 999px;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(99, 102, 241, 0.35);
  transition: transform 0.15s, filter 0.15s;
  flex-shrink: 0;
}
.reuse-mini:hover {
  transform: translateY(-1px);
  filter: brightness(1.12);
}
.card-info {
  padding: 12px 14px 14px;
  background: var(--bg-elev);
  border-top: 1px solid var(--border);
}
.card-prompt {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-dim);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 10px;
  min-height: 38px;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.meta-tag {
  flex-shrink: 0;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: var(--gradient-brand);
}
.meta-model {
  font-size: 11px;
  color: #c7d2fe;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-grow {
  flex: 1;
}
.meta-cat {
  font-size: 11px;
  color: #a5f3fc;
  background: rgba(6, 182, 212, 0.14);
  border: 1px solid rgba(6, 182, 212, 0.35);
  border-radius: 6px;
  padding: 2px 7px;
  white-space: nowrap;
}
.meta-param {
  font-size: 11px;
  color: var(--text-faint);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 7px;
  white-space: nowrap;
}

/* Skeleton */
.skeleton {
  height: 260px;
  background: linear-gradient(110deg, var(--bg-elev) 30%, var(--panel) 50%, var(--bg-elev) 70%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
@keyframes shimmer {
  to {
    background-position-x: -200%;
  }
}

/* Empty */
.empty {
  text-align: center;
  padding: 80px 0;
  color: var(--text-faint);
  font-size: 14px;
}
.empty .cta-btn {
  margin-top: 16px;
}

/* ========== Lightbox ========== */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(4, 6, 12, 0.9);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.lightbox-inner {
  position: relative;
  max-width: min(900px, 92vw);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.lightbox-img {
  max-width: 100%;
  max-height: 74vh;
  object-fit: contain;
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.65);
}
.lightbox-meta {
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.lightbox-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lightbox-tags .stamp {
  color: var(--text-faint);
  font-size: 12px;
  margin-left: auto;
}
.lightbox-prompt {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-dim);
  max-height: 72px;
  overflow-y: auto;
}
.lb-close {
  position: absolute;
  top: -46px;
  right: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid var(--glass-border);
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
}
.lb-prev,
.lb-next {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid var(--glass-border);
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  font-size: 26px;
  cursor: pointer;
  transition: background 0.15s;
}
.lb-prev:hover,
.lb-next:hover,
.lb-close:hover {
  background: rgba(255, 255, 255, 0.16);
}
.lb-prev {
  left: -64px;
}
.lb-next {
  right: -64px;
}
@media (max-width: 1280px) {
  .masonry {
    columns: 3;
  }
}
@media (max-width: 1100px) {
  .lb-prev {
    left: -8px;
  }
  .lb-next {
    right: -8px;
  }
  .masonry {
    columns: 2;
  }
}
@media (max-width: 720px) {
  .masonry {
    columns: 1;
  }
  .hero {
    height: auto;
    padding: 40px 24px;
  }
  .hero-title {
    font-size: 32px;
  }
}
</style>
