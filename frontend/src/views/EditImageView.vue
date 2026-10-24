<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, assetUrl } from '@/api/client'
import { useTaskStore } from '@/stores/task'
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

// 同路由 query 变化（编辑历史内点 ✂）不会重新挂载，用 watch immediate 兜底
watch(
  () => route.query,
  () => {
    const s = String(route.query.src ?? '')
    const img = String(route.query.img ?? '')
    if (s && img) {
      srcMode.value = true
      srcStamp.value = s
      srcImage.value = img
      originalUrl.value = assetUrl(`/api/outputs/${s}/${img}`)
    }
  },
  { immediate: true },
)

const prompt = ref('')
const imageFile = ref<File | null>(null)
const fusionFiles = ref<(File | null)[]>(Array(9).fill(null))
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
  { value: 'flux2-klein-4b', name: 'FLUX.2 [klein] 4B' },
]

// FLUX.2 klein 走统一编辑（步数建议 4）
watch(model, (m) => {
  if (m === 'flux2-klein-4b') steps.value = 4
  else steps.value = 24
})

function onImage(f: File) {
  imageFile.value = f
  srcMode.value = false
  srcStamp.value = ''
  srcImage.value = ''
  originalUrl.value = URL.createObjectURL(f)
}

function onFusionFile(i: number, f: File) {
  fusionFiles.value[i] = f
}

function removeFusion(i: number) {
  fusionFiles.value[i] = null
}

function fusionSlotUrl(i: number): string {
  const f = fusionFiles.value[i]
  return f ? URL.createObjectURL(f) : ''
}

function fusionUrlOf(f: File): string {
  return URL.createObjectURL(f)
}

// 多图融合时素材预览集合
const fusionUploaded = computed(() => fusionFiles.value.filter((x) => x) as File[])

// 提交成功后自动对比展示
watch(
  () => store.lastResult,
  (r) => {
    if (r?.outputs?.length && store.lastResult?.taskId === latestTask.value?.id) {
      resultUrl.value = assetUrl(r.outputs[0])
    }
  },
)

// 对比区左栏 URL：单图=原图，融合=首张素材；历史回显优先用历史原图
const histBefore = ref('')
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
const histRuns = ref<OutputRun[]>([])
const curHistIndex = ref(-1)

function onHistoryLoaded(runs: OutputRun[]) {
  histRuns.value = runs.filter((r) => !r.stamp.startsWith('task:'))
  if (histRuns.value.length && (curHistIndex.value < 0 || curHistIndex.value >= histRuns.value.length)) {
    curHistIndex.value = 0
    const r = histRuns.value[0]
    galleryRef.value?.selectRun(r.stamp, r.images[0])
  }
}

function navHistory(dir: 1 | -1) {
  const n = histRuns.value.length
  if (!n) return
  curHistIndex.value = ((curHistIndex.value < 0 ? 0 : curHistIndex.value) + dir + n) % n
  const r = histRuns.value[curHistIndex.value]
  galleryRef.value?.selectRun(r.stamp, r.images[0])
}

function onSelect(p: { url: string; stamp: string; image: string; prompt: string; source?: string; params?: Record<string, unknown> | null }) {
  resultUrl.value = p.url
  histBefore.value = p.source ? assetUrl(`/api/outputs/${p.stamp}/${p.source}`) : ''
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
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

async function submit() {
  if (mode.value === 'single') {
    if (!imageFile.value && !(srcMode.value && srcStamp.value && srcImage.value)) {
      error.value = '请先上传原图'
      return
    }
  } else {
    if (!fusionFiles.value.some((f) => f)) {
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
      for (const f of fusionFiles.value) {
        if (f) form.append('images', f)
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
            <div v-for="i in 9" :key="i" class="fusion-slot">
              <FileDropUpload
                :preview-url="fusionSlotUrl(i - 1)"
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
          <div class="pa-nav">
            <button type="button" class="pa-nav-btn" title="上一组（←）" @click="navHistory(-1)">‹</button>
            <span class="pa-nav-count">{{ histRuns.length ? `${curHistIndex + 1}/${histRuns.length}` : '0/0' }}</span>
            <button type="button" class="pa-nav-btn" title="下一组（→）" @click="navHistory(1)">›</button>
          </div>
          <template v-if="mode === 'fusion'">
            <div class="fusion-compare">
              <div class="fc-side fc-materials">
                <div class="fc-label">素材（{{ fusionUploaded.length || (histBefore ? 1 : 0) }} 张）</div>
                <div v-if="fusionUploaded.length" class="fc-grid">
                  <img
                    v-for="(f, idx) in fusionUploaded"
                    :key="idx"
                    :src="fusionUrlOf(f)"
                    class="fc-thumb"
                    alt="素材"
                  />
                </div>
                <div v-else-if="histBefore" class="fc-grid">
                  <img :src="histBefore" class="fc-thumb" alt="素材" />
                </div>
                <div v-else class="preview-placeholder">上传图片后显示素材</div>
              </div>
              <div class="fc-side">
                <div class="fc-label">融合结果</div>
                <img v-if="resultUrl" :src="resultUrl" class="fc-result" alt="融合结果" />
                <div v-else class="preview-placeholder">等待融合结果</div>
              </div>
            </div>
          </template>
          <template v-else-if="resultUrl">
            <BeforeAfterSlider v-if="compareLeft" :before="compareLeft" :after="resultUrl" :labels="{ left: '原图', right: '结果' }" />
            <div v-else class="single-result">
              <img :src="resultUrl" class="edit-result" alt="编辑结果" />
            </div>
          </template>
          <template v-else-if="latestTask && (latestTask.status === 'running' || latestTask.status === 'queued')">
            <div class="preview-placeholder">
              {{ latestTask.status === 'queued' ? '排队中，请稍候…' : '处理中，完成后自动回传展示…' }}
            </div>
          </template>
          <div v-else class="preview-placeholder">上传原图，描述修改内容，结果将展示在这里</div>
        </div>

        <!-- 右：编辑历史 -->
        <div class="history-area">
          <HistoryGallery
            ref="galleryRef"
            type="edit"
            @loaded="onHistoryLoaded"
            @select="onSelect"
            @goto="(p: any) => $router.push({ path: `/workspace/edit`, query: { src: p.stamp, img: p.image } })"
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
  grid-template-columns: minmax(0, 3fr) minmax(0, 1fr);
  gap: 14px;
  height: calc(100vh - 210px);
  min-height: 420px;
}
.preview-area {
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  padding: 10px;
  overflow: hidden;
  position: relative;
}
.pa-nav {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.45);
  border-radius: 999px;
  padding: 2px 6px;
}
.pa-nav-btn {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}
.pa-nav-btn:hover {
  background: var(--primary);
}
.pa-nav-count {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.9);
  min-width: 40px;
  text-align: center;
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
  align-content: start;
}
.fc-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.fc-result {
  flex: 1;
  min-height: 0;
  width: 100%;
  object-fit: contain;
  border-radius: 8px;
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
  color: var(--text-faint);
  font-size: 13px;
  text-align: center;
}
</style>
