<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api/client'
import { useTaskStore } from '@/stores/task'
import RatioSelector from '@/components/RatioSelector.vue'
import DirectionChips from '@/components/DirectionChips.vue'
import ParamNumberField from '@/components/ParamNumberField.vue'
import ImageGallery from '@/components/ImageGallery.vue'
import FileDropUpload from '@/components/FileDropUpload.vue'
import FieldGroup from '@/components/FieldGroup.vue'
import Badge from '@/components/Badge.vue'

const store = useTaskStore()

const imageFile = ref<File | null>(null)
const prompt = ref('')
const targetRatio = ref('16:9')
const direction = ref('right')
const fill = ref('edge')
const steps = ref(20)
const seed = ref(0)
const busy = ref(false)
const error = ref('')
const originalUrl = ref('')

const latestTask = ref<any>(null)

const RATIOS = [
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
  { value: '1:1', label: '1:1' },
  { value: '4:3', label: '4:3' },
  { value: '3:4', label: '3:4' },
]

const DIRECTIONS = [
  { value: 'right', label: '向右' },
  { value: 'left', label: '向左' },
  { value: 'up', label: '向上' },
  { value: 'down', label: '向下' },
  { value: 'all', label: '四周' },
]

const FILLS = [
  { value: 'edge', label: '边缘延伸' },
  { value: 'white', label: '白色' },
  { value: 'gray', label: '灰色' },
]

function onImage(f: File) {
  imageFile.value = f
  originalUrl.value = URL.createObjectURL(f)
}

async function submit() {
  if (!imageFile.value) {
    error.value = '请先上传原图'
    return
  }
  error.value = ''
  busy.value = true
  try {
    const form = new FormData()
    form.append('image', imageFile.value)
    form.append('prompt', prompt.value)
    form.append('target_ratio', targetRatio.value)
    form.append('direction', direction.value)
    form.append('fill', fill.value)
    form.append('num_inference_steps', String(steps.value))
    form.append('seed', seed.value ? String(seed.value) : '')
    const res = await api.submitOutpaint(form)
    store.track(res.task_id, 'outpaint')
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
        图像扩图
        <Badge type="brand" :dot="false">无缝扩展</Badge>
      </h2>

      <FieldGroup title="素材">
        <label>原图（必传）</label>
        <FileDropUpload @file="onImage" />
      </FieldGroup>

      <FieldGroup title="扩展设置">
        <label>目标比例</label>
        <RatioSelector v-model="targetRatio" :options="RATIOS" />

        <label>扩展方向</label>
        <DirectionChips v-model="direction" :options="DIRECTIONS" />

        <label>留白填充</label>
        <RatioSelector v-model="fill" :options="FILLS" />

        <label>扩图描述（留空自动拼接）</label>
        <textarea v-model="prompt" rows="2" placeholder="扩展区域内容，如：沙漠、雪原、城市…"></textarea>

        <div class="fields-grid">
          <ParamNumberField v-model="steps" :min="10" :max="40" label="采样步数" />
          <ParamNumberField v-model="seed" :min="0" :max="999999999" label="种子（0=随机）" />
        </div>
      </FieldGroup>

      <div class="execute">
        <div v-if="error" class="error">{{ error }}</div>
        <button class="btn generate" :disabled="busy || store.activeCount > 0" @click="submit">
          {{ busy ? '提交中…' : '开始扩图' }}
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
      <div v-if="latestTask && latestTask.status !== 'succeeded'" class="empty">
        {{ latestTask.status === 'queued' ? '排队中，请稍候…' : '处理中，完成后自动回传展示…' }}
      </div>
      <ImageGallery
        v-if="store.lastResult && store.lastResult.outputs.length"
        :images="store.lastResult.outputs"
        :compare-with="originalUrl"
        :compare-labels="{ left: '原图', right: '扩图结果' }"
      />
      <div v-else class="empty">上传原图，选择目标比例与方向，扩图结果将展示在这里</div>
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
  min-height: 50px;
}
.error {
  color: var(--danger);
  font-size: 12px;
}
.queue-hint {
  font-size: 11px;
  color: var(--warn);
}
.empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 24px 0;
  text-align: center;
}
</style>
