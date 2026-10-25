# 27 - 提示词优化 LLM GGUF 化（llama.cpp + guff_util 集成）

> 状态：已实施并发布（v1.3.1） · 日期：2026-10-25 · 关联：docs/06（提示词优化功能设计）、docs/26（sd.cpp GGUF 集成）

## 1. 背景

- **显存压力**：提示词优化 LLM 原为 transformers 驻留式推理（Qwen3.5-4B-Instruct，BF16 ~8GB）。与图像模型共存需复杂的卸载策略（docs/06 §3），且与项目内 transformers 版本存在冲突风险。
- **前置**：Qwen-Image-2.1 已切 stable-diffusion.cpp GGUF（docs/26），验证了 GGUF + 子进程方案在本机（3080 20G）可行、显存友好。
- **本次目标**：提示词优化接口（`/api/prompt/optimize`、`/api/prompt/random`）改为 llama.cpp 子进程推理（用户封装 `utils/guff_util.py`），**零显存驻留、与图像模型天然共存、移除 transformers 推理路径**。

## 2. 方案

| 项 | 结论 |
|---|---|
| 推理引擎 | **llama-cli.exe**（llama.cpp CUDA 版，子进程一次性推理） |
| 文本模型 | **Qwen3.8-9B-Q6_K.gguf**（7.04GB，`models/gguf/`） |
| 封装层 | `utils/guff_util.py`（用户封装：`run_llama_cpp(max_token, prompt, reasoning)`） |
| 调用方 | `utils/llm_prompt_optimizer.py`（PromptOptimizer 接口不变，内部切换） |
| 服务层 | `backend/app/services/llm_service.py`（子进程语义） |
| 显存策略 | 无需共存矩阵：`should_unload_for` 恒 False，图像任务不卸载 LLM |

**llama-cli 关键参数**（guff_util 内固化）：

```
llama-cli.exe -m models/gguf/Qwen3.8-9B-Q6_K.gguf
  -ngl 99 -c 4096 -n <max_token> -st
  --simple-io --no-display-prompt --no-show-timings --log-disable
  --reasoning off -p <prompt>
```

## 3. 代码变更

```
utils/guff_util.py                    # 新增（用户封装，硬路径勿改）
utils/llm_prompt_optimizer.py         # PromptOptimizer 内部推理 → guff_util 子进程
backend/app/services/llm_service.py   # should_unload_for=False、ensure_ready 空操作、
                                      # unload 去 torch、model 名 → Qwen3.8-9B-GGUF (llama.cpp)
```

- `PromptOptimizer` 对外接口不变：`optimize(prompt, target_model, layout)` / `random_generate(category, style, with_text)` / `unload()` / `loaded` / `load_time_seconds` / `gpu_memory_info()`。
- `layout=True` 分支仍走 `LAYOUT_SYSTEM_TEMPLATE` + `_extract_layout_json`（容错提取 JSON）。

## 4. 踩坑记录（模型指令跟随）

| 尝试 | 结果 |
|---|---|
| `<|im_start|>` chat 模板（system+user+assistant 引导） | 模型**先复述 system 规则**再给结果 ✗ |
| 编号规则列表模板（规则 1)2)3)4)） | 复述规则 ✗ |
| **单段自然语言指令模板**（无编号、无独立"要求"段） | **直接输出结果，无复述** ✓ |
| 简洁任务指令（角色句 + 用户输入 + 输出指令） | 完美执行 ✓ |

**结论**：Qwen3.8-9B（llama.cpp 无 chat 模板直喂）对"长规则列表"倾向复述确认，对单段指令直接执行。当前 SYSTEM_TEMPLATE / RANDOM_SYSTEM_TEMPLATE 已单段化。

## 5. 实测（3080 20G，2026-10-25）

| 用例 | 延迟 | 输出 |
|---|---|---|
| optimize "夏日冰饮节海报" | ~5.5s | 干净无前缀，含主体/场景/光线/构图/文字渲染/风格 ✓ |
| random (cyberpunk) | ~5.3s | 干净无前缀，赛博朋克主题 ✓ |
| layout=True | — | JSON 输出，`_extract_layout_json` 校验（个别用例解析失败，见 §7 备注） |
| HTTP E2E `/api/prompt/optimize` | ~6.3s | 200 ✓（用户前端实测通过） |

> 延迟含 llama-cli 子进程加载（~2-4s）+ 推理。相比 transformers 驻留（秒级响应）略慢，但换取零驻留显存 + 与图像任务完全解耦。

## 6. 部署（新环境手顺）

1. 下载 llama.cpp CUDA 版（Release 含 llama-cli.exe + llama-cli-impl.dll + ggml-cuda.dll 等，~1.8GB）解压至 `llama-cpp/llama-cpp-cu124/`（目录已 gitignore，不入库）。
2. 下载 `Qwen3.8-9B-Q6_K.gguf`（7.04GB）至 `models/gguf/`（models/ 已 gitignore）。
3. `utils/guff_util.py` 内硬路径默认指向上述两处，无需修改。
4. 重启后端（venv + uvicorn 0.0.0.0:8001），无需安装任何新 Python 依赖（llama-cli 为独立可执行文件）。

## 7. 备注 / 已知限制

- `layout=True` 的 JSON 输出在个别复杂用例下解析失败（模型未严格输出合法 JSON）——保留 `_extract_layout_json` 容错，失败抛 4xx 由前端提示重试。
- llama-cli 子进程每次加载模型约 2-4s；高频调用时延迟为叠加值，如不能接受可评估常驻 llama-server（但会重新引入驻留显存，需权衡）。
- guff_util 未设子进程超时（communicate 无 timeout 参数）——极端卡死时由 HTTP 层超时兜底，后续如需可补。
