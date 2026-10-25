# 30 - 历史删除跳转 & FLUX.2 9B 默认参数调整（v1.3.4）

> 状态：已实施 · 日期：2026-10-25 · 关联：docs/26（GGUF 集成）、docs/29（进度显示）

## 1. 删除历史图片后自动跳转下一组

**需求**：删除某张图片时，结果区自动跳转到下一组。

**实现**：

- `HistoryGallery` 新增 `deleted` 事件（`{stamp, image, remaining}`），删除成功后 emit；
- `TextToImageView` / `EditImageView` 监听：若删除的是**当前预览组**——
  - 组内仍有图（`remaining > 0`）→ 重选同组剩余第一张；
  - 组已删空（`remaining === 0`）→ `navHistory(1)` 自动跳下一组；
- 顺带修复：`EditImageView.navHistory` 此前可能选中无图组（删除后 `images` 为空的组仍在 modeRuns），改为循环跳过空组。

## 2. FLUX.2 klein 9B 默认参数

- 文生图 / 图像编辑默认采样步数 `4 → 20`（`TextToImageView` MODEL_STEP_DEFAULT、`EditImageView` watch 分支）；
- 种子保持默认随机（前端 0 → 不传 → 后端随机），无需改动。

## 3. 涉及文件

```
frontend/src/components/HistoryGallery.vue   # deleted 事件
frontend/src/views/TextToImageView.vue       # @deleted 处理；flux2 默认步数 20
frontend/src/views/EditImageView.vue         # @deleted 处理；navHistory 跳过空组；flux2 默认步数 20
```

## 4. 验证

- 前端 `npm run build` 通过；
- 删除 API 链路（前端连点确认删除 → `api.deleteImage` → works/gallery 双位置清理）实测正常；
- 跳转逻辑代码级确认（删除当前组 → 同组有图重选第一张 / 无图跳下一非空组）。
