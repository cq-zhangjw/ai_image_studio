<script setup lang="ts">
import { ref } from 'vue'
import { assetUrl } from '@/api/client'
import { downloadImage } from '@/utils/download'

const props = defineProps<{
  before: string
  after?: string
  labels?: { left?: string; right?: string }
}>()

const container = ref<HTMLElement | null>(null)
const pos = ref(50)
let dragging = false

// 外部控制滑块位置（带入原图→最右；任务完成→回中间）
function setPos(p: number) {
  pos.value = Math.min(100, Math.max(0, p))
}
defineExpose({ setPos })

// 实际像素尺寸（加载后显示在角落标签）
const beforeSize = ref('')
const afterSize = ref('')
function onBeforeLoad(e: Event) {
  const el = e.target as HTMLImageElement
  if (el.naturalWidth) beforeSize.value = `${el.naturalWidth}×${el.naturalHeight}`
}
function onAfterLoad(e: Event) {
  const el = e.target as HTMLImageElement
  if (el.naturalWidth) afterSize.value = `${el.naturalWidth}×${el.naturalHeight}`
}

async function onDownload() {
  if (!props.after) return
  await downloadImage(assetUrl(props.after), `upscale_${Date.now()}.png`)
}

function setFromClientX(x: number) {
  const el = container.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  pos.value = Math.min(100, Math.max(0, ((x - rect.left) / rect.width) * 100))
}
function onDown(e: PointerEvent) {
  if (!props.after) return // 仅展示原图态：不允许拖动裁剪
  dragging = true
  setFromClientX(e.clientX)
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
}
function onMove(e: PointerEvent) {
  if (dragging && props.after) setFromClientX(e.clientX)
}
function onUp() {
  dragging = false
}
</script>

<template>
  <div
    ref="container"
    class="ba"
    @pointerdown="onDown"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onUp"
  >
    <img v-if="after" class="ba-img ba-after" :src="assetUrl(after)" alt="after" draggable="false" @load="onAfterLoad" />
    <div class="ba-before-wrap" :style="{ clipPath: `inset(0 ${100 - pos}% 0 0)` }">
      <img class="ba-img ba-before" :src="assetUrl(before)" alt="before" draggable="false" @load="onBeforeLoad" />
    </div>
    <div v-if="after" class="ba-divider" :style="{ left: pos + '%' }">
      <span class="ba-handle">⟨⟩</span>
    </div>
    <span class="ba-label ba-left">{{ labels?.left ?? '原图' }}{{ beforeSize ? ` ${beforeSize}` : '' }}</span>
    <span v-if="after" class="ba-label ba-right">{{ labels?.right ?? '放大' }}{{ afterSize ? ` ${afterSize}` : '' }}</span>
    <button v-if="after" class="ba-download" title="下载放大图" @pointerdown.stop @click.stop="onDownload">⬇</button>
  </div>
</template>

<style scoped>
.ba {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-elev);
  width: 100%;
  flex: 1;
  min-height: 0;
  user-select: none;
  touch-action: none;
  cursor: ew-resize;
}
.ba-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  pointer-events: none;
}
.ba-before-wrap {
  position: absolute;
  inset: 0;
  z-index: 2;
}
.ba-before {
  filter: saturate(0.98);
}
.ba-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #fff;
  box-shadow: 0 0 8px rgba(0, 0, 0, 0.5);
  z-index: 3;
  transform: translateX(-1px);
}
.ba-handle {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #fff;
  color: #111;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}
.ba-label {
  position: absolute;
  top: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(15, 20, 25, 0.75);
  font-size: 11px;
  color: #fff;
  z-index: 4;
}
.ba-left {
  left: 8px;
}
.ba-right {
  right: 8px;
}
.ba-download {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 4;
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
.ba-download:hover {
  background: var(--primary);
  transform: scale(1.08);
}
</style>
