"""Qwen-Image-2.1 推理服务封装：复用 utils.qwen_21_gguf_util，接入任务进度。

底层为 stable-diffusion.cpp GGUF 引擎（sd-cli 子进程），
与 utils/qwen_21_gguf_util.py 接口兼容，服务层无需改动任务逻辑。
"""

import gc
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .. import config

# 使 utils 可导入
_PROJECT_ROOT = config.PROJECT_ROOT
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.qwen_21_gguf_util import QwenImage21Util  # noqa: E402

_util: Optional[QwenImage21Util] = None


def get_util() -> QwenImage21Util:
    global _util
    if _util is None:
        _util = QwenImage21Util(output_root=config.OUTPUT_DIR)
    return _util


def _cb(task, cb: Optional[Callable[[int, int], None]] = None):
    """包装 util 进度回调 -> 更新 TaskInfo。"""

    def wrapper(step: int, total: int):
        task.set_progress(step, total, "sampling")
        if cb is not None:
            cb(step, total)

    return wrapper


def is_loaded() -> bool:
    """GGUF 子进程引擎无持久驻留；util 构造后即可用（首次生成时加载）。"""
    global _util
    return _util is not None


def unload() -> None:
    """释放 util（子进程退出时自动释放显存）。"""
    global _util
    _util = None
    gc.collect()


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
    task.steps_per_second = _read_record(result["prompt_record"], "steps_per_second")
    task.model_load_seconds = _read_record(result["prompt_record"], "model_load_seconds")
    return result["images"]


def edit_image(task, image_path: Path, mark_path: Optional[Path], mask_path: Optional[Path]) -> List[Path]:
    """编辑：多图融合（_image_paths）→ 传列表；单图有 mask/mark → precise_edit（合成保真）；仅 mark → precise_edit；无标注 -> 全图编辑。"""
    util = get_util()
    p = task.payload
    kwargs = dict(
        prompt=p["prompt"],
        num_inference_steps=p["num_inference_steps"],
        seed=p.get("seed"),
        progress_callback=_cb(task),
    )
    image_paths: list = p.get("_image_paths") or []
    if len(image_paths) > 1:
        # 多图融合：多图输入 + 编辑指令
        result = util.edit_image(
            image=[Path(x) for x in image_paths],
            **kwargs,
        )
    elif mask_path is not None or mark_path is not None:
        result = util.precise_edit(
            image=str(image_path),
            mark=str(mark_path) if mark_path else None,
            mask=str(mask_path) if mask_path else None,
            annotation_style=p.get("annotation_style", "mask" if mask_path else "circle"),
            composite=bool(p.get("composite", True)),
            feather=int(p.get("feather", 20)),
            **kwargs,
        )
    else:
        result = util.edit_image(
            prompt=p["prompt"],
            image=str(image_path),
            num_inference_steps=p["num_inference_steps"],
            seed=p.get("seed"),
            progress_callback=_cb(task),
        )
    task.elapsed_seconds = _read_record(result["prompt_record"], "elapsed_seconds")
    task.steps_per_second = _read_record(result["prompt_record"], "steps_per_second")
    task.model_load_seconds = _read_record(result["prompt_record"], "model_load_seconds")
    _copy_inputs_as_source(result, image_path, image_paths)
    return result["images"]


def outpaint(task, image_path: Path) -> List[Path]:
    util = get_util()
    p = task.payload
    result = util.outpaint(
        prompt=p["prompt"],
        image=str(image_path),
        target_ratio=p["target_ratio"],
        direction=p.get("direction", "right"),
        canvas_fill=p.get("fill", "edge"),
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
                raw = line.split(":", 1)[1].strip()
                return float(raw)
    except Exception:  # noqa: BLE001
        return None
    return None


def _copy_inputs_as_source(result: dict, image_path: Optional[Path], image_paths: Optional[list] = None) -> None:
    """把编辑/放大的输入原图复制进结果批次，供历史卡片/对比回显（_input_original 系列）。"""
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
