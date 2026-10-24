<script setup lang="ts">
// 热门标签灵感弹窗：分类标签点选 → qwen 组合生成提示词 → 预览可编辑 → 回填
import { ref } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  modelValue: boolean
  modelId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'apply', text: string): void
}>()

interface TagCat {
  key: string
  label: string
  tags: string[]
}

const CATEGORIES: TagCat[] = [
  { key: '人物', label: '人物', tags: ['少女', '少年', '老者', '骑士', '精灵', '武士', '宇航员', '渔夫', '舞者', '小丑'] },
  { key: '动物', label: '动物', tags: ['猫', '狐狸', '狼', '鲸', '鹰', '龙', '兔', '鹿', '企鹅', '蝴蝶'] },
  { key: '风景', label: '风景', tags: ['雪山', '森林', '海滩', '沙漠', '星空', '极光', '瀑布', '麦田', '岛屿', '城市天际线'] },
  { key: '建筑', label: '建筑', tags: ['城堡', '灯塔', '寺庙', '摩天楼', '吊脚楼', '车站', '图书馆', '古桥', '风车', '废墟'] },
  { key: '风格', label: '热门风格', tags: ['赛博朋克', '水墨', '浮世绘', '像素', '水彩', '油画', '3D渲染', '黑白摄影', '玻璃拟态', '吉卜力'] },
  { key: '主题', label: '热门主题', tags: ['美食', '科幻', '奇幻', '蒸汽朋克', '复古', '未来', '夏日', '冬日', '太空', '雨夜'] },
  { key: '氛围', label: '氛围', tags: ['梦幻', '治愈', '史诗', '孤独', '欢快', '神秘', '静谧', '热血', '浪漫', '诡异'] },
]

const selected = ref<string[]>([])
const generating = ref(false)
const preview = ref('')
const genError = ref('')
const genMeta = ref<{ model: string; elapsed: number } | null>(null)

function toggle(tag: string) {
  const i = selected.value.indexOf(tag)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(tag)
}

function clearAll() {
  selected.value = []
  preview.value = ''
  genError.value = ''
  genMeta.value = null
}

async function generate() {
  if (!selected.value.length) {
    genError.value = '请先选择至少一个标签'
    return
  }
  generating.value = true
  genError.value = ''
  genMeta.value = null
  try {
    const desc = `画面元素：${selected.value.join('、')}。请基于以上元素组合成一条完整、有创意的图像生成提示词，补充构图、光线、色彩、风格与氛围细节，直接输出提示词本身。`
    const res = await api.optimizePrompt({
      prompt: desc,
      target_model: props.modelId && props.modelId !== 'qwen-image-2.1' ? props.modelId : 'auto',
    })
    preview.value = res.optimized
    genMeta.value = { model: res.model, elapsed: res.elapsed_seconds }
  } catch (e) {
    genError.value = (e as Error).message
  } finally {
    generating.value = false
  }
}

function apply() {
  if (!preview.value.trim()) return
  emit('apply', preview.value)
  close()
}

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <div v-if="modelValue" class="tag-mask" @click.self="close">
    <div class="tag-modal card">
      <div class="tag-head">
        <h3>热门标签灵感</h3>
        <button class="close" title="关闭" @click="close">×</button>
      </div>

      <div class="tag-body">
        <!-- 左：分类标签 -->
        <div class="tag-cats">
          <div v-for="cat in CATEGORIES" :key="cat.key" class="cat-block">
            <div class="cat-label">{{ cat.label }}</div>
            <div class="cat-tags">
              <button
                v-for="t in cat.tags"
                :key="t"
                class="tag-chip"
                :class="{ on: selected.includes(t) }"
                @click="toggle(t)"
              >
                {{ t }}
              </button>
            </div>
          </div>
        </div>

        <!-- 右：已选 + 生成预览 -->
        <div class="tag-preview">
          <div class="pv-block">
            <div class="pv-head">
              <label>已选标签（{{ selected.length }}）</label>
              <button v-if="selected.length" class="mini-btn" @click="clearAll">清空</button>
            </div>
            <div v-if="!selected.length" class="pv-empty">点击左侧标签加入，再点取消</div>
            <div v-else class="pv-chips">
              <span v-for="t in selected" :key="t" class="chip-on">
                {{ t }}<button class="chip-x" @click="toggle(t)">×</button>
              </span>
            </div>
          </div>

          <div class="pv-block pv-gen">
            <div class="pv-head">
              <label>生成提示词</label>
              <div class="pv-meta">
                <span v-if="genMeta" class="pv-meta-text">{{ genMeta.model }} · {{ genMeta.elapsed }}s</span>
                <button class="btn btn-secondary btn-sm" :disabled="generating || !selected.length" @click="generate">
                  {{ generating ? '生成中…' : '生成提示词' }}
                </button>
              </div>
            </div>
            <div v-if="genError" class="pv-error">{{ genError }}</div>
            <textarea
              v-model="preview"
              class="pv-textarea"
              rows="7"
              placeholder="选择标签后点击「生成提示词」，qwen 将组合出完整提示词，可在此手动修改"
            ></textarea>
          </div>
        </div>
      </div>

      <div class="tag-actions">
        <button class="btn btn-secondary" @click="close">关闭</button>
        <button class="btn" :disabled="!preview.trim()" @click="apply">回填至描述框</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tag-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}
.tag-modal {
  width: 70vw;
  height: 70vh;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
}
.tag-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tag-head h3 {
  margin: 0;
  font-size: 16px;
}
.close {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.close:hover {
  color: var(--text);
}
.tag-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
}
.tag-cats {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 6px;
}
.cat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag-chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s;
}
.tag-chip:hover {
  border-color: var(--primary);
  color: var(--text);
}
.tag-chip.on {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35);
}
.tag-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.pv-block {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  background: var(--bg-elev);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pv-head label {
  margin-bottom: 0;
  font-size: 12.5px;
}
.pv-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pv-meta-text {
  font-size: 11px;
  color: var(--text-faint);
}
.mini-btn {
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 11.5px;
  cursor: pointer;
}
.mini-btn:hover {
  color: var(--danger);
  border-color: var(--danger);
}
.pv-empty {
  font-size: 12px;
  color: var(--text-faint);
}
.pv-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip-on {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 12px;
}
.chip-x {
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0;
}
.chip-x:hover {
  color: var(--danger);
}
.pv-gen {
  flex: 1;
  min-height: 0;
}
.pv-textarea {
  flex: 1;
  width: 100%;
  resize: none;
  font-size: 13px;
  line-height: 1.6;
}
.pv-error {
  font-size: 12px;
  color: var(--danger);
}
.tag-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
@media (max-width: 900px) {
  .tag-body {
    grid-template-columns: 1fr;
  }
}
</style>
