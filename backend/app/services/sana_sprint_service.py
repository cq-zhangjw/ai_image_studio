"""SANA-Sprint 1.6B 推理服务封装：复用 utils.sana_sprint_util，接入任务进度。

显存策略：与 qwen/flux2/z-image service 互斥驻留（切换模型时由 tasks 层 unload）。
SANA-Sprint 不支持 negative_prompt（自动忽略）；默认 2 步 / guidance 4.5。
许可证：NSCL v2-custom（NVIDIA Open Model License，研究用途；商用需审阅）。
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

from utils.sana_sprint_util import SanaSprintUtil  # noqa: E402

_util: Optional[SanaSprintUtil] = None


def get_util() -> SanaSprintUtil:
    global _util
    if _util is None:
        _util = SanaSprintUtil(
            model_path=str(config.SANA_SPRINT_MODEL_DIR),
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
    if _util is not None and _util._pipe is not None:  # noqa: SLF001
        try:
            _util._pipe = None  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    _util = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def text_to_image(task) -> List[Path]:
    util = get_util()
    p = task.payload
    result = util.text_to_image(
        prompt=p["prompt"],
        negative_prompt=p.get("negative_prompt"),  # Sprint 忽略
        width=p["width"],
        height=p["height"],
        num_inference_steps=p["num_inference_steps"],
        seed=p.get("seed"),
        progress_callback=_cb(task),
    )
    task.elapsed_seconds = _read_record(result["prompt_record"], "elapsed_seconds")
    task.steps_per_second = _read_record(result["prompt_record"], "steps_per_second")
    task.model_load_seconds = _read_record(result["prompt_record"], "model_load_seconds")
    return result["images"]


def _read_record(record_path: Path, key: str) -> Optional[float]:
    try:
        text = record_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(f"{key}:"):
                return float(line.split(":", 1)[1].strip())
    except Exception:  # noqa: BLE001
        return None
    return None
