# 19-高密度文字布局JSON提示词功能

日期：2026-10-23
状态：已实施并验证
前置：docs/18（MOSS-Image-SFT 集成，布局 JSON 提示词能力验证）

## 需求

提示词输入框下方增加「高密度文字」复选框；勾选时，AI 提示词优化返回 **MOSS 布局 JSON 提示词**（精确 bbox 控制海报元素位置），用于多模块文字海报。

## 改动清单

### 后端
- `utils/llm_prompt_optimizer.py`
  - 新增 `LAYOUT_SYSTEM_TEMPLATE`：布局 JSON 生成规则（896×1216 画布、中心归一化坐标、text/element 两种 label、`\n` 手动换行、框不重叠不出界）
  - `optimize()` 新增 `layout: bool = False` 参数：layout 模式使用布局模板，`max_new_tokens` 默认 1600、`temperature` 0.5
  - 新增模块级 `_extract_layout_json(raw)`：容错提取 JSON（忽略 markdown 代码块等杂讯）、结构校验（items/label/bbox/text）、画布边界校验（x∈[-448,448]、y∈[-608,608]）
- `backend/app/services/llm_service.py`：`optimize()` 透传 `layout`，返回带 `layout` 标志
- `backend/app/routers/prompt.py`：`OptimizeRequest` 加 `layout: bool = False`；`VALID_TARGETS` 加 `moss-image-sft`

### 前端
- `frontend/src/api/client.ts`：`optimizePrompt` body/响应加 `layout`
- `frontend/src/components/PromptOptimizerModal.vue`：props 加 `layout`，请求透传；弹窗显示「布局 JSON 模式」徽标
- `frontend/src/views/TextToImageView.vue`：提示词框下加「高密度文字」复选框（`highDensity` ref），勾选时 AI 优化进入布局 JSON 模式；结果可编辑、可回填
  - **模型约束**：布局 JSON 仅 moss-image-sft 支持 → 复选框仅在选择 MOSS 模型时显示；优化请求 `layout` 仅在 moss 时透传（`isMoss && highDensity`）

## 验证

- 后端语法检查通过；`npm run build`（vue-tsc 严格）通过
- 8001 重启后 `/api/prompt/optimize` 端到端：`layout=true` 返回布局 JSON，耗时 30.4s（含 LLM 加载 6.5s + 生成）
- 返回样例：`{"summary":{"caption":"蓝紫渐变科技风格海报…"},"items":[{"label":"text","caption":"大标题，白色加粗…","text":"AI 分享会","bbox":[-300,-550,300,-250]},…]}`

## 已知事项

- LLM 生成偶发非纯 JSON：`_extract_layout_json` 已做容错提取与结构/边界校验，失败时返回明确错误
- 布局 JSON 提示词请配合 MOSS-Image-SFT 模型使用（其他模型不支持该格式）
