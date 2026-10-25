# 28 - FLUX.2 klein 4B → 9B GGUF 替换（v1.3.2）

> 状态：已实施并发布（v1.3.2） · 日期：2026-10-25 · 关联：docs/26（sd.cpp GGUF 集成）、docs/27（提示词优化 LLM GGUF 化）

## 1. 背景

- FLUX.2 klein 4B（diffusers 驻留式）能力偏弱：无 prompt upsampling、细节描述不足。
- 用户 CLI 实测 9B（Q8_0 量化）效果明显更好且 3080 20G 可跑，确认替换 4B。
- 顺带：模型目录统一——FLUX.2 三件套移入 `models/gguf/`（与文本 LLM 同目录），删除 4B 模型与旧 diffusers 封装。

## 2. 变更清单

**模型文件**（`models/gguf/`，均已 gitignore）：

| 用途 | 文件 | 大小 |
| --- | --- | --- |
| FLUX.2 扩散模型 | `flux-2-klein-9b-Q8_0.gguf` | 9.29GB |
| 文本编码器（LLM） | `Qwen3-8B-Q4_K_M.gguf` | 4.68GB |
| VAE | `flux2-vae.safetensors` | 0.31GB |

**删除**：`flux-2-klein-4b-Q4_0.gguf`、`Qwen3-4B-Q4_K_M.gguf`（4B 组件）、`utils/flux2_util.py`（4B diffusers 封装）、`config.FLUX2_MODEL_DIR` 引用。

**代码**：

```
utils/sd_cpp_util.py              # KNOWN_MODEL_FILES 更新 9B；自动发现搜索 models/gguf + sd_cpp/models
utils/flux2_gguf_util.py          # 新增：Flux2KleinUtil(SdCppUtil)，默认三件套指向 models/gguf，
                                  #       llm_vision=None（FLUX 无需视觉塔）、default_cfg_scale=None
backend/app/services/flux2_service.py   # 子进程语义（同 qwen_service）：is_loaded/unload 去 torch；
                                        # edit_image 多图仅 1 张时退化为单图（健壮性修复）
backend/app/routers/models.py     # id flux2-klein-4b → flux2-klein-9b，名称 FLUX.2 [klein] 9B
backend/app/routers/prompt.py     # VALID_TARGETS 更新
backend/app/routers/tasks.py      # 校验接受新旧 id；execute_task 旧 4B 任务映射到 9B 引擎（历史兼容）
backend/app/schemas.py            # TextToImageRequest model 白名单更新
utils/llm_prompt_optimizer.py     # TARGET_PREFS key → flux2-klein-9b
frontend/*.vue（4 处）             # ModelSelector / EditImageView / HomeView / TextToImageView id 与名称
```

## 3. 架构

```
前端（flux2-klein-9b）→ /api/tasks/{text-to-image|edit} → flux2_service
   → utils/flux2_gguf_util.py（Flux2KleinUtil）
   → utils/sd_cpp_util.py（SdCppUtil.generate：-r 参考图支持文生图/单图编辑/多图融合）
   → sd-cli.exe 子进程（--diffusion-model flux-2-klein-9b-Q8_0 --llm Qwen3-8B --vae flux2-vae）
```

- 子进程零驻留显存：与 qwen 等其他模型天然共存，tasks 层互斥卸载逻辑不再生效（保留但空操作）。
- 历史任务兼容：旧 `flux2-klein-4b` 任务重试时自动映射到 9B 引擎。

## 4. 实测（RTX 3080 20G，E2E HTTP 任务，Q8_0，20 步）

| 场景 | 规格 | 耗时 | 结果 |
| --- | --- | --- | --- |
| 文生图 | 1024×1024@20 | 58.6s | succeeded，产出 1024² PNG |
| 单图编辑 | 864×1088@20（继承输入尺寸） | 115.8s | succeeded，产出含 `_input_original.png` 对比 |
| 多图融合 | 864×1088@20，3 参考图 | 290.7s | succeeded，3 张输入全部复制入批次 |

> 相比 4B（文生图 5.3s/融合 15.6s）明显变慢——9B 参数量大 + Q8 精度。前端默认步数仍为 4（TextToImageView/EditImageView），日常生成可用低步数换取速度。

## 5. 部署（新环境手顺）

1. `models/gguf/` 放置三件套（见 §2 表格，来源：`leejet/FLUX.2-klein-9B-GGUF` / `unsloth` / `Comfy-Org/Flux-2-Klein-4B`）。
2. `sd_cpp/bin/` 放置 sd-cli.exe + dll（见 docs/26 §3）。
3. 前端 `npm run build`，重启后端（uvicorn 0.0.0.0:8001）。
4. `/api/models` 应返回 `flux2-klein-9b / FLUX.2 [klein] 9B`。

## 6. 已知限制

- 9B Q8 多图融合约 5 分钟（20 步），如需提速可改 Q4_K_M 量化或降低步数（融合 4 步实测可用）。
- `flux-2-klein-9b-Q4_K_M.gguf`（5.5G）曾下载评估，未入库；若需速度优先可换用。
