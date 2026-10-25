# 29 - GGUF 引擎前端进度显示（v1.3.3）

> 状态：已实施 · 日期：2026-10-25 · 关联：docs/26（sd.cpp GGUF 集成）、docs/28（FLUX.2 9B）

## 1. 背景

- GGUF 引擎为 sd-cli 子进程，此前任务进度只在完成时从 0% 跳到 100%（`_run_cli` 完成后回调 `(total,total)`），长任务（多图融合 ~5 分钟）无任何中间反馈。
- 目标：真实采样进度 + 中途预览图，让用户在等待期间看到生成过程。

## 2. 方案

两层组合（一套进度 UI，preview 为可选字段）：

| 层 | 机制 | 说明 |
| --- | --- | --- |
| **真实步数** | 解析 sd-cli stdout 采样进度行 `| 3/20 - 2.01s/it` | 每步一行的进度条带 `s/it` 后缀，用正则 `(\d+)/(\d+)\s+-\s+[\d.]+\s*s/it` 提取；用后缀区分模型加载条（`72/397 - 1.32GB/s`） |
| **中途预览图** | sd-cli `--preview vae --preview-interval N` | 每 N 步落一张 `output_preview_%03d.png`；后台线程轮询新文件，回调携带 preview 路径 |

- 自适应：步数 `>= 12` 才启用 preview（interval = `max(2, steps//5)`，20 步 → 每 4 步 1 张，共 5 张）；短任务（<12 步，如 4 步融合）不启用，避免 VAE 解码开销拖慢短任务。
- 前端一套组件两种形态：progress 事件带可选 `preview_url`，有则显示实时预览图 + `采样 N/M · P%`，无则维持占位/纯进度。

## 3. 数据链路

```
sd-cli stdout 采样行 / preview 文件落盘
  → SdCppUtil._run_cli 逐行解析 → progress_callback(step, total)
  → generate 监控线程 → progress_callback(est_step, total, preview_path)
  → service._cb wrapper → task.set_progress(step, total, "sampling", preview_url=path)
  → TaskInfo.progress.preview_url → SSE progress 事件（web path）
  → stores/task.ts onProgress 透传 → TextToImageView / EditImageView 运行中区
```

## 4. 变更清单

**后端**：

```
utils/sd_cpp_util.py                # _RE_SAMPLING_STEP 正则；_run_cli 逐行解析回调真实 step；
                                    # generate 启动 preview 监控线程（新文件→回调带路径）
backend/app/schemas.py              # TaskProgress 加 preview_url 可选字段
backend/app/task_manager.py         # set_progress 支持 preview_url
backend/app/routers/tasks.py        # SSE progress 事件 data 加 preview_url（_to_web_paths 转换）
backend/app/services/qwen_service.py   # _cb 支持 preview；调用处传自适应 preview_interval
backend/app/services/flux2_service.py  # 同上（文生图/编辑）
```

**前端**：

```
frontend/src/types/index.ts         # TaskProgress 加 preview_url
frontend/src/api/client.ts          # SSE onProgress 类型加 preview_url
frontend/src/stores/task.ts         # onProgress 透传 preview_url
frontend/src/views/TextToImageView.vue  # 运行中区：有 preview_url 显示实时预览图 + 采样 N/M · P%
frontend/src/views/EditImageView.vue    # 同上
```

## 5. 实测（RTX 3080 20G，qwen-image-2.1，768²@20 步，interval=4）

- 采样进度逐级上报：1/20 → 20/20（5% → 100%），模型加载期无假进度；
- preview 事件 5 次（step 4/8/12/16/20），`preview_url=/api/outputs/<stamp>/output_preview_00N.png` 可直接访问（200, image/png）；
- 终态：status succeeded，产物有效 PNG，elapsed 35.16s（预览 VAE 解码开销约 +2~3s）；
- 前端轮询显示运行中卡片真实百分比（80% 截图确认），任务完成自动回传最终图，无回归。

## 6. 已知限制

- preview 模式仅 GGUF 引擎（qwen/flux2）启用；diffusers 系（ernie/lumina/moss/z-image/sana）仍为既有分步回调，未受影响。
- preview 文件随批次保留（gitignore 的 outputs/），不额外清理；批量图片生成（--batch-count>1）时 preview 序号会跨批次继续递增，回调 step 估算基于序号，可能略跳（本项目单图生成，无影响）。
- 完成时 `_run_cli` 的 `(total,total)` 回调会清空 preview_url（任务已完成，前端显示最终图，无碍）。
