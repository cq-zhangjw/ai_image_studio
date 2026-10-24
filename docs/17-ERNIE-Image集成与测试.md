# docs/17 ERNIE-Image 集成与测试履历

> 状态：实施中（2026-10-23 启动）
> 目标：将百度开源 ERNIE-Image-Turbo（8B DiT，高密度文字/结构化布局 SOTA）集成进工作台，补齐 qwen-image 在复杂图文海报场景的短板，并完成 10 组随机提示词 + 1 组高密度海报实测。

---

## 1. 背景与选型结论

- 用户实测：qwen-image-2.1 生成"5 模块 × 多要点"分享会海报时出现模块标题错位/重复（v1 交付 https://aka.doubaocdn.com/s/MD5HNaJaCf）。
- 对比结论：Copilot 一次准确靠的是 GPT-4o 自回归"写"文字 + Designer 模板管线；本地扩散模型要补文字渲染能力，开源最优解是 **ERNIE-Image**（LTBench 文字保真 0.9733，支持中/英/日/韩）。
- 显存评估（3080 20G）：官方 bf16 标 24GB；**FP8 diffusers 版（13.1GB）20G 可全载**。
- **关键发现**：社区 `szwagros/ernie-image-turbo-fp8` 是**标准 diffusers 仓库格式**（model_index.json + scheduler/text_encoder/tokenizer/transformer/vae + ErnieImagePipeline），加载方式与现有 qwen/flux 完全一致 → 集成改动最小化。
- **依赖结论**：本机 diffusers **0.41.0 已内置 ErnieImagePipeline**（已验证），**零新增依赖**。不需要 sglang / ComfyUI / GGUF loader / bitsandbytes。
- Ampere(30系) 无 FP8 硬件加速：diffusers 加载 FP8 权重后按可用内核反量化计算，速度略降但可用（验证于测试节）。

## 2. 集成改动清单

| 文件 | 改动 |
|---|---|
| `config.py` | 新增 `ERNIE_MODEL_DIR = MODEL_ROOT / "ERNIE-Image-Turbo-FP8"` |
| `utils/ernie_util.py` | **新增**：ErnieImageUtil（from_pretrained + text_to_image，接口对齐 flux2_util） |
| `services/ernie_service.py` | **新增**：加载/卸载/进度回调/统计，照 flux2_service 模板 |
| `routers/tasks.py` | execute_task 加 `ernie-image` 分发（先 unload qwen/z-image/sana/llm） |
| `schemas.py` | TextToImageRequest.model pattern 加 `ernie-image` |
| `routers/models.py` | 模型列表加 `ernie-image` 项 |
| 前端 `ModelSelector.vue` / `TextToImageView.vue` 等 | MODEL_IDS 加 `ernie-image` |
| 前端 `types/index.ts` | 模型类型联合加 `ernie-image` |

### 显存策略
- ERNIE-Image-Turbo FP8 权重 13.1GB → 与 qwen-image(~14GB) / z-image / seedvr2 互斥；与 klein/sana 可共存（沿用 LLM 共存策略：`llm_service.should_unload_for` 判断）。
- 切换时 execute_task 统一 unload 冲突模型（gc + empty_cache）。

### ERNIE 出图参数（Turbo 版默认）
- 步数：默认 20（Turbo 蒸馏版支持更少步数，实测见履历）
- 尺寸：复用现有 DIMS（1:1 / 2:3 / 3:4 / 16:9 / 9:16）
- 提示词：中文直接可用，**结构化海报写法**见 §4

## 3. 测试计划

| # | 用例 | 数量 | 验收 |
|---|---|---|---|
| 1 | 随机提示词文生图（AI 生成提示词，覆盖多分类/尺寸） | 10 | 全部成功、无 OOM、落库作品 |
| 2 | 高密度中文海报（分享会场景，复刻 docs 海报参考图结构） | 1 | 模块标题与内容无错位、小字清晰 |

## 4. 高密度海报提示词模板（本测试用）

```
竖版活动分享会海报，卡通手绘插画风格，蓝紫渐变主色调。
顶部大标题：「AI社区×项目管理社区 实用AI use case分享会」，副标题「用AI让项目管理更高效、更简单！」。
中部五个彩色模块卡片（左列3右列2），每块含小标题+短要点+图标：
1「进度计划管理」：用Copilot快速生成进度表；
2「障碍分析」：AI引导式提问分析原因并生成报告；
3「日常办公技巧」：优化PPT、分析Excel、自动生成会议纪要；
4「Order点检」：整合PASS计划数据和SAP实际工时生成点检报告；
5「会议纪要自动化」：抓取会议记录、AI总结、自动保存并通知。
模块间箭头流程连接。底部三栏：总结价值/社区后续/下一步行动。
文字清晰准确可读，排版专业。
```

---

## 5. 测试履历（实施中填写）

| 时间 | 用例 | 模型 | 尺寸 | 步数 | 结果 | 备注 |
|---|---|---|---|---|---|---|
| (待填) | 随机×10 | ernie-image | 混合 | 20 | - | - |
| (待填) | 高密度海报×1 | ernie-image | 896×1216 | 20 | - | - |

### 已测结论（追加）
- [x] diffusers 0.41.0 内置 ErnieImagePipeline —— **已确认**
- [x] FP8 仓库结构：标准 diffusers 子目录，但 safetensors 文件名非标准，需复制标准名
- [x] `pe` 组件仓库未带权重，需从 model_index.json 移除声明
- [x] FP8 权重为 PyTorch 原生 FP8（`_data`/`_scale`），diffusers 不支持 → 需转换脚本反量化 bf16
- [x] BF16 转换版（25GB）cpu_offload 推理可用（512² 8步 45.6s / 896×1216 20步 ~8min），中文海报无乱码
- [ ] INT8 版（ixim/ERNIE-Image-INT8，23.7GB diffusers）：**2026-10-23 网络不可达**——hf-mirror 无缓存且大文件 xet CAS 401（镜像故障）、huggingface.co 直连被墙、ModelScope 无此仓库 → **下载失败，已回退清理**
- [ ] 官方 baidu/ERNIE-Image-Turbo（32GB bf16 标准结构）：可下载（hf_transfer 需 5-6min），但 32GB 权重 20G 显存仍须 offload，速度不变 → 用户权衡后放弃换仓
- [ ] **待网络恢复**：重下 FP8（12GB）→ 跑 tools/convert_ernie_fp8.py → 恢复 BF16 方案；集成代码（util/service/分发/前端）全部保留，只缺模型权重
- [ ] Kolors（ModelScope 可下 17.8GB）作为可替代主力中文文字模型 —— 待决策

---
## 现状更新（2026-10-24）
- 该文档为 ERNIE-Image 集成历史记录。SeedVR2 已从项目整体移除（代码/权重/文档），本文件中的 seedvr2 互斥描述仅作当时语境参考。
- ERNIE-Image-INT8 已下载并集成完毕（当前 models/ERNIE-Image-INT8），工作台可选。
