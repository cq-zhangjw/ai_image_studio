<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  accept?: string
  /** 外部预览 URL（服务端带入图等），变化时同步显示 */
  previewUrl?: string
}>()

const emit = defineEmits<{ file: [file: File] }>()

const preview = ref<string>('')
const dragging = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

// 外部带入的预览（如历史跳转 src 图）优先显示；用户重新上传时由 handleFile 覆盖
watch(
  () => props.previewUrl,
  (v) => {
    if (v) preview.value = v
  },
  { immediate: true },
)

function handleFile(file: File | undefined | null) {
  if (!file) return
  if (!file.type.startsWith('image/')) {
    alert('请上传图片文件')
    return
  }
  preview.value = URL.createObjectURL(file)
  emit('file', file)
}

function onDrop(e: DragEvent) {
  dragging.value = false
  handleFile(e.dataTransfer?.files?.[0])
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  handleFile(input.files?.[0])
  input.value = ''
}
</script>

<template>
  <div
    class="drop"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
    @click="inputRef?.click()"
  >
    <input ref="inputRef" type="file" :accept="accept ?? 'image/*'" style="display: none" @change="onPick" />
    <img v-if="preview" :src="preview" alt="preview" class="preview" />
    <template v-else>
      <div class="icon">🖼</div>
      <div class="hint">点击或拖拽上传图片</div>
    </template>
  </div>
</template>

<style scoped>
.drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 120px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-elev);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  overflow: hidden;
  position: relative;
}
.drop.dragging {
  border-color: var(--primary);
  background: var(--primary-soft);
}
.icon {
  font-size: 24px;
}
.hint {
  font-size: 12px;
  color: var(--text-faint);
}
.preview {
  max-width: 100%;
  max-height: 200px;
  object-fit: contain;
}
</style>
