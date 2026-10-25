"""提示词优化 LLM 封装：llama.cpp GGUF 子进程推理（用户封装 guff_util）。

供后端 llm_service 调用。底层为 llama-cli.exe + Qwen3.8-9B GGUF（utils/guff_util.py），
每次推理为独立子进程：不驻留显存、与图像模型天然共存（无需卸载策略）。
用法：
    opt = PromptOptimizer()
    out = opt.optimize("夏日冰饮节海报", target_model="auto")
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Union

from utils import guff_util  # 用户封装：llama-cli 子进程 GGUF 推理（同包）

# target_model -> 模板偏好描述（决定优化输出风格）
TARGET_PREFS = {
    "auto": "中文主体描述 + 英文风格关键词，海报场景强调版式与可读文字",
    "qwen-image-2.1": "中英混合，海报场景强调版式、构图与可读文字（该模型文字渲染强）",
    "z-image-turbo": "中英混合，强调中文/英文标题文字可读性与商业设计感",
    "flux2-klein-9b": "纯英文为主，细节尽量充分（该模型无 prompt upsampling，描述即一切）",
    "sana-sprint-1.6b": "英文为主，简洁明确，避免复杂文字要求（该模型文字渲染弱）",
}

SYSTEM_TEMPLATE = """你是专业的 AI 图像生成提示词优化器。请将用户描述直接扩写为可用于扩散模型的详细提示词并输出结果：严格保留用户核心意图与主体，补充主体外观动作、场景环境、光线氛围、构图布局、艺术风格、色彩基调、镜头语言、质感纹理等细节，输出 120-220 词的一段连贯文字，不加任何前缀。目标模型偏好：{pref}"""


RANDOM_SYSTEM_TEMPLATE = """你是专业的 AI 图像提示词创意生成器，面向「图片展示网站」的每日一图栏目。请根据分类与约束直接生成一条全新、有创意的图像生成提示词并输出结果：分类 {category}，风格倾向 {style}；每次生成明显不同避免套路化，可在主体、场景、光线、构图、色彩、质感上大胆组合；{text_rule}；输出一段连贯中文描述（80-180 字），包含主体、场景、光线、构图、色彩基调与风格细节，不加任何前缀；若画面需要文字则明确写出文字内容并强调清晰、准确、可读。"""

# 布局 JSON（高密度文字海报）模板：输出给 MOSS-Image 的布局提示词
LAYOUT_SYSTEM_TEMPLATE = """你是专业的 AI 海报布局规划器。用户给出海报需求，你输出 MOSS-Image 模型可读的「布局 JSON 提示词」，精确控制每个文字/元素的位置。
规则：
1) 输出必须是合法的 JSON 对象，不要 markdown 代码块、不要任何额外文字。
2) 结构：{"summary": {"caption": "整体场景/风格一句话"}, "items": [{"label": "text", "caption": "该框视觉样式", "text": "框内渲染的文字", "bbox": [x1, y1, x2, y2]}]}
3) label 取值："text"（渲染文字的框，text 必填）或 "element"（纯元素/装饰框，如图标、箭头、分隔线）。
4) 坐标：中心归一化像素坐标，画布 896×1216 → x 范围 [-448, 448]、y 范围 [-608, 608]（画布中心为原点，左上为负）；bbox=[x1,y1,x2,y2] 为左上角/右下角，必须 x1<x2、y1<y2。
5) 布局规范：大标题用横贯顶部的宽框；多个模块用不重叠的矩形卡片框（可左右两列或网格排布）；文字过长用 \n 手动拆行；可加底部三栏/侧栏。
6) 必须完整覆盖用户描述中的标题、全部模块/要点；caption 描述框内样式（颜色、加粗、字号、圆角等），元素框 caption 描述其外观。
7) 框不得相互重叠、不得超出画布边界；留出合理间距。"""


def _extract_layout_json(raw: str) -> str:
    """从 LLM 输出中容错提取布局 JSON，并做基本结构校验。"""
    import json

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"LLM 未输出 JSON 布局：{raw[:120]!r}")
    body = raw[start : end + 1]
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"布局 JSON 解析失败：{e}") from e
    if not isinstance(data, dict) or "items" not in data or not isinstance(data["items"], list):
        raise ValueError("布局 JSON 缺少 items 数组")
    for it in data["items"]:
        if not isinstance(it, dict) or "label" not in it or "bbox" not in it:
            raise ValueError("布局 item 必须含 label 与 bbox")
        if it["label"] == "text" and not it.get("text"):
            raise ValueError("text 类 item 必须含 text 内容")
    # 校验 bbox 边界（896×1216 画布）
    for it in data["items"]:
        x1, y1, x2, y2 = it["bbox"]
        if not (x1 < x2 and y1 < y2):
            raise ValueError(f"bbox 非法（需 x1<x2 且 y1<y2）：{it['bbox']}")
        if x1 < -448 or x2 > 448 or y1 < -608 or y2 > 608:
            raise ValueError(f"bbox 超出画布 896×1216：{it['bbox']}")
    return json.dumps(data, ensure_ascii=False)


class PromptOptimizer:
    """提示词优化器：llama.cpp GGUF 子进程推理（guff_util）。

    - 子进程模式：构造即就绪（loaded=True）、unload() 为空操作、不驻留显存；
    - 与图像模型天然共存：llm_service.should_unload_for 应返回 False（见 llm_service）。
    """

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        max_new_tokens: int = 256,
        temperature: float = 0.7,
    ) -> None:
        # model_path 由 guff_util 内部固定路径决定；保留参数以兼容旧调用
        self.model_path = str(model_path) if model_path else "llama-cpp (guff_util)"
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self._load_time_seconds: Optional[float] = None
        self._ready = True

    # ------------------------------------------------------------------ #
    def _complete(
        self,
        system: str,
        user: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """llama.cpp 子进程推理：纯文本任务指令格式（实测指令跟随最佳）。"""
        prompt_text = (
            f"{system}\n"
            f"用户输入：{user}\n"
            f"请直接输出结果，不要复述或引用任何规则。"
        )
        t0 = time.perf_counter()
        result = guff_util.run_llama_cpp(
            max_token=max_new_tokens or self.max_new_tokens,
            prompt=prompt_text,
            reasoning=False,
        )
        self._load_time_seconds = max(self._load_time_seconds or 0, time.perf_counter() - t0)
        return result.strip()

    # ------------------------------------------------------------------ #
    def _load(self):
        """兼容旧调用：子进程模式无需预加载。"""
        if self._ready:
            return None
        self._ready = True
        return None

    def unload(self) -> None:
        """子进程模式：无驻留显存，空操作。"""
        self._ready = False

    @property
    def loaded(self) -> bool:
        return self._ready

    @property
    def load_time_seconds(self) -> Optional[float]:
        return self._load_time_seconds

    # ------------------------------------------------------------------ #
    def optimize(
        self,
        prompt: str,
        target_model: str = "auto",
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        layout: bool = False,
    ) -> dict:
        """优化提示词。

        layout=True 时返回「布局 JSON 提示词」（MOSS 高密度文字海报用）：
        返回 {"optimized": str(json), "elapsed_seconds": float, "layout": True}
        """
        if layout:
            system = LAYOUT_SYSTEM_TEMPLATE
            max_new_tokens = max_new_tokens or 1600
            temperature = temperature if temperature is not None else 0.5
        else:
            pref = TARGET_PREFS.get(target_model, TARGET_PREFS["auto"])
            system = SYSTEM_TEMPLATE.format(pref=pref)

        t0 = time.perf_counter()
        result = self._complete(system, prompt, max_new_tokens, temperature)
        elapsed = time.perf_counter() - t0
        if layout:
            result = _extract_layout_json(result)
            return {"optimized": result, "elapsed_seconds": round(elapsed, 2), "layout": True}
        return {"optimized": result, "elapsed_seconds": round(elapsed, 2)}

    @staticmethod
    def gpu_memory_info() -> str:
        """llama.cpp 子进程显存：进程运行期间占显存，结束后释放；返回进程名说明。"""
        return "llama-cli.exe (subprocess, transient VRAM)"

    # ------------------------------------------------------------------ #
    def random_generate(
        self,
        category: str = "landscape",
        style: str = "",
        with_text: bool = False,
        temperature: Optional[float] = 0.9,
        max_new_tokens: Optional[int] = None,
    ) -> dict:
        """AI 随机生成一条创意提示词（面向图片网站每日一图）。

        返回 {"prompt": str, "elapsed_seconds": float}
        """
        text_rule = (
            "画面需要包含清晰可读的文字（标题或标语，如品牌名/活动名），文字内容请具体给出，并强调排版美观。"
            if with_text
            else "画面不要包含任何文字。"
        )
        system = RANDOM_SYSTEM_TEMPLATE.format(
            category=category, style=style or "随机探索", text_rule=text_rule
        )
        user = f"分类：{category}；风格倾向：{style or '不限'}。请生成一条每日一图提示词。"

        t0 = time.perf_counter()
        result = self._complete(system, user, max_new_tokens, temperature)
        elapsed = time.perf_counter() - t0
        return {"prompt": result, "elapsed_seconds": round(elapsed, 2)}
