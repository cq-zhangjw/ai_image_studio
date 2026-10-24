# 20-ERNIE-INT8 调试与 Lumina-Image-2.0 接入

> 日期：2026-10-24
> 范围：后端模型接入（ERNIE-Image-INT8 量化版调通 + Lumina-Image-2.0 新增）、前端模型选项同步、schemas 白名单补全
> 状态：已交付（ERNIE 已放开画面、Lumina 已跑通冒烟+API 全链路）

## 一、ERNIE-Image-INT8（22.03GB，iximbox 官方量化版）

### 1. 模型组成
- `transformer`：quanto int8（7665MB）
- `text_encoder`：bf16 Mistral3（7342MB）
- `pe`：bf16 Ministral3（7308MB）——prompt enhancer，use_pe 默认启用
- `vae`：AutoencoderKLFlux2（160MB）
- `scheduler/tokenizer/pe_tokenizer` 齐备
- 目录自带 `quantization_config.json`（format: quanto, weights: int8）

### 2. 加载方式（核心坑，已固化）
```
# 正确（唯一可行）：
ErnieImagePipeline.from_pretrained(模型目录, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()   # 20G 卡必须 offload（官方建议 24G+）
```
- **禁止显式传任何 quantization_config**：
  - `diffusers.QuantoConfig` → 报 "must be an instance of PipelineQuantizationConfig"（QuantoConfig 是 QuantizationConfigMixin，非子类）
  - `PipelineQuantizationConfig(quant_backend="quanto", quant_kwargs={"weights":"int8"})` → 报 "__init__ 签名不匹配，请提供 quant_mapping"
- diffusers 会**自动识别**目录内 quantization_config.json，transformer 走 quanto int8、text_encoder/pe 保 bf16

### 3. 实测数据（RTX 3080 20G，offload 模式）
| 项 | 结果 |
| --- | --- |
| 模型加载 | 18.8s（API 链路 19.2s） |
| 512×512 / 10 步 | 32.7s |
| 1024×1024 / 20 步 | 100.9s（API 全链路） |
| GPU 显存 | 推理后 allocated≈0 / reserved≈42MB（offload 逐模块搬移） |
| 输出质量 | 正常（橘猫/少女立绘均符合提示词，无乱码） |

### 4. 参数备忘（官方 README）
- 推荐分辨率：1024×1024 / 848×1264 / 1264×848 / 1200×896
- 官方示例：`use_pe=True`、`guidance_scale=4.0`、`num_inference_steps=50`
- 当前 `ernie_util.text_to_image` 未显式传 use_pe（默认启用），guidance 未传（走 pipeline 默认）
- 局限：中文提示词语义理解有漂移（海报提示词易生成插画风），文字排版建议配合 JSON 强化提示词

### 5. 依赖
- 新增 `optimum-quanto 0.2.7` + `ninja 1.13.2`（唯一新增，未动其他包）

## 二、Lumina-Image-2.0（31.7GB，Alpha-VLLM 官方）

### 1. 模型组成（本地 29.5GB 实测）
- `consolidated.00-of-01.pth`：9.72GB 主权重（差分包里最易漏，下载完成标志）
- `transformer/`：9.27GB + 0.45GB safetensors（diffusers 格式，shard-2）
- `text_encoder/`：9.74GB（Gemma-2-2B，safetensors 3 shard；fp32 存储，bf16 加载后 ~4.8GB）
- `vae`：AutoencoderKL；scheduler：FlowMatchEulerDiscreteScheduler
- `model_index.json`：`Lumina2Pipeline` + `Lumina2Transformer2DModel`（diffusers 0.41 原生支持，已验证）

### 2. 加载方式
```
Lumina2Pipeline.from_pretrained(模型目录, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()   # 默认开启，20G 卡稳定
```
- bf16 全载估算 14-16GB（20G 可直接跑），offload 更稳

### 3. 实测数据（RTX 3080 20G）
| 项 | 结果 |
| --- | --- |
| 模型加载 | ~24s（util 直连）/ 19.1s（API 链路） |
| 1024×1024 / 30 步 | 43.4s（1.25s/it，util 直连）/ 41.2s（API 全链路） |
| 输出质量 | 写实/插画正常；**中文文字渲染弱**（海报标题变模糊字符，已知特性） |

### 4. 接入代码
- `utils/lumina_util.py`：LuminaImageUtil（同构 ernie_util：prompt_record + output_xx.png + 耗时记录；默认 40 步、guidance 4.0、offload）
- `backend/app/services/lumina_service.py`：service 同构 qwen/moss
- `backend/app/routers/models.py`：注册 `lumina-image-2.0`（Lumina-Image 2.0）
- `backend/app/routers/tasks.py`：text-to-image 分发分支（unload qwen/flux2/z-image/sana/ernie 后转 lumina）
- 前端：`ModelSelector.vue` OPTIONS + `TextToImageView.vue`（MODEL_IDS + 默认步数 40 + 随机提示词中文分支）+ `HomeView.vue`（MODEL_FILTERS + modelFromPath 归一化）

### 5. 参数备忘（官方 demo）
- 40 步、guidance 4.0；支持 negative/width/height/seed
- 适合：写实摄影、艺术插画、动漫；不适合：高密度中文文字海报

## 三、schemas 白名单补全（本次修复）

`backend/app/schemas.py` TextToImageRequest：
- `model` pattern 追加 `lumina-image-2.0`（此前提交 lumina 任务会 422）
- `category` pattern 追加 `design|work|3d|anime`（此前前端已有 4 类但后端校验漏了，选新分类提交会 422）
- 注：旧实例需重启生效（本次已重启验证）

## 四、测试履历

| 时间 | 用例 | 模型 | 结果 |
| --- | --- | --- | --- |
| 00:02 | 冒烟 512×512/10 步 seed42 橘猫 | ERNIE-INT8 | ✅ 32.7s，图正常 |
| 00:17 | API 1024×1024/20 步 seed20261024 冰饮海报 | ERNIE-INT8 | ✅ 100.9s，图正常（少女立绘，提示词漂移） |
| 07:46 | 冒烟 1024×1024/30 步 seed42 橘猫 | Lumina | ✅ 67.6s，图正常 |
| 07:47 | API 1024×1024/30 步 seed20261024 冰饮海报 | Lumina | ✅ 41.2s，进度正常；**文字渲染弱**（模糊字符） |

## 五、遗留 / 建议
1. Lumina 中文文字弱：海报场景建议用 ERNIE（配合 JSON 强化提示词）或后续评估 Ideogram 4 / Anima（注意两者均为非商用许可）
2. 项目根 `E:\my_projects\qwen-2.1` 无 git 仓库（仅 seedvr 子目录有），提交/Tag 流程需确认仓库归属
3. docs 目录此前最新为 19，本文件为 20；config.py/prompt.py 注释中引用的 docs/21 尚未撰写（如后续有 21 需求再补）

---
## 现状更新（2026-10-24）
- 第 2 条已过时：项目根已 `git init` 并托管至 GitHub（cq-zhangjw/ai_image_studio），v1.0.0 已打 Tag。
- Lumina-Image-2.0（models/Lumina-Image-2.0）已接入工作台；docs/21（SeedVR2 tile 模式）已随 SeedVR2 移除而删除。
