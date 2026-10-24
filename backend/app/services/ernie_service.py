"""ERNIE-Image-Turbo 推理服务封装：复用 utils.ernie_util，接入任务进度。

显存策略：FP8 权重 13.1GB，与 qwen-image(~14GB)/z-image 互斥驻留（20G 卡），
切换模型时由 tasks 层调用 unload 释放（gc + empty_cache）。
"""

import gc
import sys
from pathlib import Path
from typing import Callable, List, Optional

import torch

from .. import config

_PROJECT_ROOT = config.PROJECT_ROOT
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.ernie_util import ErnieImageUtil  # noqa: E402

_util: Optional[ErnieImageUtil] = None


def get_util() -> ErnieImageUtil:
    global _util
    if _util is None:
        _util = ErnieImageUtil(
            model_path=str(config.ERNIE_MODEL_DIR),
            output_root=config.OUTPUT_DIR,
        )
    return _util


def _cb(task, cb: Optional[Callable[[int, int], None]] = None):
    def wrapper(step: int, total: int):
        task.set_progress(step, total, "sampling")
        if cb is not None:
            cb(step, total)

    return wrapper


def is_loaded() -> bool:
    global _util
    return _util is not None and _util._pipe is not None  # noqa: SLF001


def unload() -> None:
    """卸载模型，释放显存（切换模型时调用）。"""
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


def _read_record(record_path: Path, key: str) -> Optional[float]:
    try:
        text = record_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith(f"{key}: "):
                return float(line.split(": ", 1)[1])
    except Exception:  # noqa: BLE001
        return None
    return None


def text_to_image(task) -> List[Path]:
    util = get_util()
    p = task.payload
    result = util.text_to_image(
        prompt=p["prompt"],
        negative_prompt=p.get("negative_prompt"),
        width=p["width"],
        height=p["height"],
        num_inference_steps=p["num_inference_steps"],
        seed=p.get("seed"),
        progress_callback=_cb(task),
    )
    task.elapsed_seconds = _read_record(result["prompt_record"], "elapsed_seconds")
    task.model_load_seconds = _read_record(result["prompt_record"], "model_load_seconds")
    return result["images"]
