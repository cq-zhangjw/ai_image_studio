<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  label?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const min = computed(() => props.min ?? 0)
const max = computed(() => props.max ?? 100)
const step = computed(() => props.step ?? 1)

const text = ref(String(props.modelValue))

watch(
  () => props.modelValue,
  (v) => {
    text.value = String(v)
  },
)

function onInput(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', v)
  text.value = String(v)
}

function onTextInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
  text.value = raw
  const v = Number(raw)
  if (!Number.isNaN(v)) emit('update:modelValue', v)
}
</script>

<template>
  <div class="field">
    <label v-if="label">{{ label }}</label>
    <div class="row">
      <input type="range" :min="min" :max="max" :step="step" :value="modelValue" @input="onInput" />
      <input class="num mono" type="number" :min="min" :max="max" :value="text" @input="onTextInput" />
    </div>
  </div>
</template>

<style scoped>
.field .row {
  display: flex;
  align-items: center;
  gap: 8px;
}
input[type='range'] {
  flex: 1;
  accent-color: var(--primary);
}
.num {
  width: 64px;
  text-align: right;
}
</style>
