<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, assetUrl } from '@/api/client'
import { downloadImage } from '@/utils/download'
import { useTaskStore } from '@/stores/task'
import { useReuseStore } from '@/stores/reuse'
import ParamNumberField from '@/components/ParamNumberField.vue'
import RatioSelector from '@/components/RatioSelector.vue'
import HistoryGallery from '@/components/HistoryGallery.vue'
import ModelSelector from '@/components/ModelSelector.vue'
import PromptOptimizerModal from '@/components/PromptOptimizerModal.vue'
import PromptTagModal from '@/components/PromptTagModal.vue'
import FieldGroup from '@/components/FieldGroup.vue'
import Badge from '@/components/Badge.vue'
import { generateRandomPrompt } from '@/utils/randomPrompt'
import type { OutputRun } from '@/types'

const store = useTaskStore()
const router = useRouter()
const reuse = useReuseStore()

const prompt = ref('夏日冰饮节海报：夏日冰饮节主标题、冰爽一夏副标题、冰饮与水果元素、渐变蓝橙背景、商业促销设计')
const negative = ref('blurry, low quality, watermark, text artifacts')
const highDensity = ref(false)
// 布局 JSON 提示词仅 MOSS 支持：非 moss 模型时隐藏复选框且不传 layout
const isMoss = computed(() => model.value === 'moss-image-sft')
const model = ref('qwen-image-2.1')
const category = ref('landscape')
const ratio = ref('16:9')
const steps = ref(20)
const showSampling = ref(false) // 采样参数折叠（默认折叠，普通用户不关心）
const seed = ref(0) // 0 = 随机
const busy = ref(false)
const error = ref('')
const tagOpen = ref(false)
const randomLoading = ref(false)

// 内容分类（与后端白名单一致，docs/14 §2，docs/20 新增 设计/工作/3D/动漫）
const CATEGORIES = [
  { value: 'landscape', label: '风景' },
  { value: 'portrait', label: '人物' },
  { value: 'animal', label: '动物' },
  { value: 'architecture', label: '建筑' },
  { value: 'food', label: '美食' },
  { value: 'sci-fi', label: '科幻' },
  { value: 'fantasy', label: '奇幻' },
  { value: 'retro', label: '复古' },
  { value: 'minimal', label: '极简' },
  { value: 'cyberpunk', label: '赛博朋克' },
  { value: 'design', label: '设计' },
  { value: 'work', label: '工作' },
  { value: '3d', label: '3D' },
  { value: 'anime', label: '动漫' },
]

/** 🎲 AI 随机提示词：走 qwen LLM 生成（分类感知），失败兜底本地随机 */
async function handleRandom() {
  randomLoading.value = true
  try {
    const res = await api.randomPrompt({ category: category.value, with_text: false, count: 1 })
    const item = res.items?.[0]
    if (item?.prompt) {
      prompt.value = item.prompt
      return
    }
    throw new Error('empty')
  } catch {
    const r = generateRandomPrompt()
    prompt.value = model.value === 'qwen-image-2.1' || model.value === 'ernie-image' || model.value === 'moss-image-sft' || model.value === 'lumina-image-2.0' ? r.prompt : r.en
  } finally {
    randomLoading.value = false
  }
}

// 各模型推荐默认步数
const MODEL_STEP_DEFAULT: Record<string, number> = {
  'qwen-image-2.1': 20,
  'ernie-image': 20,
  'moss-image-sft': 30,
  'flux2-klein-9b': 4,
  'z-image-turbo': 8,
  'sana-sprint-1.6b': 2,
  'lumina-image-2.0': 40,
}
// 切换模型时同步步数默认值
watch(model, (m) => {
  steps.value = MODEL_STEP_DEFAULT[m] ?? steps.value
})

const RATIOS = [
  { value: '1:1', label: '1:1' },
  { value: '2:3', label: '2:3' },
  { value: '3:4', label: '3:4' },
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
  { value: 'custom', label: '自定义' },
]

const DIMS: Record<string, [number, number]> = {
  '1:1': [1024, 1024],
  '2:3': [1024, 1536],
  '3:4': [896, 1216],
  '16:9': [1536, 864],
  '9:16': [864, 1536],
}

// 自定义画布宽高（32 的倍数，单边建议 ≤2048）
const customW = ref(DIMS['16:9'][0])
const customH = ref(DIMS['16:9'][1])
const dimHint = ref('')

// 点击比例 chip → 输入框同步该比例真实分辨率
watch(ratio, (r) => {
  if (r !== 'custom' && DIMS[r]) {
    const [w, h] = DIMS[r]
    customW.value = w
    customH.value = h
    dimHint.value = ''
  }
})

// 手动修改任意输入框 → 自动切为自定义模式
function onCustomInput() {
  if (ratio.value !== 'custom') ratio.value = 'custom'
}

// 光标移出：非 32 倍数 → 自动修正为最近倍数并提示；>2048 → 钳制为 2048
function normalizeDim(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return v
  let n = Math.round(v)
  if (n > 2048) n = 2048
  const r = n % 32
  if (r !== 0) {
    const down = n - r
    const up = n + (32 - r)
    n = n - down <= up - n ? down : up
  }
  return n
}
let dimHintTimer: ReturnType<typeof setTimeout> | null = null
function onBlurDim(which: 'w' | 'h') {
  const cur = which === 'w' ? customW.value : customH.value
  if (!cur || cur <= 0) return
  const raw = Math.round(cur)
  const fixed = normalizeDim(raw)
  const dimName = which === 'w' ? '宽度' : '高度'
  if (fixed !== raw) {
    if (which === 'w') customW.value = fixed
    else customH.value = fixed
    dimHint.value = `${dimName} ${raw} 不符合规范，已自动修正为 ${fixed}${raw > 2048 ? '（≤2048）' : '（32 的倍数）'}`
  }
  if (dimHintTimer) clearTimeout(dimHintTimer)
  dimHintTimer = setTimeout(() => {
    dimHint.value = ''
  }, 4000)
}

const MODEL_IDS = ['qwen-image-2.1', 'ernie-image', 'moss-image-sft', 'flux2-klein-9b', 'z-image-turbo', 'sana-sprint-1.6b', 'lumina-image-2.0']

const latestTask = ref<any>(null)

// ---- 大图预览（上半）----
// 支持多图：urls/stamps/names 平行数组 + index 切换
interface PreviewState {
  urls: string[]
  stamps: string[]
  names: string[]
  index: number
  prompt: string
  pinned: boolean
  /** 生成元信息（模型 / 尺寸等），自动预览时从任务参数取 */
  meta?: string[]
  /** 分类（自动预览时从任务参数取） */
  category?: string
}
const preview = ref<PreviewState | null>(null)

// 结果预览图真实像素尺寸（加载后左上角角标）
const previewSize = ref('')
function onPreviewLoad(e: Event) {
  const el = e.target as HTMLImageElement
  if (el.naturalWidth) previewSize.value = `${el.naturalWidth}×${el.naturalHeight}`
}

const previewUrl = computed(() => {
  if (preview.value?.urls?.length) return preview.value.urls[preview.value.index] ?? preview.value.urls[0]
  if (store.lastResult?.outputs?.length) return assetUrl(store.lastResult.outputs[0])
  return ''
})

// ---- 历史记录快速导航：←/→ 切换前后历史并回填参数 ----
const historyRuns = ref<OutputRun[]>([])
const historyRef = ref<InstanceType<typeof HistoryGallery> | null>(null)
const hasHistory = computed(() => historyRuns.value.some((r) => r.images.length))

// 当前预览在历史列表中的位置（用于计数徽标）
const curHistIndex = computed(() => {
  const p = preview.value
  if (!p) return -1
  const stamp = p.stamps?.[p.index]
  if (!stamp) return -1
  return historyRuns.value.findIndex((r) => r.stamp === stamp)
})

function onHistoryLoaded(runs: OutputRun[]) {
  historyRuns.value = runs
  // 默认展示最近一条历史（仅当当前没有任何预览时，避免覆盖本次会话生成结果）
  if (!preview.value && !store.lastResult?.outputs?.length) {
    const first = runs.find((r) => r.images.length)
    if (first) historyRef.value?.selectRun(first.stamp)
  }
}

// dir: -1 = 上一条（更新），1 = 下一条（更旧），循环
function navHistory(dir: -1 | 1) {
  const p = preview.value
  if (!p) return
  viewingHistory.value = true
  // 定位当前选中：优先当前预览批次；无则回退最近一次历史（列表头部）
  let cur = curHistIndex.value
  if (cur < 0) cur = 0
  const n = historyRuns.value.filter((r) => r.images.length).length
  if (!n) return
  const target = (cur + dir + n) % n
  const targetRun = historyRuns.value.filter((r) => r.images.length)[target]
  if (historyRef.value?.selectRun(targetRun.stamp)) {
    // 回填由 select 事件 → onHistorySelect 完成
  }
}

// 键盘 ←/→ 切换历史；输入框/文本域内不响应，避免干扰打字
function onPreviewKeydown(e: KeyboardEvent) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  if (!preview.value) return
  e.preventDefault()
  navHistory(e.key === 'ArrowLeft' ? -1 : 1)
}

// 预览区：手动收录/取消收录主页（★）
const pinBusy = ref(false)
async function togglePreviewPin() {
  const p = preview.value
  if (!p || pinBusy.value) return
  const stamp = p.stamps?.[p.index]
  const img = p.names?.[p.index]
  if (!stamp || !img) return
  pinBusy.value = true
  try {
    if (p.pinned) await api.unpinImage(stamp, img)
    else await api.pinImage(stamp, img)
    p.pinned = !p.pinned
  } finally {
    pinBusy.value = false
  }
}

// 生成成功 → 自动展示最新结果（含多图）；用户浏览历史时不打断
const viewingHistory = ref(false)
watch(
  () => store.lastResult,
  (r) => {
    if (r?.outputs?.length && !viewingHistory.value) {
      const outs = r.outputs.map(String)
      const stamps = outs.map((o) => String(o).match(/(\d{8}_\d{6})/)?.[1] ?? '')
      const names = outs.map((o) => o.split('/').pop() ?? '')
      // 元信息：模型 / 尺寸（来自任务参数）
      const t = store.tasks[r.taskId]
      const meta: string[] = []
      if (t?.model) meta.push(String(t.model).replace(/^.*[\\/]/, '').slice(0, 26))
      const tp = (t?.params ?? {}) as Record<string, unknown>
      if (tp.width && tp.height) meta.push(`${tp.width}×${tp.height}`)
      else if (tp.output_size) meta.push(String(tp.output_size))
      preview.value = {
        urls: outs.map(assetUrl),
        stamps,
        names,
        index: 0,
        prompt: '',
        pinned: false, // 新生成默认不收录主页
        meta,
        category: String(tp.category ?? ''),
      }
    }
  },
)

// 预览区元信息：历史记录从 runs 匹配（模型/尺寸），否则用 preview.meta
const previewMeta = computed<string[]>(() => {
  const p = preview.value
  if (!p) return []
  const stamp = p.stamps?.[p.index]
  const run = historyRuns.value.find((r) => r.stamp === stamp)
  if (run) {
    const parts: string[] = []
    const rp = (run.params ?? {}) as Record<string, unknown>
    const m = String(rp.model ?? '').replace(/^.*[\\/]/, '').slice(0, 26)
    if (m) parts.push(m)
    if (rp.output_size) parts.push(String(rp.output_size))
    else if (rp.input_size && rp.output_size) parts.push(`${rp.input_size} → ${rp.output_size}`)
    else if (rp.width && rp.height) parts.push(`${rp.width}×${rp.height}`)
    return parts
  }
  return p.meta ?? []
})

// 批次号 → YYYY/MM/DD hh:mm:ss（stamp 即本地生成时刻，直接格式化避免时区偏差）
function fmtStampDate(stamp: string | undefined): string {
  if (!stamp) return ''
  const m = stamp.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/)
  if (!m) return stamp
  return `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}:${m[6]}`
}

// ---- 预览区分类：显示 + 下拉选择更新 ----
const catOpen = ref(false)
const curCategory = computed(() => {
  const p = preview.value
  if (!p) return ''
  const stamp = p.stamps?.[p.index]
  const run = historyRuns.value.find((r) => r.stamp === stamp)
  if (run?.category) return run.category
  return p.category ?? ''
})
const curCategoryLabel = computed(() => {
  const c = curCategory.value
  return (CATEGORIES.find((x) => x.value === c)?.label ?? c) || '未分类'
})
function onCatDocClick() {
  catOpen.value = false
}
async function setPreviewCategory(cat: string) {
  catOpen.value = false
  const p = preview.value
  if (!p) return
  const stamp = p.stamps?.[p.index]
  if (!stamp) return
  try {
    await api.setCategory(stamp, cat)
    p.category = cat
    const run = historyRuns.value.find((r) => r.stamp === stamp)
    if (run) run.category = cat
  } catch {
    /* 静默：更新失败保持原值 */
  }
}

// ---- 参数回填（主页做同款 / 历史点击共用） ----
function fillParams(q: Record<string, any>) {
  if (q.prompt) prompt.value = String(q.prompt)
  if (q.negative_prompt) negative.value = String(q.negative_prompt)
  if (q.model && MODEL_IDS.includes(q.model)) model.value = q.model
  if (q.width && q.height) {
    const found = Object.entries(DIMS).find(([, [w, h]]) => w === Number(q.width) && h === Number(q.height))
    if (found) {
      ratio.value = found[0]
    } else {
      ratio.value = 'custom'
      customW.value = Number(q.width)
      customH.value = Number(q.height)
    }
  }
  if (q.num_inference_steps) steps.value = Number(q.num_inference_steps)
  if (q.seed) seed.value = Number(q.seed)
}

function applyReuse() {
  const p = reuse.consume()
  if (!p || p.type !== 'text-to-image') return
  fillParams(p.params)
}

onMounted(() => {
  applyReuse()
  window.addEventListener('keydown', onPreviewKeydown)
  document.addEventListener('click', onCatDocClick)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onPreviewKeydown)
  document.removeEventListener('click', onCatDocClick)
})

// 历史缩略图点击：上大图 + 按批次匹配任务参数回填
async function onHistorySelect(p: { url: string; stamp: string; image: string; prompt: string; pinned: boolean }) {
  viewingHistory.value = true
  preview.value = {
    urls: [p.url],
    stamps: [p.stamp],
    names: [p.image],
    index: 0,
    prompt: p.prompt,
    pinned: p.pinned,
  }
  try {
    const data = await api.tasks(50)
    const t = data.tasks.find((x) => x.outputs?.some((o) => String(o).includes(p.stamp)))
    if (t?.params) fillParams(t.params)
    else if (p.prompt) prompt.value = p.prompt
  } catch {
    if (p.prompt) prompt.value = p.prompt
  }
}

// 历史图片 → 去放大 / 去编辑（跳转并自动带入该图）
function onHistoryGoto(p: { stamp: string; image: string; action: 'upscale' | 'edit' }) {
  router.push({ path: `/workspace/${p.action}`, query: { src: p.stamp, img: p.image } })
}

async function generate() {
  if (!prompt.value.trim()) {
    error.value = '请输入生成描述'
    return
  }
  let w: number
  let h: number
  if (ratio.value === 'custom') {
    w = Math.round(customW.value || 0)
    h = Math.round(customH.value || 0)
    if (!w || !h) {
      error.value = '请输入自定义宽度和高度'
      return
    }
    if (w % 32 !== 0 || h % 32 !== 0) {
      error.value = '自定义宽高必须是 32 的倍数'
      return
    }
    if (w > 2048 || h > 2048) {
      error.value = '单边最大建议不超过 2048，超清大图请生成后使用放大功能'
      return
    }
  } else {
    ;[w, h] = DIMS[ratio.value]
  }
  error.value = ''
  busy.value = true
  try {
    const res = await api.submitTextToImage({
      prompt: prompt.value,
      negative_prompt: negative.value || undefined,
      model: model.value,
      category: category.value,
      width: w,
      height: h,
      num_inference_steps: steps.value,
      seed: seed.value || null,
    })
    store.track(res.task_id, 'text-to-image')
    latestTask.value = store.tasks[res.task_id]
    // 回到"最新结果"态：完成后自动回传展示；退出历史浏览
    viewingHistory.value = false
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="workspace">
    <section class="panel card">
      <h2 class="panel-title">
        文生图
        <Badge type="brand" :dot="false">5 模型</Badge>
      </h2>

      <FieldGroup title="模型选择">
        <ModelSelector v-model="model" model-id="qwen-image-2.1" />
      </FieldGroup>

      <FieldGroup title="提示词">
        <div class="prompt-head">
          <label>生成描述</label>
          <div class="prompt-actions">
            <button class="icon-btn" title="热门标签灵感（分类选标签，AI 组合成提示词）" @click="tagOpen = true">🏷</button>
            <button class="icon-btn" :disabled="randomLoading" :title="randomLoading ? 'AI 生成中…' : 'AI 随机生成一条创意提示词'" @click="handleRandom">
              <span v-if="randomLoading" class="spinner-mini" />
              <span v-else>🎲</span>
            </button>
            <PromptOptimizerModal v-model="prompt" :model-id="model" :layout="isMoss && highDensity" @apply="(t: string) => (prompt = t)" />
          </div>
        </div>
        <textarea v-model="prompt" rows="4" placeholder="描述你想生成的画面与文字…"></textarea>

        <label v-if="isMoss" class="dense-row">
          <input v-model="highDensity" type="checkbox" />
          <span>高密度文字（AI 优化返回布局 JSON，适用于多模块文字海报）</span>
        </label>

        <label>负面提示词</label>
        <input v-model="negative" placeholder="不想要的内容（可选）" />
      </FieldGroup>

      <FieldGroup title="作品分类（用于主页筛选）">
        <div class="cat-btns">
          <button
            v-for="c in CATEGORIES"
            :key="c.value"
            class="cat-btn"
            :class="{ on: category === c.value }"
            @click="category = c.value"
          >
            {{ c.label }}
          </button>
        </div>
      </FieldGroup>

      <PromptTagModal v-model="tagOpen" :model-id="model" @apply="(t: string) => (prompt = t)" />

      <FieldGroup title="画布比例（宽高比）">
        <RatioSelector v-model="ratio" :options="RATIOS" />
        <div class="custom-ratio">
          <input
            v-model.number="customW"
            type="number"
            class="cr-input"
            min="32"
            step="32"
            placeholder="宽度"
            @input="onCustomInput"
            @blur="onBlurDim('w')"
          />
          <span class="cr-x">×</span>
          <input
            v-model.number="customH"
            type="number"
            class="cr-input"
            min="32"
            step="32"
            placeholder="高度"
            @input="onCustomInput"
            @blur="onBlurDim('h')"
          />
          <span class="tip-wrap">
            <span class="tip-q">?</span>
            <span class="tip-box">宽高必须是 32 的倍数；单边最大建议不超过 2048，超清大图可生成后使用放大功能</span>
          </span>
        </div>
        <div v-if="dimHint" class="dim-hint">{{ dimHint }}</div>
      </FieldGroup>

      <div class="sampling-group">
        <button class="sampling-toggle" type="button" @click="showSampling = !showSampling">
          <span>采样参数</span>
          <span class="sampling-chev" :class="{ open: showSampling }">▾</span>
        </button>
        <div v-show="showSampling" class="sampling-body">
          <div class="fields-grid">
            <ParamNumberField v-model="steps" :min="10" :max="40" label="采样步数" />
            <ParamNumberField v-model="seed" :min="0" :max="999999999" label="种子（留空=随机）" />
          </div>
        </div>
      </div>

      <div class="execute">
        <div v-if="error" class="error">{{ error }}</div>
        <button class="btn generate" :disabled="busy" @click="generate">
          {{ busy ? '提交中…' : '开始生成' }}
        </button>
        <div v-if="store.activeCount > 0" class="queue-hint">有 {{ store.activeCount }} 个任务在排队执行，可继续提交（单 worker 串行）</div>
      </div>
    </section>

    <section class="panel card result-panel">
      <h2 class="panel-title">
        结果
        <Badge v-if="latestTask && latestTask.status === 'succeeded'" type="ok">成功</Badge>
        <Badge v-else-if="latestTask && (latestTask.status === 'running' || latestTask.status === 'queued')" type="warn">进行中</Badge>
        <Badge v-else type="idle">空闲</Badge>
      </h2>

      <div class="result-split">
        <!-- 上半：大图预览（简单图片展示：处理完自动更新 / 点击历史图预览） -->
        <div class="preview-area">
          <template v-if="previewUrl">
            <div class="preview-img-wrap">
              <img
                :src="previewUrl"
                :alt="preview?.prompt ?? ''"
                class="preview-img"
                decoding="async"
                @load="onPreviewLoad"
              />
              <span v-if="previewSize" class="size-badge">{{ previewSize }}</span>
              <button class="dl-btn" title="下载图片" @click.stop="downloadImage(previewUrl, `gen_${preview?.stamps?.[preview.index] || Date.now()}.png`)">⬇</button>
              <button
                v-if="hasHistory"
                class="nav-btn nav-prev"
                title="上一条历史（←）"
                @click.stop="navHistory(-1)"
              >‹</button>
              <button
                v-if="hasHistory"
                class="nav-btn nav-next"
                title="下一条历史（→）"
                @click.stop="navHistory(1)"
              >›</button>
            </div>
            <div class="preview-meta">
              <span v-if="curHistIndex >= 0" class="preview-count mono">{{ curHistIndex + 1 }}/{{ historyRuns.length }}</span>
              <span class="mono preview-stamp">{{ fmtStampDate(preview?.stamps?.[preview?.index ?? 0]) }}</span>
              <span v-if="previewMeta.length" class="preview-meta-parts">{{ previewMeta.join(' · ') }}</span>
              <span class="cat-select-wrap" @click.stop>
                <button class="cat-select" type="button" @click.stop="catOpen = !catOpen">
                  {{ curCategoryLabel }}
                  <span class="cat-caret" :class="{ up: catOpen }">▾</span>
                </button>
                <div v-if="catOpen" class="cat-menu">
                  <button
                    v-for="c in CATEGORIES"
                    :key="c.value"
                    type="button"
                    class="cat-menu-item"
                    :class="{ on: c.value === curCategory }"
                    @click.stop="setPreviewCategory(c.value)"
                  >
                    {{ c.label }}
                  </button>
                </div>
              </span>
              <button
                v-if="preview"
                class="pin-toggle"
                :class="{ on: preview.pinned }"
                :disabled="pinBusy"
                :title="preview.pinned ? '取消主页展示' : '加入主页展示（质量合格后手动收录）'"
                @click.stop="togglePreviewPin"
              >
                {{ preview.pinned ? '★ 已在主页' : '☆ 加入主页' }}
              </button>
            </div>
            <p v-if="preview?.prompt || prompt" class="preview-prompt" :title="preview?.prompt || prompt">
              {{ preview?.prompt || prompt }}
            </p>
          </template>
          <template v-else-if="latestTask && (latestTask.status === 'running' || latestTask.status === 'queued')">
            <div v-if="latestTask.progress?.preview_url" class="preview-live">
              <img :src="latestTask.progress.preview_url" alt="生成中预览" />
              <div class="preview-live-meta">
                <span class="live-dot"></span>
                <span>采样 {{ latestTask.progress.step }}/{{ latestTask.progress.total }} · {{ latestTask.progress.percent }}%</span>
              </div>
            </div>
            <div v-else class="preview-placeholder">
              {{ latestTask.status === 'queued' ? '排队中，请稍候…' : '生成中，完成后自动回传展示…' }}
            </div>
          </template>
          <div v-else class="preview-placeholder">输入描述，点击「开始生成」，成品将展示在这里</div>
        </div>

        <!-- 下半：图片历史 -->
        <div class="history-area">
          <HistoryGallery
            ref="historyRef"
            type="text-to-image"
            @select="onHistorySelect"
            @goto="onHistoryGoto"
            @loaded="onHistoryLoaded"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.workspace {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
  align-items: start;
}
.panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.panel-title {
  margin: 0 0 4px;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.fields-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
.sampling-group {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elev);
  overflow: hidden;
}
.sampling-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sampling-toggle:hover {
  background: var(--panel);
  color: var(--text);
}
.sampling-chev {
  font-size: 11px;
  color: var(--text-faint);
  transition: transform 0.2s;
}
.sampling-chev.open {
  transform: rotate(180deg);
}
.sampling-body {
  padding: 0 14px 12px;
}
.prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-head label {
  margin-bottom: 0;
}
.prompt-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dense-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 10px;
  font-size: 12px;
  color: var(--text-dim);
  cursor: pointer;
  user-select: none;
}
.dense-row input {
  width: 14px;
  height: 14px;
  accent-color: var(--primary);
  cursor: pointer;
}
.dense-row:has(input:checked) span {
  color: var(--primary);
  font-weight: 600;
}
.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid var(--border-strong);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.icon-btn:hover {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
}
.icon-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}
.spinner-mini {
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
.cat-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: calc(2 * 30px + 6px); /* 最多两行，超出滚动 */
  overflow-y: auto;
}
.cat-btn {
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.cat-btn:hover {
  border-color: var(--primary);
  color: var(--text);
}
.custom-ratio {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.cr-input {
  width: 76px;
  height: 30px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--text);
  font-size: 12px;
  box-sizing: border-box;
  -moz-appearance: textfield;
  appearance: textfield;
}
.cr-input::-webkit-outer-spin-button,
.cr-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.cr-input:focus {
  outline: none;
  border-color: var(--primary);
}
.dim-hint {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--warn);
  line-height: 1.5;
}
.cr-x {
  color: var(--text-faint);
  font-size: 13px;
}
.tip-wrap {
  position: relative;
  display: inline-flex;
  margin-left: 2px;
}
.tip-q {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 11px;
  line-height: 15px;
  text-align: center;
  cursor: help;
  display: inline-block;
}
.tip-box {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: 240px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(15, 20, 25, 0.92);
  color: #fff;
  font-size: 11.5px;
  line-height: 1.5;
  text-align: left;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s;
  z-index: 30;
  white-space: normal;
}
.tip-wrap:hover .tip-box,
.tip-wrap:focus-within .tip-box {
  opacity: 1;
}
.cat-btn.on {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35);
}
.execute {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.generate {
  background: var(--gradient-brand);
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.3);
}
.generate:hover {
  filter: brightness(1.1);
}
textarea {
  resize: vertical;
  min-height: 80px;
}
.generate {
  margin-top: 4px;
}
.error {
  color: var(--danger);
  font-size: 12px;
}
.queue-hint {
  font-size: 11px;
  color: var(--warn);
}

/* ===== 结果区：左右两列，结果:历史 = 3:1 ===== */
.result-panel {
  min-width: 0;
}
.result-split {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr);
  gap: 14px;
  /* 占满 ws-main 剩余高度（顶部导航+子tab+padding） */
  height: calc(100vh - 210px);
  min-height: 420px;
}
.preview-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}
.preview-img-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}
.size-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(15, 20, 25, 0.75);
  font-size: 11px;
  color: #fff;
  font-family: var(--font-mono, monospace);
  z-index: 2;
}
.dl-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 2;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: rgba(15, 20, 25, 0.75);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, transform 0.1s;
}
.dl-btn:hover {
  background: var(--primary);
  transform: scale(1.08);
}
.nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: rgba(15, 20, 25, 0.55);
  color: #fff;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, transform 0.1s;
  padding-bottom: 3px;
}
.nav-btn:hover {
  background: var(--primary);
  transform: translateY(-50%) scale(1.08);
}
.nav-prev {
  left: 10px;
}
.nav-next {
  right: 10px;
}
.preview-count {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.14);
  border: 1px solid rgba(59, 130, 246, 0.35);
  color: var(--primary);
  font-weight: 600;
}
.pin-toggle {
  height: 22px;
  padding: 0 9px;
  border-radius: 6px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.pin-toggle:hover {
  border-color: #f59e0b;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}
.pin-toggle.on {
  border-color: rgba(245, 158, 11, 0.5);
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
  font-weight: 600;
}
.pin-toggle:disabled {
  opacity: 0.6;
  cursor: default;
}
.cat-select-wrap {
  position: relative;
  display: inline-flex;
}
.cat-select {
  height: 22px;
  padding: 0 9px;
  border-radius: 6px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.cat-select:hover {
  border-color: var(--primary);
  color: var(--text);
  background: rgba(59, 130, 246, 0.06);
}
.cat-caret {
  font-size: 9px;
  transition: transform 0.15s;
}
.cat-caret.up {
  transform: rotate(180deg);
}
.cat-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 150px;
  max-height: 280px;
  overflow-y: auto;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  padding: 5px;
  z-index: 50;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 2px;
}
.cat-menu-item {
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 11.5px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.cat-menu-item:hover {
  background: rgba(59, 130, 246, 0.1);
  color: var(--text);
}
.cat-menu-item.on {
  background: rgba(59, 130, 246, 0.14);
  color: var(--primary);
  font-weight: 600;
}
.preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
}
.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}
.preview-meta-parts {
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-note {
  color: var(--warn);
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 4px;
  padding: 1px 6px;
}
.preview-prompt {
  margin: 0;
  font-size: 12px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}
.preview-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-faint);
  font-size: 13px;
  text-align: center;
}
.preview-live {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.preview-live img {
  max-width: 100%;
  max-height: calc(100% - 34px);
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
}
.preview-live-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger);
  animation: live-pulse 1.2s ease-in-out infinite;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.history-area {
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}
.empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 24px 0;
  text-align: center;
}
</style>
