<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useModelStore } from '@/stores/model'

const store = useModelStore()
let timer: number | undefined

onMounted(() => {
  store.refresh()
  store.refreshStats(50)
  timer = window.setInterval(() => store.refresh(), 5000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})

function gpuPercent(): number {
  const p = store.gpu.percent
  return typeof p === 'number' ? p : 0
}

function fmtMb(mb?: number | null): string {
  if (mb == null) return '--'
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${mb}MB`
}

/** 按模型聚合统计：最近 N 条 + 平均耗时 */
function statsByModel() {
  const map = new Map<string, { count: number; total: number; latest: number | null; avg: number | null }>()
  for (const s of store.stats) {
    if (!s.model || s.elapsed_seconds == null) continue
    const cur = map.get(s.model) ?? { count: 0, total: 0, latest: null, avg: null }
    cur.count += 1
    cur.total += s.elapsed_seconds
    if (cur.latest === null) cur.latest = s.elapsed_seconds // stats 已倒序，首条即最近
    map.set(s.model, cur)
  }
  const list = [...map.entries()].map(([model, v]) => ({
    model,
    count: v.count,
    latest: v.latest,
    avg: v.count ? v.total / v.count : null,
  }))
  list.sort((a, b) => (b.latest ?? 0) - (a.latest ?? 0))
  return list
}

/** 条形图宽度：相对最大耗时归一化 */
function barWidth(latest: number | null, max: number): string {
  if (latest == null || max <= 0) return '0%'
  return `${Math.max(4, Math.round((latest / max) * 100))}%`
}

function maxLatest(list: { latest: number | null }[]): number {
  return Math.max(1, ...list.map((x) => x.latest ?? 0))
}
</script>

<template>
  <aside class="sidebar">
    <section class="card">
      <h3 class="sec-title">模型</h3>
      <div v-for="m in store.models" :key="m.id" class="model-row">
        <div class="model-name mono">{{ m.name }}</div>
        <span v-if="m.loaded" class="badge badge-ok">已加载</span>
        <span v-else class="badge badge-idle">已就绪</span>
      </div>
    </section>

    <section class="card">
      <h3 class="sec-title">GPU 状态</h3>
      <div class="gpu-name">{{ store.gpu.name ?? 'CUDA 不可用' }}</div>
      <div class="gpu-bar-wrap">
        <div class="gpu-bar" :style="{ width: gpuPercent() + '%' }"></div>
      </div>
      <div class="gpu-meta">
        <span>显存 {{ fmtMb(store.gpu.used_mb) }} / {{ fmtMb(store.gpu.total_mb) }}</span>
        <span class="mono">{{ gpuPercent().toFixed(1) }}%</span>
      </div>
    </section>

    <section class="card">
      <h3 class="sec-title">最近推理统计</h3>
      <div class="stat-row">
        <span>耗时</span>
        <span class="mono">{{ store.lastStats.elapsed_seconds != null ? store.lastStats.elapsed_seconds.toFixed(1) + 's' : '--' }}</span>
      </div>
      <div class="stat-row">
        <span>速度</span>
        <span class="mono">{{ store.lastStats.steps_per_second != null ? store.lastStats.steps_per_second.toFixed(2) + ' steps/s' : '--' }}</span>
      </div>
      <div class="stat-row">
        <span>模型加载</span>
        <span class="mono">{{ store.lastStats.model_load_seconds != null ? store.lastStats.model_load_seconds.toFixed(1) + 's' : '--' }}</span>
      </div>
    </section>

    <section class="card">
      <h3 class="sec-title">历史统计</h3>
      <div v-if="!store.stats.length" class="stat-empty">暂无历史数据</div>
      <div v-for="s in statsByModel()" :key="s.model" class="hist-block">
        <div class="hist-head">
          <span class="hist-model mono">{{ s.model }}</span>
          <span class="hist-count">{{ s.count }} 次</span>
        </div>
        <div class="hist-bar-wrap">
          <div
            class="hist-bar"
            :style="{ width: barWidth(s.latest, maxLatest(statsByModel())) }"
          ></div>
        </div>
        <div class="hist-meta">
          <span>最近 {{ s.latest != null ? s.latest.toFixed(1) + 's' : '--' }}</span>
          <span>均值 {{ s.avg != null ? s.avg.toFixed(1) + 's' : '--' }}</span>
        </div>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.card {
  position: relative;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--glass-border);
  border-radius: 14px;
  padding: 14px;
}
.sec-title {
  position: relative;
  margin: 0 0 10px;
  padding-left: 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.sec-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 2px;
  width: 3px;
  border-radius: 2px;
  background: var(--gradient-brand);
}
.model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  margin: 0 -8px;
  border-radius: 8px;
  transition: background 0.15s;
}
.model-row:hover {
  background: var(--card-hover);
}
.model-name {
  font-size: 12px;
}
.gpu-name {
  font-size: 13px;
  margin-bottom: 8px;
  color: var(--text-dim);
}
.gpu-bar-wrap {
  height: 8px;
  border-radius: 4px;
  background: var(--bg-elev);
  overflow: hidden;
}
.gpu-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), #60a5fa);
  transition: width 0.4s;
}
.gpu-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 6px;
}
.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 4px 0;
  color: var(--text-dim);
}
.stat-row .mono {
  color: var(--text);
}
.stat-empty {
  color: var(--text-faint);
  font-size: 12px;
  padding: 8px 0;
  text-align: center;
}
.hist-block {
  padding: 8px 0;
  border-top: 1px solid var(--border);
}
.hist-block:first-of-type {
  border-top: none;
}
.hist-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  margin-bottom: 5px;
}
.hist-model {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}
.hist-count {
  color: var(--text-faint);
  flex-shrink: 0;
}
.hist-bar-wrap {
  height: 6px;
  border-radius: 3px;
  background: var(--bg-elev);
  overflow: hidden;
}
.hist-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), #8b5cf6);
  transition: width 0.4s;
}
.hist-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-faint);
  margin-top: 4px;
}
</style>
