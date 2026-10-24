"""Real-ESRGAN 放大服务封装：复用 utils.realesrgan_util，接入任务进度。"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from .. import config

_PROJECT_ROOT = config.PROJECT_ROOT
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def upscale_image_realesrgan(task, image_path: Path) -> List[Path]:
    """Real-ESRGAN 快速超分（ncnn-vulkan，秒级，不占 CUDA 显存）。"""
    from utils.realesrgan_util import RealESRGANUtil
    from PIL import Image

    util = RealESRGANUtil(output_root=config.OUTPUT_DIR)
    p = task.payload

    def _cb(step: int, total: int, phase: str):
        task.set_progress(step, total, phase, int(round(step / total * 100)))

    input_size = Image.open(image_path).size
    p["input_size"] = f"{input_size[0]}x{input_size[1]}"
    result = util.upscale_image(
        image=str(image_path),
        scale=int(p.get("scale", 2)),
        tile_size=int(p.get("tile_size", 0)),
        progress_callback=_cb,
    )
    task.elapsed_seconds = _read_record(result["record"], "elapsed_seconds")
    # 写回实际输出尺寸（供历史展示 input → output）
    if result["images"]:
        out_size = Image.open(result["images"][0]).size
        p["output_size"] = f"{out_size[0]}x{out_size[1]}"
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


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
