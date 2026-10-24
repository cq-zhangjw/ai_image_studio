"""FLUX.2 [klein] 4B 推理服务封装：复用 utils.flux2_util，接入任务进度。

显存策略：与 qwen_service 互斥驻留（20G 卡不足同时加载两个大模型），
切换模型时由 tasks 层调用 unload 释放另一模型（gc + empty_cache）。
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

from utils.flux2_util import Flux2KleinUtil  # noqa: E402

_util: Optional[Flux2KleinUtil] = None


def get_util() -> Flux2KleinUtil:
    global _util
    if _util is None:
        _util = Flux2KleinUtil(
            model_path=str(config.FLUX2_MODEL_DIR),
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


def _apply_stats(task, result: dict) -> None:
    task.elapsed_seconds = _read_record(result["prompt_record"], "elapsed_seconds")
    task.steps_per_second = _read_record(result["prompt_record"], "steps_per_second")
    task.model_load_seconds = _read_record(result["prompt_record"], "model_load_seconds")


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
    _apply_stats(task, result)
    return result["images"]


def edit_image(task, image_path: Optional[Path]) -> List[Path]:
    """图像编辑：多图参考（_image_paths）→ 传列表（提示词融合）；单图 → 单参考编辑。"""
    util = get_util()
    p = task.payload
    paths: list = p.get("_image_paths") or []
    image_arg: object
    if len(paths) > 1:
        image_arg = [str(Path(x)) for x in paths]
    else:
        image_arg = str(image_path)
    result = util.edit_image(
        prompt=p["prompt"],
        image=image_arg,
        num_inference_steps=p["num_inference_steps"],
        seed=p.get("seed"),
        progress_callback=_cb(task),
    )
    _apply_stats(task, result)
    _copy_inputs_as_source(result, image_path, paths)
    return result["images"]


def _copy_inputs_as_source(result: dict, image_path: Optional[Path], image_paths: Optional[list] = None) -> None:
    """把编辑输入原图复制进结果批次，供历史卡片/对比回显（_input_original 系列）。"""
    import shutil

    run_dir = Path(result.get("run_dir", ""))
    if not run_dir.is_dir():
        return
    inputs: list = [Path(x) for x in (image_paths or [])] if image_paths else []
    if image_path is not None:
        inputs.insert(0, Path(image_path))
    for i, src in enumerate(inputs):
        if src and src.is_file():
            name = "_input_original.png" if i == 0 else f"_input_original_{i}.png"
            try:
                dest = run_dir / name
                if not dest.exists():
                    shutil.copy2(src, dest)
            except Exception:  # noqa: BLE001
                pass


def _read_record(record_path: Path, key: str) -> Optional[float]:
    try:
        text = record_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith(f"{key}: "):
                return float(line.split(": ", 1)[1])
    except Exception:  # noqa: BLE001
        return None
    return None
