<script setup lang="ts">
// 状态徽标（docs/08 §4.3）：ok 成功 / warn 进行中 / idle 就绪 / brand 品牌 / danger 失败
withDefaults(
  defineProps<{
    type?: 'ok' | 'warn' | 'idle' | 'brand' | 'danger'
    dot?: boolean
  }>(),
  { type: 'idle', dot: true },
)
</script>

<template>
  <span class="badge" :class="`badge-${type}`">
    <span v-if="dot" class="dot" />
    <slot />
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  line-height: 18px;
  white-space: nowrap;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.badge-ok {
  color: var(--success);
  background: rgba(34, 197, 94, 0.12);
}
.badge-warn {
  color: var(--warn);
  background: rgba(245, 158, 11, 0.12);
}
.badge-warn .dot {
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
.badge-idle {
  color: var(--text-dim);
  background: var(--panel-2);
}
.badge-brand {
  color: #fff;
  background: var(--gradient-brand);
}
.badge-danger {
  color: var(--danger);
  background: rgba(239, 68, 68, 0.12);
}
</style>
