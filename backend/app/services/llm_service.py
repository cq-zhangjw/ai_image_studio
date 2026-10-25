"""提示词优化 LLM 服务：llama.cpp GGUF 子进程推理（utils.guff_util + Qwen3.8-9B GGUF）。

显存策略（docs/06 §3）：
    - 优化请求到达时若 LLM 未加载，先卸载驻留图像模型再加载 LLM，之后 LLM 驻留；
    - 图像任务执行前由 tasks 层按 should_unload_for(model) 决定是否卸载 LLM。
"""

import gc
import sys
from pathlib import Path

import torch

from .. import config

_PROJECT_ROOT = config.PROJECT_ROOT
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.llm_prompt_optimizer import PromptOptimizer  # noqa: E402

_util: PromptOptimizer | None = None

# 与 LLM(~8GB) 无法共存的图像模型 id（其余可共存）
# llama.cpp 子进程模式：不驻留显存，无需显存共存/卸载策略（见 should_unload_for）


def get_util() -> PromptOptimizer:
    global _util
    if _util is None:
        _util = PromptOptimizer(
            model_path=str(config.LLM_MODEL_DIR),
        )
    return _util


def is_loaded() -> bool:
    global _util
    return _util is not None and _util.loaded


def should_unload_for(model_id: str) -> bool:
    """llama.cpp 子进程模式：不驻留显存，图像任务无需卸载 LLM。"""
    return False


def ensure_ready() -> None:
    """子进程模式：构造即就绪，无需预加载或卸载图像模型。"""
    get_util()


def unload() -> None:
    """卸载 LLM，释放显存。"""
    global _util
    if _util is not None:
        try:
            _util.unload()
        except Exception:  # noqa: BLE001
            pass
    _util = None
    gc.collect()
    # 子进程模式：无驻留显存，无需 empty_cache


def optimize(prompt: str, target_model: str = "auto", layout: bool = False) -> dict:
    """执行提示词优化；layout=True 返回 MOSS 布局 JSON 提示词；返回含 optimized / elapsed_seconds / model / load_seconds。"""
    util = get_util()
    result = util.optimize(prompt, target_model=target_model, layout=layout)
    out = {
        "original": prompt,
        "optimized": result["optimized"],
        "elapsed_seconds": result["elapsed_seconds"],
        "model": "Qwen3.8-9B-GGUF (llama.cpp)",
        "layout": bool(result.get("layout")),
    }
    if util.load_time_seconds is not None:
        out["model_load_seconds"] = round(util.load_time_seconds, 2)
    return out


def random_prompt(category: str = "landscape", style: str = "", with_text: bool = False) -> dict:
    """AI 随机生成一条创意提示词（面向每日一图）。"""
    util = get_util()
    result = util.random_generate(category=category, style=style, with_text=with_text)
    out = {
        "prompt": result["prompt"],
        "elapsed_seconds": result["elapsed_seconds"],
        "category": category,
        "with_text": with_text,
        "model": "Qwen3.8-9B-GGUF (llama.cpp)",
    }
    if util.load_time_seconds is not None:
        out["model_load_seconds"] = round(util.load_time_seconds, 2)
    return out
