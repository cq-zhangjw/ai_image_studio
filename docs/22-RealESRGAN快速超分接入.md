# 22-Real-ESRGAN 快速超分接入

> 日期：2026-10-24
> 范围：工作台放大功能新增"Real-ESRGAN 快速超分"引擎（ncnn-vulkan，秒级，不占 CUDA）
> 状态：已交付（exe 直测 + util 直连 + API 全链路验证通过）

## 一、背景

- 用户询问"是否方便引入 Real-ESRGAN 进行放大"。
- 探查发现 `E:\my_projects\ai-image-service` 已有完整现成包：`plugins/realesrgan/`（Windows exe + Linux 版 + vcomp140 dll + 6 套模型），且该服务的 `flux2_klein.py` 放大已在用它（`scale_up_x4` → realesrgan-x4plus）。
- 方案：复制二进制包到本项目 `vendor/realesrgan`，subprocess 调用，**零新增 Python 依赖**（Vulkan 推理，不吃 CUDA 显存，自带 tile 分块 `-t`）。

## 二、实现

### 二进制与模型（vendor/realesrgan）
- `realesrgan-ncnn-vulkan.exe`（Win）/ `realesrgan-ncnn-vulkan`（Linux）+ vcomp140(d).dll
- models：`realesr-animevideov3-x2/x3/x4`、`realesrgan-x4plus`、`realesrgan-x4plus-anime`

### utils/realesrgan_util.py（RealESRGANUtil）
- `upscale_image(image, scale=4, tile_size=0, output_dir, progress_callback)` → `{"run_dir","record","images"}`
- 3 阶段进度回调：sampling（1/3）→ saving（2/3）→ 完成
- 输出约定与 seedvr2_util 一致：`outputs/<YYYYMMDD_hhmmss>/output_01.png` + `input_prompt.txt`（含引擎/模型/倍数/尺寸/耗时）

### 关键坑：模型倍数
- 官方 `animevideov3-x2/x3` 的 param 是"内部 4x + 末尾 Resize 缩回 2x/3x"；实测 **ncnn-vulkan 忽略末尾 Resize 层 → 实际恒输出 4x**（512 输入 → 2048 输出）。
- 解决方案：**统一用 `realesrgan-x4plus`（写实 4x）**，2x/3x = 4x 超分输出 LANCZOS 缩到目标尺寸（细节更丰富）。

### 后端接入
- `upscale_service.py`：新增 `upscale_image_realesrgan()`（scale 2/3/4、tile_size 0=自动、进度换算 percent）
- `tasks.py`：`/api/tasks/upscale` 新增 `engine` 字段（`seedvr2` 默认 / `realesrgan`），分发时 engine=realesrgan → 快速超分分支；engine 校验（非法值 400）
- 前端 `UpscaleView.vue`：新增"放大引擎"选择（SeedVR2 修复放大 / Real-ESRGAN 快速超分）；realesrgan 模式显示"倍数 2x/3x/4x"，SeedVR2 模式保持目标面积/2x(tile)/DiT offload

## 三、测试履历

| 用例 | 输入 | scale | 结果 |
| --- | --- | --- | --- |
| exe 直测 x4plus | 1024×1024 橘猫 | 4x | ✅ 4096×4096 |
| exe 直测 animevideov3-x2 | 512×512 灰块 | 2x | ⚠️ 输出 2048（4x）→ 定位 param Resize 失效，弃用该模型 |
| util 直连 x4plus | 1024×1024 | 2x | ✅ 2048×2048（4x 后 LANCZOS 缩） |
| API 全链路 engine=realesrgan scale=2 | 1024×1024 | 2x | ✅ 2048×2048，4.99s |
| API 全链路 engine=realesrgan scale=4 | 1024×1024 | 4x | ✅ 4096×4096，5.07s |

- 画质：2x/4x 输出与原图缩略对比无伪影/无变形；4x 真实分辨率细节清晰
- 速度：**~5s/张**（对比 SeedVR2 单图 7-9 分钟，快约 100 倍），Vulkan 引擎不吃 CUDA 显存

## 四、备注 / 建议
1. Real-ESRGAN = 纯超分（增强清晰度/纹理），SeedVR2 = 修复级放大（生成缺失细节）。工作台保留两者：**快速超分选 Real-ESRGAN，修复级/大幅提升细节选 SeedVR2（tile 模式）**
2. animevideov3-x2/x3 模型当前被跳过（param 兼容问题）；如后续需要"动漫 4x 专用"，可加 animevideov3-x4 / x4plus-anime 选项（同样 4x 原生）
3. 大图（如 3840×2160）Real-ESRGAN 用 `-t` 自动分块，无需担心显存

---
## 现状更新（2026-10-24）
- SeedVR2 已整体移除：放大引擎仅保留 Real-ESRGAN（单张模式），`/api/tasks/upscale-folder` 与文件夹批量已删除。
- 二进制已从 `vendor/realesrgan` 移至 `models/realesrgan`，`utils/realesrgan_util.py` 对应更新。
- 前端放大页：引擎固定 Real-ESRGAN，倍数 2x/3x/4x（默认 2x），结果区支持原图/放大图左右滑块对比。
