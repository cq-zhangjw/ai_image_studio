# 26. stable-diffusion.cpp GGUF 集成

> 状态：已上线（v1.3.0）｜日期：2026-10-25｜引擎：stable-diffusion.cpp（sd-cli 子进程）+ GGUF 量化模型

## 1. 背景与动机

- Qwen-Image-2.1 多图融合走 diffusers 路径实测 **1665s（批次 `20261025_010213`）**，且 RTX 3080 20G 显存满载，吞吐不可用。
- 慢的根源为**输入图编码量**（多参考图时 prompt 编码 + 图像 token 数暴涨），与提示词写法无关。
- 用户提出 llama.cpp 量化思路 → 图像侧对应项目为 **stable-diffusion.cpp**（ggml 原生 C++ 引擎，与 PyTorch/diffusers 零依赖）。

## 2. 方案决策

| 候选 | 结论 |
| --- | --- |
| pip 源码编译（VS+CUDA） | 放弃：需安装 VS Build Tools + CUDA 工具链，对用户不友好 |
| sd-server.exe HTTP（预编译） | **死路**：加载模型正常，但任何生成 POST 均无日志静默退出（OpenAI `/v1/images/generations` 与 WebUI `/sdapi/v1/txt2img`、`--offload-to-cpu`/`--eager-load` 均复现） |
| **sd-cli.exe 子进程 CLI** | ✅ 采用：官方预编译 zip 免编译，全链路稳定，多参考图（`-r` 可复用）验证通过 |

**最终架构**：`SdCppUtil`（通用 GGUF CLI 推理层）→ `QwenImage21Util`（兼容层，同签名无缝替换 diffusers util）。

## 3. 组件与下载源

二进制（release `master-1005`，`sd-master-ea209db-bin-win-cuda12-x64.zip`，327.6MB）→ `sd_cpp/bin/`：

- `sd-cli.exe` / `sd-server.exe` / `ggml-cuda.dll`（324MB）/ `stable-diffusion.dll` 等

GGUF 模型 → `sd_cpp/models/`（全部走 `hf-mirror.com`）：

| 用途 | 文件 | 大小 | 来源 |
| --- | --- | --- | --- |
| Qwen 文生图/编辑/融合 | `qwen_image_2.1-Q8_0.gguf` | 7.3GB | `leejet/Qwen-Image-2.1-GGUF` |
| Qwen 视觉塔（编辑/多图参考必需） | `mmproj-Qwen3VL-8B-Instruct-F16.gguf` | 1.1GB | `Qwen/Qwen3-VL-8B-Instruct-GGUF` |
| Qwen LLM（编辑指令/视觉链路） | `Qwen3VL-8B-Instruct-Q4_K_M.gguf` | 4.8GB | 同上 |
| Qwen VAE | `qwen_image_2.1_vae_bf16.safetensors` | 644MB | `Comfy-Org/Qwen-Image-2.1` |
| FLUX.2 klein 9B（已接入服务 v1.3.2，见 docs/28） | `flux-2-klein-9b-Q8_0.gguf` + `Qwen3-8B-Q4_K_M.gguf` + `flux2-vae.safetensors` → `models/gguf/` | 9.3G+4.7G+320M | `leejet/FLUX.2-klein-9B-GGUF` / `unsloth` / `Comfy-Org/Flux-2-Klein-4B` |

> `black-forest-labs/FLUX.2-dev` gated 仓库 403 不可用；VAE 取自 Comfy-Org 仓库（gated 主仓库不可用）。

## 4. 封装架构

```
utils/sd_cpp_util.py          # 通用层 SdCppUtil
  ├─ 子进程调用 sd-cli.exe（_build_command / _run_cli）
  ├─ 组件路径自动发现（KNOWN_MODEL_FILES）/ 可配
  ├─ generate / text_to_image / edit_image：签名对齐旧 util
  ├─ 输出约定：outputs/<stamp>/ + input_prompt.txt + output_01.png + prompt_record.json
  ├─ hw 继承输入图尺寸；PIL 对象落临时文件
  └─ gpu_memory_info()：走 nvidia-smi
utils/qwen_21_gguf_util.py    # 兼容层 QwenImage21Util(SdCppUtil)
  ├─ 与原 utils/qwen_21_util.py 同名同签名（调用方零改动）
  ├─ 默认 Qwen GGUF 四件套
  ├─ 旧参数 model_path/dtype/vae_slicing/vae_tiling 保留但忽略
  └─ outpaint / precise_edit / draw_circle_mark：纯 PIL 逻辑原样移植
backend/app/services/qwen_service.py  # import 改 utils.qwen_21_gguf_util
  ├─ get_util() 不再传 model_path（GGUF 默认组件）
  ├─ is_loaded()/unload() 适配子进程模式（去 torch/_pipe 引用）
  └─ 文生图/单图编辑/多图融合/扩图全走 GGUF
```

验证脚本：`utils/test_sd_cpp_util.py`（文生图/单图编辑/多图融合/prompt_record 格式/旧签名构造全通过）。

## 5. CLI 关键参数（已查证，cli_help.txt 落盘）

```
--diffusion-model / --llm / --llm_vision / --vae
--offload-to-cpu  -p(rompt)  -H -W  --steps  --cfg-scale  --seed  -o(utput)
-r 参考图（可多次，多参考）  --image-preprocess
--preview (none|proj|tae|vae)  --preview-interval  --preview-path
```

日志判据：`[I] sampling completed, taking Xs`、`[I] generate_image completed in Xs`、`[I] preprocess ref[N]`。

## 6. 性能实测（RTX 3080 20G，均含子进程模型加载）

| 场景 | 规格 | 耗时 | 备注 |
| --- | --- | --- | --- |
| klein 4B 文生图 | 768² | 4.1s | 1024²=5.33s（已下线，4B 被 9B 替换） |
| klein 4B 多图融合 | 1024² | 15.6s | CLI 直测（已下线） |
| **Qwen 多图融合** | 1024²@20 步 | **104.2s**（采样 95.3s） | diffusers 1665s → **快 16 倍** |
| Qwen 单图编辑 | 864×1088@12 步 | 79.9s（采样 62.6s ≈ 5.2s/步） | E2E 任务 `task_631d07b3818441a3` |
| Qwen 文生图 | E2E | 15.3s | 任务 `task_901e1d673512438e` |
| **klein 9B 文生图（v1.3.2）** | 1024²@20 步 | **58.6s** | E2E，Q8_0 量化 |
| **klein 9B 单图编辑（v1.3.2）** | 864×1088@20 步 | **115.8s** | E2E |
| **klein 9B 多图融合（v1.3.2）** | 864×1088@20 步 | **290.7s** | E2E，3 参考图 |

多图参考有效性：日志 `preprocess ref[0]/ref[1]` + `Using 'qwen'/'flux2' preset for reference images` 确认 `-r` 可复用。

## 7. 前端配套改动（本轮）

- **EditImageView.vue**：多图融合素材上传由 9 格改为 **6 格（3×2）**；历史回显素材仅还原前 6 张（`si < 6`）；结果区素材预览 3 列对齐。
- **HistoryGallery.vue**：历史卡片缩略图布局重构——素材网格竖直等分（内联像素高度 `thumbStyle(n)` 按行数均分，3 张以内 1 列、>4 张 2 列），`object-fit: contain` 显示全图 + "N 张"角标。
- 结果预览：素材区垂直居中、图片点击弹窗放大（lightbox）、融合结果 10px 圆角边框。

> 调试履历：历史卡片黑图多轮修复（flex/grid 高度塌陷根因 = grid `1fr` 行 + item `height:100%` 循环依赖，Chrome 解析为 0；最终改为内联像素高度确定性布局）。`file://` 复现页加载 http 图片会被混合内容拦截，需挂 8001 同源验证。

## 8. 已知限制

- **进度回调为完成制**：sd-cli 无逐 step 文本日志，`progress_callback` 仅完成时回调 `(total, total)`；真实中途进度需 `--preview vae --preview-interval` 中途预览图轮询（性能开销待实测，被中断无结论）。
- **显存查询**：Windows 普通权限下 `nvidia-smi --query-compute-apps` 的 used_memory 列显示 `[N/A]`（Insufficient Permissions）；进程名列可见 `sd-cli.exe`（任务型子进程，任务结束即退出，不常驻）。
- sd-server HTTP 路由为死路，勿回退该方案。
- FLUX.2 klein 的 GGUF 组件已备好但**未接入服务**（`flux2_service` 仍走 diffusers）。

## 9. 环境构筑手顺（从 0 搭建）

1. 下载官方预编译 zip（见 §3）解压到 `sd_cpp/bin/`。
2. `hf-mirror.com` 下载 GGUF/VAE 组件到 `sd_cpp/models/`（文件名与 `KNOWN_MODEL_FILES` 一致即可自动发现）。
3. `pip install` 无需新增依赖（子进程方案零 torch/transformers 依赖）。
4. 启动：`cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001`。
5. 前端：`cd frontend; npm run build`（vue-tsc -b && vite build）。

## 10. 测试履历

- [x] 二进制/模型全部经 hf-mirror 下载成功
- [x] sd-cli 文生图/单图编辑/多图融合全链路（test_sd_cpp_util.py）
- [x] 后端 E2E：文生图 15.3s / 融合 104s / 单图编辑 80s
- [x] 单图编辑进程验证：nvidia-smi 可见 sd-cli.exe（PID 8640，显存 10.9G→19G）
- [x] UI：6 格融合布局、历史卡片缩略图、lightbox 放大
