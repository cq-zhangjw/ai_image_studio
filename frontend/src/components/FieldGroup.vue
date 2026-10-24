<script setup lang="ts">
// 参数分区容器：分组标签 + 分隔线（docs/08 §4.3）
defineProps<{ title: string }>()
</script>

<template>
  <div class="field-group">
    <div class="group-label">{{ title }}</div>
    <div class="group-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.field-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
}
.field-group:first-child {
  border-top: none;
  padding-top: 0;
}
.field-group:last-child {
  padding-bottom: 0;
}
.group-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-dim);
  letter-spacing: 0.4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.group-label::before {
  content: '';
  width: 3px;
  height: 12px;
  border-radius: 2px;
  background: var(--gradient-brand);
}
.group-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
