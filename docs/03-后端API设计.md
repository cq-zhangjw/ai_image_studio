# 03 · 后端 API 设计

> 版本：v0.1 · 2026-10-21
> Base URL：`http://127.0.0.1:8000`；所有接口默认 `application/json`；SSE 接口为 `text/event-stream`。

## 0. 通用约定

- 时间：`created_at` / `finished_at` 为 ISO8601 字符串（本地时区）。
- 图片路径：统一以 `/api/outputs/<stamp>/<file>` 形式提供，前端直接 `<img src>`。
- 任务 ID：`task_<16位hex>`。
- 响应错误统一：`{"detail": {"code": "...", "message": "..."}}`。

## 1. 健康与模型状态

### 1.1 GET /api/health
存活探针。返回 `{"status": "ok", "version": "0.1.0"}`。

### 1.2 GET /api/models
模型与 GPU 实时状态。

```json
{
  "models": [
    {"id": "qwen-image-2.1", "name": "Qwen-Image-2.1", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "ernie-image", "name": "ERNIE-Image Turbo", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "lumina-image-2.0", "name": "Lumina-Image 2.0", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "moss-image-sft", "name": "MOSS-Image SFT", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "flux2-klein-4b", "name": "FLUX.2 [klein] 4B", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "z-image-turbo", "name": "Z-Image Turbo", "status": "ready", "loaded": false, "load_seconds": null},
    {"id": "sana-sprint-1.6b", "name": "SANA-Sprint 1.6B", "status": "ready", "loaded": false, "load_seconds": null}
  ],
  "gpu": {
    "available": true,
    "name": "NVIDIA GeForce RTX 3080",
    "total_mb": 20480,
    "used_mb": 2480,
    "percent": 12.1,
    "max_allocated_mb": 19535
  },
  "last_stats": {
    "elapsed_seconds": 46.2,
    "steps_per_second": 2.21,
    "model_load_seconds": 21.0
  }
}
```
说明：`status`：`ready`（可加载）/`loading`/`loaded`；模型懒加载，前端轮询本接口（5s）。

## 2. 任务接口

### 2.1 POST /api/tasks/text-to-image
文生图。

请求体：
```json
{
  "prompt": "夏日冰饮节海报，主标题“夏日冰饮节”……",
  "negative_prompt": "blurry, low quality, watermark",
  "width": 1024,
  "height": 1536,
  "num_inference_steps": 20,
  "seed": 2026
}
```
响应：`{"task_id": "task_xxx", "status": "queued", "queue_position": 0}`

参数校验：
- `width/height` ∈ [256, 2048]，且宽高比必须在 util `ASPECT_RATIOS` 允许集合内（或倍数）；
  为降低首版复杂度，**宽高比由前端映射为合法组合**，后端校验 `width*height ≤ 4_000_000`。
- `num_inference_steps` ∈ [1, 100]；`seed` 可空（服务端随机）。

### 2.2 POST /api/tasks/edit
图像编辑（支持画圈标注 / 分离 mask / 直接描述）。

请求：`multipart/form-data`
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| prompt | str | ✅ | 编辑意图（中文/英文均可） |
| image | file | ✅ | 原图（png/jpg/webp ≤20MB） |
| mark | file | 否 | 画圈/涂鸦标注图（与 mask 二选一或同传） |
| mask | file | 否 | 分离 mask（白=编辑区） |
| annotation_style | str | 否 | `circle` / `paint` / `mask`，默认 `circle` |
| num_inference_steps | int | 否 | 默认 24 |
| seed | int | 否 | 可空 |
| composite | bool | 否 | 区域合成保真，默认 true |
| feather | int | 否 | 羽化半径，默认 20 |

响应：`{"task_id": ...}`（同 2.1）

### 2.3 POST /api/tasks/outpaint
图像扩图。

请求：`multipart/form-data`
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| image | file | ✅ | 原图 |
| prompt | str | 否 | 扩展区域内容描述；缺省由服务端按方向自动拼接 |
| target_ratio | str | ✅ | `16:9` / `9:16` / `1:1` / `4:3` / `3:4` |
| direction | str | 否 | `left`/`right`/`up`/`down`/`all`，默认 `right` |
| fill | str | 否 | `white`/`gray`/`edge`，默认 `edge` |
| num_inference_steps | int | 否 | 默认 20 |
| seed | int | 否 | 可空 |

### 2.4 POST /api/tasks/upscale
单张放大（Real-ESRGAN）。

请求：`multipart/form-data`
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| image | file | ✅ | 原图 |
| engine | str | 否 | 仅 `realesrgan`（默认） |
| scale | int | 否 | `2`（默认）/ `3` / `4` |

> 说明：SeedVR2 与文件夹批量放大（`/api/tasks/upscale-folder`）已移除，放大仅保留 Real-ESRGAN 单张模式。

### 2.6 GET /api/tasks/{task_id}
任务详情。
```json
{
  "id": "task_xxx",
  "type": "text-to-image",
  "status": "running",
  "progress": {"step": 12, "total": 20, "phase": "sampling", "percent": 60},
  "message": "正在采样…",
  "outputs": [],
  "elapsed_seconds": 30.1,
  "steps_per_second": 1.9,
  "model_load_seconds": 21.0,
  "error": null,
  "created_at": "2026-10-21T19:30:00",
  "finished_at": null
}
```
`status` ∈ `queued | running | succeeded | failed | cancelled`。

### 2.7 GET /api/tasks/{task_id}/events（SSE）
事件流（sse-starlette）。事件格式：

```
event: progress
data: {"step": 12, "total": 20, "percent": 60, "phase": "sampling"}

event: status
data: {"status": "succeeded", "outputs": ["/api/outputs/20261021_193000/output_01.png"],
       "elapsed_seconds": 46.2, "steps_per_second": 2.21, "model_load_seconds": 21.0}

event: done
data: {"task_id": "task_xxx"}
```

### 2.8 GET /api/tasks?limit=20&status=
最近任务列表（倒序）。返回 `{"tasks": [TaskDetail...]}`。

## 3. 历史输出

### 3.1 GET /api/outputs?limit=50
按时间倒序的产物目录列表：
```json
{"runs": [
  {"stamp": "20261021_193000",
   "path": "/api/outputs/20261021_193000",
   "images": ["output_01.png", "output_02.png"],
   "prompt": "夏日冰饮节……（input_prompt.txt 前 200 字）",
   "created_at": "2026-10-21T19:30:00"}
]}
```

### 3.2 静态资源
- `GET /api/outputs/{stamp}/{filename}`：图片文件（挂载 `outputs/` 目录）。
- `GET /api/outputs/{stamp}/input_prompt.txt`：prompt 记录文本。

## 4. 前端对接示例

```ts
// 提交文生图
const res = await fetch('/api/tasks/text-to-image', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({prompt, width, height, num_inference_steps, seed})
});
const { task_id } = await res.json();

// 订阅进度
const es = new EventSource(`/api/tasks/${task_id}/events`);
es.addEventListener('progress', e => updateProgress(JSON.parse(e.data)));
es.addEventListener('status', e => { const d = JSON.parse(e.data); if (d.status==='succeeded') showResult(d.outputs); es.close(); });
```
