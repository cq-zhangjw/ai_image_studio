# docs/18 · MOSS-Image-SFT 集成（2026-10-23）

## 背景与选型
ERNIE-Image 集成（docs/17）受制于：①网络（hf-mirror 大文件 xet CAS 401 故障，官方/INT8/FP8 全部不可达）；②速度（BF16 offload 8 分钟/张）。经评估后引入 **MOSS-Image-SFT**：

- **OpenMOSS-Team/MOSS-Image-SFT**（Apache 2.0）：5B DiT（42 层，dense）+ **Qwen3.5-9B 文本编码器** + FLUX.2 VAE
- 核心卖点：**原生 JSON 布局控制**（画框指定文字/元素位置）+ 强中英文本渲染，4K tokens 提示词
- 下载渠道：**ModelScope `OpenMOSS/MOSS-Image-SFT`（国内直下）**——hf-mirror 故障期间的可靠路径
- 仓库 27.23GB（十进制）≈ 25.4GiB；标准 diffusers 结构 + 自定义 pipeline（MOSSImagePipeline/MOSSImageTransformer/MOSSImageScheduler 定义在仓库内 pipeline_moss_image.py）

## 依赖评估（结论：零新增，不影响既存功能）
- pipeline 源码声明依赖：`torch>=2.9`（2.11 ✓）、`diffusers>=0.38`（0.41.0 ✓）、`transformers>=5.3`（5.20.2 ✓）、safetensors/accelerate/Pillow（✓）
- 组件均为标准 API（AutoencoderKLFlux2 / AutoModel / AutoTokenizer / DiffusionPipeline 基类）
- modelscope 1.40.2 已有（用于下载）
- **唯一新增参数**：`trust_remote_code=True`（自定义 scheduler/transformer 类在仓库内，需本地执行）
- Qwen3.5-9B 的 `causal_conv1d` / `flash-linear-attention` 未装：transformers 自动回退参考实现（慢但正确），**不安装**

## 改动清单
| 文件 | 改动 |
|---|---|
| `tools/build_moss_pipeline_local.py` | 新增：从官方 pipeline_moss_image.py 生成注入版（加 `callback_on_step_end(step,total)` 进度钩子） |
| `utils/moss_pipeline_local.py` | 新增：注入版 pipeline（签名 + 循环体各 +1 行） |
| `utils/moss_util.py` | 新增：MossImageUtil（照 ernie_util 模板；from_pretrained + bf16 + enable_model_cpu_offload + vae_slicing/tiling；加载时自动用注入版覆盖模型目录内 pipeline 文件） |
| `backend/app/services/moss_service.py` | 新增：get_util/is_loaded/unload/text_to_image（照 ernie_service） |
| `backend/app/config.py` | `MOSS_MODEL_DIR = models/MOSS-Image-SFT` |
| `backend/app/schemas.py` | model pattern 加 `moss-image-sft` |
| `backend/app/routers/tasks.py` | 分发：moss 分支（先 unload qwen/flux/z/sana/ernie） |
| `backend/app/routers/models.py` | 模型列表加 moss-image-sft |
| `backend/app/services/llm_service.py` | `_CONFLICT_MODELS` 加 moss-image-sft |
| 前端 ModelSelector.vue | OPTIONS 加 MOSS-Image SFT |
| 前端 TextToImageView.vue | 随机提示词中文分支 + 默认步数 30 + MODEL_IDS |
| 前端 HomeView.vue | 模型筛选加 MOSS-Image + 路径识别 |

## 显存策略
- 全量 bf16 27.2GB → 20G 卡 **cpu_offload**（pipeline 内置 `model_cpu_offload_seq = text_encoder->transformer->vae`）
- 与 qwen-image/z-image/seedvr2/ernie 互斥驻留（_CONFLICT_MODELS），LLM 切换时卸载
- 后续提速路径（未实施）：DiT int8（5.4GB）+ TE 4bit（7.3GB）≈ 12.7GB 全载 GPU

## 测试履历（docs/18）
| 时间 | 项 | 结果 |
|---|---|---|
| 2026-10-23 | 冒烟 512² 8 步（seed 42，红苹果） | ✅ 加载 10.8s；推理 13s（~1.7s/步）；stddev 64；进度回调正常；产物 `outputs/20261023_134233/output_01.png` |
| 2026-10-23 | 中文模块化海报 896×1216 20 步（docs/17 §4 模板） | ✅ 80s（2.5s/步，快于 ERNIE 6 倍）；产物 `outputs/20261023_140318/output_01.png`；**用户反馈"差点儿意思"（布局/排版待改进，可后续用 JSON 布局控制重测）** |
| 2026-10-23 | 随机 10 组（AI 提示词 10 分类各 1，MOSS 排队生成） | ✅ 10/10 成功；单张 55-101s；产物 `outputs/20261023_183744~184748`（10 目录）；履历见 `_moss_rand_results.json` |
| 2026-10-23 | 布局 JSON 高密度海报（docs/17 §4 内容，bbox 坐标精确控制） | ✅ 88.5s；产物 `outputs/20261023_185540/output_01.png`；用户确认"看到了，还是有点儿瑕疵" |
| 2026-10-23 | 布局海报 4 变体对比（30 步：基准/手动换行/精简caption+大框/精简caption+箭头） | ✅ 4/4 成功 88-112s；产物 `outputs/20261023_191033~191508`；**用户反馈"整体还不错，少许错别字，也有完全没问题的"** |
| - | 量化提速（int8 DiT + 4bit TE） | 待实施 |

## 已知事项
- from_pretrained 加载时 transformer 组件类型来自 diffusers 动态模块缓存（`diffusers_modules.local.pipeline_moss_image`）与本 util 导入的 `utils.moss_pipeline_local` 为两个类定义 → 仅 isinstance 检查 warning，**不影响推理**（冒烟已证）
- 模型目录内 `transformer/pipeline_moss_image.py` 为 ModelScope 镜像冗余文件（不影响加载）
- ERNIE-Image 集成代码保留（docs/17），模型权重待网络恢复后可重下；工作台模型列表两者并存

---
## 现状更新（2026-10-24）
- SeedVR2 已从项目整体移除；本文件中的 seedvr2 互斥描述仅作当时语境参考。
- MOSS-Image-SFT 已集成完毕（当前 models/MOSS-Image-SFT），工作台可选。
