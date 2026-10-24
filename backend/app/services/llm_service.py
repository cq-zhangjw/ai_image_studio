"""提示词优化 LLM 服务：Qwen3.5-4B-Instruct（GPU 推理，懒加载单例）。

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
_CONFLICT_MODELS = {"qwen-image-2.1", "z-image-turbo", "ernie-image", "moss-image-sft"}


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
    """图像任务执行前判断：该模型是否需先卸载 LLM 腾显存。"""
    return is_loaded() and model_id in _CONFLICT_MODELS


def ensure_ready() -> None:
    """确保 LLM 可加载：klein/sana 驻留时可共存；qwen/z-image/ernie 驻留时先卸载。"""
    if is_loaded():
        return
    from . import qwen_service, upscale_service, z_image_service

    for svc in (qwen_service, z_image_service, upscale_service):
        if svc.is_loaded():
            svc.unload()
    get_util()  # 触发加载


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
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def optimize(prompt: str, target_model: str = "auto", layout: bool = False) -> dict:
    """执行提示词优化；layout=True 返回 MOSS 布局 JSON 提示词；返回含 optimized / elapsed_seconds / model / load_seconds。"""
    util = get_util()
    result = util.optimize(prompt, target_model=target_model, layout=layout)
    out = {
        "original": prompt,
        "optimized": result["optimized"],
        "elapsed_seconds": result["elapsed_seconds"],
        "model": "qwen3.5-4b-instruct",
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
        "model": "qwen3.5-4b-instruct",
    }
    if util.load_time_seconds is not None:
        out["model_load_seconds"] = round(util.load_time_seconds, 2)
    return out
