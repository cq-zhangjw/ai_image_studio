<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, assetUrl } from '@/api/client'
import type { OutputRun } from '@/types'

const runs = ref<OutputRun[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await api.outputs(30)
    runs.value = data.runs
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="outputs card">
    <div class="head">
      <h3>历史输出</h3>
      <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
    </div>
    <div v-if="!runs.length" class="empty">暂无历史产物</div>
    <div v-else class="run-list">
      <div v-for="run in runs" :key="run.stamp" class="run">
        <div class="run-head">
          <span class="stamp mono">{{ run.stamp }}</span>
          <span class="count">{{ run.images.length }} 张</span>
        </div>
        <div class="run-imgs">
          <a
            v-for="img in run.images"
            :key="img"
            :href="assetUrl(`${run.path}/${img}`)"
            target="_blank"
            class="thumb"
          >
            <img :src="assetUrl(`${run.path}/${img}`)" :alt="img" loading="lazy" />
          </a>
        </div>
        <div v-if="run.prompt" class="run-prompt" :title="run.prompt">{{ run.prompt }}</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.outputs {
  max-height: 480px;
  overflow-y: auto;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.head h3 {
  margin: 0;
  font-size: 14px;
}
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
.empty {
  color: var(--text-faint);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}
.run {
  padding: 10px 0;
  border-top: 1px solid var(--border);
}
.run:first-of-type {
  border-top: none;
}
.run-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.stamp {
  font-size: 11px;
}
.run-imgs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.thumb {
  width: 64px;
  height: 64px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.run-prompt {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
