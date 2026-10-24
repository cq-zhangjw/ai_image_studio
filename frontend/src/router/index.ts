import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/workspace',
      component: () => import('@/views/WorkspaceView.vue'),
      children: [
        { path: '', redirect: '/workspace/text-to-image' },
        { path: 'text-to-image', name: 'text-to-image', component: () => import('@/views/TextToImageView.vue') },
        { path: 'edit', name: 'edit', component: () => import('@/views/EditImageView.vue') },
        { path: 'upscale', name: 'upscale', component: () => import('@/views/UpscaleView.vue') },
        { path: 'outpaint', name: 'outpaint', component: () => import('@/views/OutpaintView.vue') },
      ],
    },
    // 旧路由兼容：重定向到工作台子页
    { path: '/text-to-image', redirect: '/workspace/text-to-image' },
    { path: '/edit', redirect: '/workspace/edit' },
    { path: '/upscale', redirect: '/workspace/upscale' },
    { path: '/outpaint', redirect: '/workspace/outpaint' },
  ],
})

export default router
