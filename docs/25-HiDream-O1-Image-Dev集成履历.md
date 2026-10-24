# 25-HiDream-O1-Image-Dev 集成履历

日期：2026-10-24
状态：已完成，业务链路验证通过，前端已放开

## 背景

用户确认模型权重已下载至 `models\HiDream-O1-Image-Dev`（8 个 safetensors，约 36GB），要求先完成图像编辑页收尾、再集成 HiDream。模型为 Pixel-level Unified Transformer（无独立 VAE/TE），官方架构 `Qwen3VLForConditionalGeneration`，Dev 参数：28 步 / guidance 0.0 / shift 1.0 / flash scheduler + DEFAULT_TIMESTEPS；≤2048×2048 直出。

## 集成动作

1. 官方仓库代码（HiDream-O1-Image-main）复制至 `backend\app\services\hidream\`，`pipeline.py` 中 `use_flash_attn: True→False`（无 flash_attn 依赖）。
2. 新建 `backend\app\services\hidream_service.py`：HiDreamUtil 持 AutoProcessor + int4 NF4 量化（bnb，compute bf16，double_quant），device_map="cuda"，eager attention；`text_to_image` 用官方 Dev 参数，按 stamp 落盘 `output_01.png` + `input_prompt.txt`。
3. `config.py` 加 `HIDREAM_MODEL_DIR`；`tasks.py` text-to-image 分发加 hidream（先 unload 其他模型）；`models.py` 注册 `/api/models` 条目；`schemas.py` TextToImageRequest.model pattern 追加 `hidream-o1-image-dev`。
4. 前端：ModelSelector.vue DEFAULT_OPTIONS + HomeView.vue MODEL_FILTERS 加 HiDream 选项，`npm run build` 通过。

## 花屏排障链（关键）

现象：生成成功（28 步跑完）但输出绿色/紫色噪点花屏。

已排除：int4 量化（bf16 对照也花屏）、attention 实现（eager/sdpa 均花屏）、采样器（flash/FlowUniPC 均花屏）、权重完整性（759 tensors ALL OK）、token 映射、输入构造（position_ids 各维非全 0 正常）、mask 格式（0/-inf 正确）、x_pred 数值（前几步正常但末步 std=1.89 发散）、@use_kernel_forward_from_hub（5.20.2 为 no-op）、dynamic_rope_update 装饰器（两版行为一致）、官方原版代码在 4.57.1 下正常出图（决定性对照）。

**根因**：transformers 5.20.2 的 `Qwen3VLTextConfig` 不再提供顶层 `rope_theta` 属性，真实值 5000000 只存在于 `rope_parameters`/`rope_scaling` 字典中。为兼容 5.x 缺失的 "default" rope 实现而注册的补丁函数使用 `getattr(config, "rope_theta", 10000.0)`，回退到 10000 → inv_freq 偏差 500 倍 → 旋转位置编码频率错误 → attention 位置信息失效 → 输出位置无关的绿色网格花屏。

**修复**：补丁函数改为优先从 `config.rope_parameters`（或 `rope_scaling`）读取 `rope_theta`，无则回退 `config.rope_theta`/10000。修复后 inv_freq 与 4.57.1 完全一致。

## 验证结果

| 项 | 结果 |
| --- | --- |
| int4 冒烟（1024 请求，吸附 2048²） | 47.8s，输出正常（橘猫戴草帽+樱花庭院） |
| 4.57.1 + 官方原版代码对照 | 42s，输出正常（同 prompt） |
| 真实业务链路 API（int4） | 47.6s，`succeeded`，落盘 output_01.png |
| UTF-8 中文 prompt 链路 | 47.6s，输出与 prompt 完全匹配（白柴犬粉色和服+樱花+石灯笼） |
| 显存占用 | int4 约 10-13GB（20G 卡余量充足），未爆显存 |

## 遗留

- 编辑/多参考（IP/layout/skeleton）能力未开放：`/api/tasks/edit` 的 model 白名单仍为 qwen-image-2.1 / flux2-klein-4b；HiDream 仅注册 text-to-image 分发。
- 参考图/编辑链路如需放开，可复用官方 generate_image 的 ref_image_paths 分支（keep_original_aspect、flow_match 等），建议另开迭代。
- 隔离对照环境 tmp_tf457（transformers 4.57.1 + tokenizers 0.22.2 + hub 0.36.2 + diffusers 0.32.0）已删除；主 venv 保持 transformers 5.20.2 不变（其余模型服务不受影响）。

---
## 现状更新（2026-10-24）
- HiDream-O1-Image-Dev 已整体移除（后端 7 处 / 前端 2 处代码、`models/HiDream-O1-Image-Dev` 约 36GB 权重、测试产物均已清理），本文件仅作排障记录保留。
- 工作台当前图像模型：Qwen-Image-2.1 / ERNIE-Image Turbo / Lumina-Image-2.0 / MOSS-Image SFT / FLUX.2 [klein] 4B / Z-Image Turbo / SANA-Sprint 1.6B。
