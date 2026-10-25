"""FLUX.2 [klein] 9B 推理服务封装：复用 utils.flux2_gguf_util，接入任务进度。

底层为 stable-diffusion.cpp GGUF 引擎（sd-cli 子进程，flux-2-klein-9b-Q8_0 +
Qwen3-8B + flux2-vae，models/gguf），与 utils/flux2_gguf_util.py 接口兼容，
服务层无需改动任务逻辑；子进程零驻留显存，无互斥卸载需求。
"""

import gc
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .. import config

_PROJECT_ROOT = config.PROJECT_ROOT
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.flux2_gguf_util import Flux2KleinUtil  # noqa: E402

_util: Optional[Flux2KleinUtil] = None


def get_util() -> Flux2KleinUtil:
    global _util
    if _util is None:
        _util = Flux2KleinUtil(output_root=config.OUTPUT_DIR)
    return _util


def _cb(task, cb: Optional[Callable[[int, int], None]] = None):
    def wrapper(step: int, total: int, preview: Optional[str] = None):
        task.set_progress(step, total, "sampling", preview_url=preview)
        if cb is not None:
            cb(step, total)

    return wrapper


def _preview_interval(steps: int) -> int:
    """GGUF 采样中途预览自适应：>=12 步才启用（interval=max(2, steps//5)），短任务仅进度行。"""
    return max(2, int(steps) // 5) if int(steps) >= 12 else 0


def is_loaded() -> bool:
    """GGUF 子进程引擎无持久驻留；util 构造后即可用（首次生成时加载）。"""
    global _util
    return _util is not None


def unload() -> None:
    """释放 util（子进程退出时自动释放显存）。"""
    global _util
    _util = None
    gc.collect()


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
        preview_interval=_preview_interval(p["num_inference_steps"]),
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
    elif paths:
        image_arg = str(Path(paths[0]))  # 多图提交但仅 1 张：退化为单图编辑
    else:
        image_arg = str(image_path)
    result = util.edit_image(
        prompt=p["prompt"],
        image=image_arg,
        num_inference_steps=p["num_inference_steps"],
        seed=p.get("seed"),
        progress_callback=_cb(task),
        preview_interval=_preview_interval(p["num_inference_steps"]),
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
