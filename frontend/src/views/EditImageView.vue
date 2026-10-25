<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, assetUrl } from '@/api/client'
import { useTaskStore } from '@/stores/task'
import { useReuseStore } from '@/stores/reuse'
import type { OutputRun } from '@/types'
import ParamNumberField from '@/components/ParamNumberField.vue'
import BeforeAfterSlider from '@/components/BeforeAfterSlider.vue'
import HistoryGallery from '@/components/HistoryGallery.vue'
import FileDropUpload from '@/components/FileDropUpload.vue'
import ModelSelector from '@/components/ModelSelector.vue'
import PromptOptimizerModal from '@/components/PromptOptimizerModal.vue'
import FieldGroup from '@/components/FieldGroup.vue'
import Badge from '@/components/Badge.vue'

const store = useTaskStore()
const route = useRoute()

// ---- 功能选择：单图编辑 / 多图融合（默认单图） ----
const mode = ref<'single' | 'fusion'>('single')

// 服务端引用模式（历史跳转带入）：src_stamp/src_image 替代上传
const srcMode = ref(false)
const srcStamp = ref('')
const srcImage = ref('')

const prompt = ref('')
const imageFile = ref<File | null>(null)
const fusionFiles = ref<(File | null)[]>(Array(6).fill(null))
// 融合历史素材还原（服务端引用模式）：九宫格显示历史素材 URL，提交时用 src_stamp + src_images 引用
const fusionSrcMode = ref(false)
const fusionSrcUrls = ref<string[]>(Array(6).fill(''))
const model = ref('qwen-image-2.1')
const steps = ref(24)
const seed = ref(0) // 0 = 随机
const showSampling = ref(false)
const busy = ref(false)
const error = ref('')
const originalUrl = ref('')
const resultUrl = ref('')

const latestTask = ref<any>(null)

// 编辑可用模型（后端白名单）
const EDIT_MODELS = [
  { value: 'qwen-image-2.1', name: 'Qwen-Image-2.1' },
  { value: 'flux2-klein-9b', name: 'FLUX.2 [klein] 9B' },
]

// FLUX.2 klein 走统一编辑（步数建议 20）
watch(model, (m) => {
  if (m === 'flux2-klein-9b') steps.value = 20
  else steps.value = 24
})

function onImage(f: File) {
  imageFile.value = f
  srcMode.value = false
  srcStamp.value = ''
  srcImage.value = ''
  originalUrl.value = URL.createObjectURL(f)
  resultUrl.value = ''
  histBefore.value = ''
  // 上传原图：预览结果区显示原图，滑块拉到最右侧
  nextTick(() => sliderRef.value?.setPos(100))
}

function onFusionFile(i: number, f: File) {
  fusionFiles.value[i] = f
  // 用户重新上传素材 → 退出历史引用模式
  fusionSrcMode.value = false
  fusionSrcUrls.value = []
}

function removeFusion(i: number) {
  fusionFiles.value[i] = null
  fusionSrcUrls.value[i] = ''
}

// 九宫格预览：历史引用素材 URL 优先；否则本地上传文件
function fusionSlotUrl(i: number): string {
  if (fusionSrcUrls.value[i]) return fusionSrcUrls.value[i]
  const f = fusionFiles.value[i]
  return f ? URL.createObjectURL(f) : ''
}

function fusionUrlOf(f: File): string {
  return URL.createObjectURL(f)
}

// 多图融合时素材预览集合（本地文件；历史引用模式用 fusionSrcUrls）
const fusionUploaded = computed(() => fusionFiles.value.filter((x) => x) as File[])
// 素材计数（结果区）：历史引用 → 引用素材数；否则本地上传数
const fusionCount = computed(() => {
  if (fusionSrcMode.value && fusionSrcUrls.value.some(Boolean)) {
    return fusionSrcUrls.value.filter(Boolean).length
  }
  return fusionUploaded.value.length
})

// 提交成功后自动对比展示（用户正在浏览历史时不打断，避免重置为最新结果）
const viewingHistory = ref(false)
const curStamp = ref('')
watch(
  () => store.lastResult,
  (r) => {
    if (r?.outputs?.length && store.lastResult?.taskId === latestTask.value?.id && !viewingHistory.value) {
      resultUrl.value = assetUrl(r.outputs[0])
      // 生图结束：滑块回到正中间
      nextTick(() => sliderRef.value?.setPos(50))
    }
  },
)

// 对比区左栏 URL：单图=原图，融合=首张素材；历史回显优先用历史原图
const histBefore = ref('')

// 同路由 query 变化（编辑历史内点 ✂）不会重新挂载，用 watch immediate 兜底
// 由外部跳转带入（文生图历史 → 去编辑）：设置引用模式并跳过"自动选中最新历史"，
// 避免历史加载后 onSelect 把带入的图覆盖掉
// 注意：必须放在 originalUrl/resultUrl/histBefore 声明之后（TDZ 会导致赋值中断）
const jumpedFromQuery = ref(false)
watch(
  () => route.query,
  () => {
    const s = String(route.query.src ?? '')
    const img = String(route.query.img ?? '')
    if (s && img) {
      jumpedFromQuery.value = true
      srcMode.value = true
      srcStamp.value = s
      srcImage.value = img
      originalUrl.value = assetUrl(`/api/outputs/${s}/${img}`)
      // 清空残留结果，避免误显示上一次任务的对比图
      resultUrl.value = ''
      histBefore.value = ''
      // 带入原图：预览结果区显示原图，滑块拉到最右侧
      nextTick(() => sliderRef.value?.setPos(100))
    } else {
      jumpedFromQuery.value = false
    }
  },
  { immediate: true },
)

const reuse = useReuseStore()
// 主页"做同款"带入：复用路由 query 带入的同一链路（stamp+img → 素材原图 + 跳过历史覆盖）
function applyReuse() {
  const p = reuse.consume()
  if (!p || p.type !== 'edit') return
  const q = (p.params ?? {}) as Record<string, any>
  if (q.model) model.value = String(q.model)
  if (q.num_inference_steps) steps.value = Number(q.num_inference_steps)
  if (q.seed) seed.value = Number(q.seed)
  if (q.prompt) prompt.value = String(q.prompt)
  // 主页带过来的是产物直链（/api/outputs/<stamp>/<img>?t=...）
  const src = String(q._preview_url ?? '')
  if (src) {
    const seg = src.split('?')[0].split('/')
    const img = decodeURIComponent(seg.pop() ?? '')
    const s = seg.pop() ?? ''
    if (s && img) {
      jumpedFromQuery.value = true
      srcMode.value = true
      srcStamp.value = s
      srcImage.value = img
      originalUrl.value = src
      resultUrl.value = ''
      histBefore.value = ''
      nextTick(() => sliderRef.value?.setPos(100))
    }
  }
}

const compareLeft = computed(() => {
  if (histBefore.value) return histBefore.value
  if (mode.value === 'fusion') {
    const f = fusionUploaded.value[0]
    return f ? URL.createObjectURL(f) : ''
  }
  return originalUrl.value
})

// ---- 历史导航：‹ › + 键盘 ←/→，默认显示第一组（最新） ----
const galleryRef = ref<InstanceType<typeof HistoryGallery> | null>(null)
const sliderRef = ref<InstanceType<typeof BeforeAfterSlider> | null>(null)

// ---- 预览图点击放大（lightbox） ----
const lightboxUrl = ref('')
function openLightbox(url: string) {
  if (url) lightboxUrl.value = url
}
function closeLightbox() {
  lightboxUrl.value = ''
}
const histRuns = ref<OutputRun[]>([])
const curHistIndex = ref(-1)

// 多图融合历史：任务 payload 含 _image_paths（多图）；单图编辑无 → 用于隔离两侧历史
function isFusionRun(r: OutputRun | null | undefined): boolean {
  const p = ((r?.params ?? {}) as Record<string, unknown>)
  const paths = p._image_paths
  return Array.isArray(paths) && paths.length > 0
}
// 当前模式可见的历史（单图编辑 / 多图融合互相隔离）
const modeRuns = computed(() =>
  histRuns.value.filter((r) => (mode.value === 'fusion') === isFusionRun(r)),
)
// 传给 HistoryGallery 的过滤：已完成记录按模式隔离；进行中占位任务始终显示
const galleryFilter = computed(() => (r: OutputRun) =>
  r.stamp.startsWith('task:') || (mode.value === 'fusion') === isFusionRun(r),
)
// 切换模式 → 浏览对应模式历史（默认选中第一组）；清空跨模式残留（结果/历史原图），素材各自独立保留
watch(mode, () => {
  viewingHistory.value = true
  curStamp.value = ''
  resultUrl.value = ''
  histBefore.value = ''
  if (modeRuns.value.length) {
    curHistIndex.value = 0
    const r = modeRuns.value[0]
    galleryRef.value?.selectRun(r.stamp, r.images[0])
  } else {
    curHistIndex.value = -1
  }
})

// 批次号 → YYYY/MM/DD hh:mm:ss（stamp 即本地生成时刻，直接格式化避免时区偏差）
function fmtStampDate(stamp: string | undefined): string {
  if (!stamp) return ''
  const m = stamp.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/)
  if (!m) return stamp
  return `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}:${m[6]}`
}

// 当前预览条目的信息（历史选中优先，否则最新任务）
const currentRun = computed<OutputRun | null>(() => {
  if (curHistIndex.value >= 0 && curHistIndex.value < modeRuns.value.length) {
    return modeRuns.value[curHistIndex.value]
  }
  return null
})
const currentModel = computed(() => {
  const r = currentRun.value
  if (r?.params?.model) return String(r.params.model).replace(/^.*[\\/]/, '').slice(0, 26)
  const t = latestTask.value as any
  return t?.model ? String(t.model).replace(/^.*[\\/]/, '').slice(0, 26) : ''
})
const currentStamp = computed(() => {
  const r = currentRun.value
  return fmtStampDate(r?.stamp) || (latestTask.value as any)?.stamp || ''
})
const currentPrompt = computed(() => {
  const r = currentRun.value
  if (r?.prompt) return r.prompt
  return prompt.value
})

function onHistoryLoaded(runs: OutputRun[]) {
  histRuns.value = runs.filter((r) => !r.stamp.startsWith('task:'))
  // 外部跳转带入的图优先展示，不自动选中最新历史（避免覆盖带入图）
  if (jumpedFromQuery.value) return
  if (!modeRuns.value.length) return
  // 用户正在浏览历史：按 stamp 保持当前选择（新批次插入顶部时 index 会漂移）
  if (viewingHistory.value && curStamp.value) {
    const idx = modeRuns.value.findIndex((r) => r.stamp === curStamp.value)
    if (idx >= 0) {
      curHistIndex.value = idx
      return
    }
    // 当前记录已被删除 → 回退选最新
  }
  if (curHistIndex.value < 0 || curHistIndex.value >= modeRuns.value.length) {
    curHistIndex.value = 0
    const r = modeRuns.value[0]
    curStamp.value = r.stamp
    galleryRef.value?.selectRun(r.stamp, r.images[0])
  }
}

function navHistory(dir: 1 | -1) {
  const n = modeRuns.value.length
  if (!n) return
  viewingHistory.value = true
  const start = (curHistIndex.value < 0 ? 0 : curHistIndex.value) + dir
  // 跳过已被删空的组（删除图片后 images 可能为 0）
  for (let k = 0; k < n; k++) {
    const i = (((start + k * dir) % n) + n) % n
    const r = modeRuns.value[i]
    if (r.images.length > 0) {
      curHistIndex.value = i
      curStamp.value = r.stamp
      galleryRef.value?.selectRun(r.stamp, r.images[0])
      return
    }
  }
}

// 删除历史图片：若删除的是当前预览组，组内还有图则重选第一张，组空则自动跳下一组
function onHistoryDeleted(e: { stamp: string; image: string; remaining: number }) {
  if (curStamp.value !== e.stamp) return
  if (e.remaining > 0) {
    galleryRef.value?.selectRun(e.stamp)
  } else {
    navHistory(1)
  }
}

function onSelect(p: { url: string; stamp: string; image: string; prompt: string; source?: string; sources?: string[]; params?: Record<string, unknown> | null }) {
  // 历史条目与当前模式不匹配 → 自动切换对应模式
  const want = isFusionRun(histRuns.value.find((r) => r.stamp === p.stamp)) ? 'fusion' : 'single'
  if (mode.value !== want) mode.value = want
  resultUrl.value = p.url
  histBefore.value = p.source ? assetUrl(`/api/outputs/${p.stamp}/${p.source}`) : ''
  viewingHistory.value = true
  // 同步当前条目索引（供预览信息行显示该条目的时间/模型/指令）
  const idx = modeRuns.value.findIndex((r) => r.stamp === p.stamp)
  if (idx >= 0) {
    curHistIndex.value = idx
    curStamp.value = p.stamp
  }
  // 融合历史：素材还原到九宫格（服务端引用模式，提交时用 src_stamp + src_images）
  if (mode.value === 'fusion') {
    if (p.sources?.length) {
      fusionSrcMode.value = true
      srcStamp.value = p.stamp
      fusionSrcUrls.value = Array(6).fill('')
      p.sources.forEach((s, si) => {
        if (si < 6) fusionSrcUrls.value[si] = assetUrl(`/api/outputs/${p.stamp}/${s}`)
      })
    } else {
      fusionSrcMode.value = false
      fusionSrcUrls.value = []
    }
  }
  // 历史选中即进入服务端引用模式：提交时用 src_stamp/src_image 作为原图源
  if (p.stamp && p.image && mode.value === 'single') {
    srcMode.value = true
    srcStamp.value = p.stamp
    srcImage.value = p.image
  }
  const pr = (p.params ?? {}) as Record<string, unknown>
  const t = typeof pr.prompt === 'string' && pr.prompt ? pr.prompt : p.prompt
  if (t) prompt.value = t
  if (pr.model) model.value = String(pr.model)
  if (pr.num_inference_steps != null) steps.value = Number(pr.num_inference_steps)
  if (pr.seed != null && pr.seed !== '') seed.value = Number(pr.seed)
  // 原图预览回显（单图上传区）
  if (histBefore.value) originalUrl.value = histBefore.value
}

function onKeydown(e: KeyboardEvent) {
  const el = e.target as HTMLElement | null
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
  if (e.key === 'ArrowLeft') navHistory(-1)
  else if (e.key === 'ArrowRight') navHistory(1)
}
onMounted(() => {
  applyReuse()
  window.addEventListener('keydown', onKeydown)
  // 组件挂载兜底：query 带入的原图，滑块拉到最右侧（immediate watch 可能早于挂载）
  if (jumpedFromQuery.value) nextTick(() => sliderRef.value?.setPos(100))
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

async function submit() {
  if (mode.value === 'single') {
    if (!imageFile.value && !(srcMode.value && srcStamp.value && srcImage.value)) {
      error.value = '请先上传原图'
      return
    }
  } else {
    const hasSrc = fusionSrcMode.value && fusionSrcUrls.value.some(Boolean)
    if (!hasSrc && !fusionFiles.value.some((f) => f)) {
      error.value = '请至少上传一张图片'
      return
    }
  }
  if (!prompt.value.trim()) {
    error.value = '请输入编辑说明'
    return
  }
  error.value = ''
  busy.value = true
  try {
    const form = new FormData()
    form.append('prompt', prompt.value)
    form.append('model', model.value)
    form.append('num_inference_steps', String(steps.value))
    if (seed.value) form.append('seed', String(seed.value))
    if (mode.value === 'fusion') {
      // 历史素材引用：src_stamp + src_images（文件名列）；否则上传文件
      const srcNames = fusionSrcUrls.value.filter(Boolean).map((u) => u.split('/').pop() ?? '')
      if (fusionSrcMode.value && srcStamp.value && srcNames.length) {
        form.append('src_stamp', srcStamp.value)
        form.append('src_images', srcNames.join(','))
      } else {
        for (const f of fusionFiles.value) {
          if (f) form.append('images', f)
        }
      }
    } else if (srcMode.value && srcStamp.value && srcImage.value) {
      form.append('src_stamp', srcStamp.value)
      form.append('src_image', srcImage.value)
    } else {
      form.append('image', imageFile.value as File)
    }
    const res = await api.submitEdit(form)
    store.track(res.task_id, 'edit')
    latestTask.value = store.tasks[res.task_id]
    // 回到"最新结果"态：任务完成后自动回传展示；退出历史浏览
    viewingHistory.value = false
    curStamp.value = ''
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
        图像编辑
        <Badge type="brand" :dot="false">Qwen / FLUX</Badge>
      </h2>

      <div class="mode-seg">
        <button
          type="button"
          class="mode-btn"
          :class="{ on: mode === 'single' }"
          @click="mode = 'single'"
        >单图编辑</button>
        <button
          type="button"
          class="mode-btn"
          :class="{ on: mode === 'fusion' }"
          @click="mode = 'fusion'"
        >多图融合</button>
      </div>

      <FieldGroup title="模型选择">
        <ModelSelector v-model="model" model-id="qwen-image-2.1" :options="EDIT_MODELS" />
      </FieldGroup>

      <FieldGroup :title="mode === 'single' ? '原图（必传）' : '图片素材（至少 1 张）'">
        <template v-if="mode === 'single'">
          <FileDropUpload :preview-url="originalUrl" @file="onImage" />
        </template>
        <template v-else>
          <div class="fusion-slots">
            <div v-for="i in 6" :key="i" class="fusion-slot">
              <FileDropUpload
                :preview-url="fusionSlotUrl(i - 1)"
                :hide-hint="true"
                :fill="true"
                @file="(f: File) => onFusionFile(i - 1, f)"
              />
              <button
                v-if="fusionFiles[i - 1]"
                class="fusion-rm"
                type="button"
                @click="removeFusion(i - 1)"
              >×</button>
            </div>
          </div>
        </template>
      </FieldGroup>

      <FieldGroup title="编辑指令">
        <div class="prompt-head">
          <label>编辑说明</label>
          <PromptOptimizerModal v-model="prompt" :model-id="model" @apply="(t: string) => (prompt = t)" />
        </div>
        <textarea v-model="prompt" rows="3" placeholder="描述要修改的内容…（多图融合：描述如何组合这些图片）"></textarea>
      </FieldGroup>

      <div class="sampling-group">
        <button class="sampling-toggle" type="button" @click="showSampling = !showSampling">
          <span>采样参数</span>
          <span class="sampling-chev" :class="{ open: showSampling }">▾</span>
        </button>
        <div v-show="showSampling" class="sampling-body">
          <ParamNumberField v-model="steps" :min="10" :max="40" label="采样步数" />
          <ParamNumberField v-model="seed" :min="0" :max="999999999" label="种子（0=随机）" />
        </div>
      </div>

      <div class="execute">
        <div v-if="error" class="error">{{ error }}</div>
        <button class="btn generate" :disabled="busy" @click="submit">
          {{ busy ? '提交中…' : mode === 'single' ? '开始编辑' : '开始融合' }}
        </button>
        <div v-if="store.activeCount > 0" class="queue-hint">有任务执行中，新任务将排队</div>
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
        <!-- 左：编辑前/后对比 -->
        <div class="preview-area">
          <div class="compare-wrap">
            <template v-if="mode === 'fusion'">
              <div class="fusion-compare">
                <div class="fc-side fc-materials">
                  <div class="fc-label">素材（{{ fusionCount }} 张）</div>
                  <div v-if="fusionSrcMode && fusionSrcUrls.some(Boolean)" class="fc-grid">
                    <img
                      v-for="(u, idx) in fusionSrcUrls.filter(Boolean)"
                      :key="idx"
                      :src="u"
                      class="fc-thumb"
                      alt="素材"
                      @click="openLightbox(u)"
                    />
                  </div>
                  <div v-else-if="fusionUploaded.length" class="fc-grid">
                    <img
                      v-for="(f, idx) in fusionUploaded"
                      :key="idx"
                      :src="fusionUrlOf(f)"
                      class="fc-thumb"
                      alt="素材"
                      @click="openLightbox(fusionUrlOf(f))"
                    />
                  </div>
                  <div v-else class="preview-placeholder">上传图片后显示素材</div>
                </div>
                <div class="fc-side">
                  <div class="fc-label">融合结果</div>
                  <img
                    v-if="resultUrl"
                    :src="resultUrl"
                    class="fc-result"
                    alt="融合结果"
                    @click="openLightbox(resultUrl)"
                  />
                  <div v-else class="preview-placeholder">等待融合结果</div>
                </div>
              </div>
            </template>
            <template v-else-if="resultUrl">
              <BeforeAfterSlider
                v-if="compareLeft"
                ref="sliderRef"
                :before="compareLeft"
                :after="resultUrl"
                :labels="{ left: '原图', right: '结果' }"
              />
              <div v-else class="single-result">
                <img :src="resultUrl" class="edit-result" alt="编辑结果" @click="openLightbox(resultUrl)" />
              </div>
            </template>
            <template v-else-if="compareLeft">
              <!-- 已设置原图（上传/带入），尚未生成结果：显示原图，滑块在最右 -->
              <BeforeAfterSlider ref="sliderRef" :before="compareLeft" :labels="{ left: '原图' }" />
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
                {{ latestTask.status === 'queued' ? '排队中，请稍候…' : '处理中，完成后自动回传展示…' }}
              </div>
            </template>
            <div v-else class="preview-placeholder">上传原图，描述修改内容，结果将展示在这里</div>

            <button
              v-if="modeRuns.length"
              type="button"
              class="nav-btn nav-prev"
              title="上一组（←）"
              @click="navHistory(-1)"
            >‹</button>
            <button
              v-if="modeRuns.length"
              type="button"
              class="nav-btn nav-next"
              title="下一组（→）"
              @click="navHistory(1)"
            >›</button>
          </div>
          <div v-if="modeRuns.length || currentModel || currentStamp" class="preview-meta">
            <span v-if="modeRuns.length" class="preview-count mono">{{ curHistIndex + 1 }}/{{ modeRuns.length }}</span>
            <span class="mono preview-stamp">{{ currentStamp }}</span>
            <span v-if="currentModel" class="preview-meta-parts">{{ currentModel }}</span>
          </div>
          <p v-if="currentPrompt" class="preview-prompt" :title="currentPrompt">{{ currentPrompt }}</p>
        </div>

        <!-- 右：编辑历史 -->
        <div class="history-area">
          <HistoryGallery
            ref="galleryRef"
            type="edit"
            :filter-fn="galleryFilter"
            @loaded="onHistoryLoaded"
            @select="onSelect"
            @goto="(p: any) => $router.push({ path: `/workspace/${p.action}`, query: { src: p.stamp, img: p.image } })"
            @deleted="onHistoryDeleted"
          />
        </div>
      </div>
    </section>

    <!-- 预览图点击放大（lightbox） -->
    <div v-if="lightboxUrl" class="lightbox" @click="closeLightbox">
      <button type="button" class="lightbox-close" title="关闭" @click.stop="closeLightbox">×</button>
      <img :src="lightboxUrl" alt="预览放大" class="lightbox-img" @click.stop />
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
  align-items: start;
  height: 100%;
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
  grid-template-columns: 1fr 1fr;
  gap: 10px;
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
  min-height: 70px;
}
.prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-head label {
  margin-bottom: 0;
}
.error {
  color: var(--danger);
  font-size: 12px;
}
.queue-hint {
  font-size: 11px;
  color: var(--warn);
}
.mode-seg {
  display: flex;
  gap: 6px;
  padding: 2px;
  border-radius: 10px;
  background: var(--bg-elev);
}
.mode-btn {
  flex: 1;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-dim);
  font-size: 12.5px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.mode-btn.on {
  background: var(--gradient-brand);
  color: #fff;
  font-weight: 600;
}
.sampling-group {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.sampling-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border: none;
  background: var(--bg-elev);
  color: var(--text);
  font-size: 12.5px;
  cursor: pointer;
}
.sampling-chev {
  font-size: 11px;
  color: var(--text-dim);
  transition: transform 0.15s;
}
.sampling-chev.open {
  transform: rotate(180deg);
}
.sampling-body {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fusion-slots {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.fusion-slot {
  position: relative;
}
.fusion-rm {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 5;
  height: 22px;
  padding: 0 8px;
  border: none;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.85);
  color: #fff;
  font-size: 11px;
  cursor: pointer;
}
.empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 24px 0;
  text-align: center;
}
.result-panel {
  height: 100%;
  min-height: 0;
}
.result-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr);
  gap: 14px;
  height: calc(100vh - 210px);
  min-height: 420px;
}
.preview-area {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  padding: 10px;
  overflow: hidden;
  position: relative;
}
.compare-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  width: 100%;
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
.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--text-dim);
  padding-top: 8px;
  flex-shrink: 0;
  justify-content: flex-start;
}
.preview-count {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.14);
  border: 1px solid rgba(59, 130, 246, 0.35);
  color: var(--primary);
  font-weight: 600;
  font-size: 11px;
}
.preview-stamp {
  font-size: 11px;
}
.preview-meta-parts {
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.fusion-compare {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  min-height: 0;
}
.fc-side {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}
.fc-label {
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}
.fc-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  overflow-y: auto;
  align-content: center;
}
.fc-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: scale-down;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #000;
  cursor: zoom-in;
}
.fc-result {
  flex: 1;
  min-height: 0;
  width: 100%;
  object-fit: contain;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #000;
  cursor: zoom-in;
}
.single-result {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.edit-result {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 10px;
  border: 1px solid var(--border);
  cursor: zoom-in;
}
/* 预览图点击放大 */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
  animation: lightbox-in 0.15s ease;
}
.lightbox-img {
  max-width: 92vw;
  max-height: 92vh;
  object-fit: contain;
  border-radius: 8px;
  cursor: zoom-out;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
}
.lightbox-close {
  position: absolute;
  top: 18px;
  right: 24px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.35);
  background: rgba(15, 20, 25, 0.55);
  color: #fff;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-bottom: 3px;
}
.lightbox-close:hover {
  background: var(--danger);
}
@keyframes lightbox-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.history-area {
  min-height: 0;
  overflow-y: auto;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  padding: 4px 6px;
}
.preview-placeholder {
  flex: 1;
  min-height: 0;
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
</style>
