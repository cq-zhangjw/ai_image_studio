<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, assetUrl } from '@/api/client'
import { downloadImage } from '@/utils/download'
import { useTaskStore } from '@/stores/task'
import RatioSelector from '@/components/RatioSelector.vue'
import BeforeAfterSlider from '@/components/BeforeAfterSlider.vue'
import HistoryGallery from '@/components/HistoryGallery.vue'
import FileDropUpload from '@/components/FileDropUpload.vue'
import FieldGroup from '@/components/FieldGroup.vue'
import Badge from '@/components/Badge.vue'

const store = useTaskStore()
const route = useRoute()

// 服务端引用模式（历史跳转带入）：src_stamp/src_image 替代上传
const srcMode = ref(false)
const srcStamp = ref('')
const srcImage = ref('')

const mode = ref<'single'>('single')
const imageFile = ref<File | null>(null)
const busy = ref(false)
const error = ref('')
const originalUrl = ref('')

// 同路由 query 变化（放大历史内点 🔍）不会重新挂载，用 watch immediate 兜底
// 注意：必须放在 originalUrl 声明之后（TDZ 会导致赋值中断）
const sliderRef = ref<InstanceType<typeof BeforeAfterSlider> | null>(null)
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
      // 带入原图：预览结果区显示原图，滑块拉到最右侧
      nextTick(() => sliderRef.value?.setPos(100))
    }
  },
  { immediate: true },
)

const latestTask = ref<any>(null)

// 放大完成：滑块回到正中间
watch(
  () => store.lastResult,
  (r) => {
    if (r?.outputs?.length && store.lastResult?.taskId === latestTask.value?.id) {
      nextTick(() => sliderRef.value?.setPos(50))
    }
  },
)

// 放大历史选中预览：有原图副本(source) → 滑块对比；否则单图
const historyPreview = ref<{ url: string; stamp: string; image: string; source: string } | null>(null)

function onHistorySelect(p: { url: string; stamp: string; image: string; prompt: string; pinned: boolean; source?: string }) {
  historyPreview.value = { url: p.url, stamp: p.stamp, image: p.image, source: p.source || '' }
  historySize.value = ''
  // 历史回显对比：滑块回正中间
  nextTick(() => sliderRef.value?.setPos(50))
}

// 历史单图真实像素尺寸（左上角角标）
const historySize = ref('')
function onHistoryImgLoad(e: Event) {
  const el = e.target as HTMLImageElement
  if (el.naturalWidth) historySize.value = `${el.naturalWidth}×${el.naturalHeight}`
}

// 放大引擎：Real-ESRGAN（ncnn-vulkan 快速超分，秒级，不占 CUDA 显存）
const engine = ref('realesrgan')
const ENGINES = [
  { value: 'realesrgan', label: 'Real-ESRGAN 快速超分' },
]

const SCALES = [
  { value: '2', label: '2x' },
  { value: '3', label: '3x' },
  { value: '4', label: '4x' },
]
const scale = ref('2')

const MODES = [
  { value: 'single', label: '单张' },
]

function onImage(f: File) {
  imageFile.value = f
  srcMode.value = false
  srcStamp.value = ''
  srcImage.value = ''
  originalUrl.value = URL.createObjectURL(f)
  historyPreview.value = null
  // 上传原图：预览结果区显示原图，滑块拉到最右侧
  nextTick(() => sliderRef.value?.setPos(100))
}

async function submit() {
  error.value = ''
  busy.value = true
  let taskId = ''
  try {
    const form = new FormData()
    if (srcMode.value && srcStamp.value && srcImage.value) {
      form.append('src_stamp', srcStamp.value)
      form.append('src_image', srcImage.value)
    } else {
      if (!imageFile.value) {
        error.value = '请先上传图片'
        return
      }
      form.append('image', imageFile.value)
    }
    form.append('engine', engine.value)
    form.append('scale', String(scale.value))
    const res = await api.submitUpscale(form)
    taskId = res.task_id
    if (taskId) {
      store.track(taskId, 'upscale')
      latestTask.value = store.tasks[taskId]
    }
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
        图像放大
      </h2>

      <FieldGroup title="任务模式">
        <label>模式</label>
        <RatioSelector v-model="mode" :options="MODES" />
      </FieldGroup>

      <FieldGroup title="素材">
        <label>原图（必传）</label>
        <FileDropUpload :preview-url="originalUrl" @file="onImage" />
      </FieldGroup>

      <FieldGroup title="放大参数">
        <label>放大引擎</label>
        <RatioSelector v-model="engine" :options="ENGINES" />

        <label>倍数</label>
        <RatioSelector v-model="scale" :options="SCALES" />
      </FieldGroup>

      <div class="execute">
        <div v-if="error" class="error">{{ error }}</div>
        <button class="btn generate" :disabled="busy || store.activeCount > 0" @click="submit">
          {{ busy ? '提交中…' : '开始放大' }}
        </button>
        <div v-if="store.activeCount > 0" class="queue-hint">有任务执行中，新任务将排队（单张约 1-4 分钟）</div>
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
        <!-- 左（3fr）：当前结果（对比/单图/占位） -->
        <div class="preview-area">
          <template v-if="latestTask && (latestTask.status === 'running' || latestTask.status === 'queued')">
            <div class="preview-placeholder">
              {{ latestTask.status === 'queued' ? '排队中，请稍候…' : '放大中，完成后自动回传展示…' }}
            </div>
          </template>
          <template v-else-if="historyPreview">
            <BeforeAfterSlider
              v-if="historyPreview.source"
              ref="sliderRef"
              :before="assetUrl(`/api/outputs/${historyPreview.stamp}/${historyPreview.source}`)"
              :after="historyPreview.url"
              :labels="{ left: '原图', right: '放大' }"
            />
            <template v-else>
              <div class="preview-img-wrap">
                <img
                  :src="historyPreview.url"
                  :alt="historyPreview.image"
                  class="preview-img"
                  decoding="async"
                  @load="onHistoryImgLoad"
                />
                <span v-if="historySize" class="size-badge">{{ historySize }}</span>
                <button
                  class="dl-btn"
                  title="下载图片"
                  @click.stop="downloadImage(historyPreview.url, `upscale_${historyPreview.stamp}.png`)"
                >
                  ⬇
                </button>
              </div>
              <div class="preview-meta">
                <span class="mono preview-stamp">{{ historyPreview.stamp }}</span>
                <span class="mono preview-file">{{ historyPreview.image }}</span>
              </div>
            </template>
          </template>
          <template
            v-else-if="
              originalUrl && store.lastResult?.outputs?.length && store.lastResult?.taskId === latestTask.value?.id
            "
          >
            <BeforeAfterSlider
              ref="sliderRef"
              :before="originalUrl"
              :after="store.lastResult.outputs[0]"
              :labels="{ left: '原图', right: '放大' }"
            />
          </template>
          <template v-else-if="originalUrl">
            <!-- 已设置原图（上传/带入），尚未生成结果：显示原图，滑块在最右 -->
            <BeforeAfterSlider ref="sliderRef" :before="originalUrl" :labels="{ left: '原图' }" />
          </template>
          <div v-else class="preview-placeholder">确认素材与参数后，点击「开始放大」，对比结果将展示在这里</div>
        </div>

        <!-- 右（1fr）：放大历史 -->
        <div class="history-area">
          <HistoryGallery
            type="upscale"
            title="放大历史"
            @select="onHistorySelect"
            @goto="(p: any) => $router.push({ path: `/workspace/${p.action}`, query: { src: p.stamp, img: p.image } })"
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
.preview-stamp {
  font-size: 11px;
}
.preview-file {
  font-size: 11px;
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
.history-area {
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}
.panel-title {
  margin: 0 0 4px;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
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
.error {
  color: var(--danger);
  font-size: 12px;
}
.queue-hint {
  font-size: 11px;
  color: var(--warn);
}
.note {
  font-size: 12px;
  color: var(--text-faint);
}
.switch-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}
</style>
