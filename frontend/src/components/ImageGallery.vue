<script setup lang="ts">
import { assetUrl } from '@/api/client'

defineProps<{
  images: string[]
  compareWith?: string | null
  compareLabels?: { left?: string; right?: string }
}>()
</script>

<template>
  <div class="gallery" :class="{ single: images.length === 1 }">
    <template v-if="compareWith">
      <figure class="cell compare">
        <figcaption>{{ compareLabels?.left ?? '原图' }}</figcaption>
        <img :src="assetUrl(compareWith)" alt="before" />
      </figure>
      <figure class="cell compare">
        <figcaption>{{ compareLabels?.right ?? '结果' }}</figcaption>
        <img :src="assetUrl(images[0])" alt="after" />
      </figure>
    </template>
    <template v-else>
      <figure v-for="(img, i) in images" :key="img" class="cell">
        <img :src="assetUrl(img)" :alt="`result ${i + 1}`" loading="lazy" />
        <a class="download" :href="assetUrl(img)" download :title="`下载结果 ${i + 1}`">⤓</a>
      </figure>
    </template>
  </div>
</template>

<style scoped>
.gallery {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.gallery.single {
  grid-template-columns: 1fr;
}
.cell {
  position: relative;
  margin: 0;
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg-elev);
  border: 1px solid var(--border);
}
.cell img {
  display: block;
  width: 100%;
  height: auto;
}
.cell.compare img {
  aspect-ratio: 1 / 1;
  object-fit: cover;
}
.cell figcaption {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(15, 20, 25, 0.75);
  font-size: 11px;
  color: var(--text);
  z-index: 1;
}
.download {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  background: rgba(15, 20, 25, 0.75);
  color: var(--text);
  text-decoration: none;
  font-size: 15px;
  z-index: 1;
}
.download:hover {
  background: var(--primary);
}
</style>
