<script setup lang="ts">
defineProps<{
  modelValue: string
  options: { value: string; label: string }[]
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function select(v: string) {
  emit('update:modelValue', v)
}
</script>

<template>
  <div class="chips">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="chip"
      :class="{ active: modelValue === opt.value }"
      @click="select(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>
