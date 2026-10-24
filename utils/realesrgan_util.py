"""Real-ESRGAN 快速超分封装（ncnn-vulkan 外部引擎）。

基于 ai-image-service/utils/realesrgan_util.py 的方案扩展：
    - 支持 2x / 3x / 4x 倍数（自动选模型：animevideov3-x2/x3/x4、x4plus）
    - 大图自动 tile 分块（ncnn -t 参数），不占 CUDA 显存（Vulkan 推理）
    - 输出约定：outputs/<YYYYMMDD_hhmmss>/output_01.png + input_prompt.txt

用法：
    from utils.realesrgan_util import RealESRGANUtil
    util = RealESRGANUtil()
    r = util.upscale_image("inputs/a.png", scale=4)     # {"run_dir", "record", "images"}
"""

from __future__ import annotations

import datetime
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BIN_DIR = _REPO_ROOT / "models" / "realesrgan"
_OUTPUT_ROOT_DEFAULT = _REPO_ROOT / "outputs"

# ncnn 原生仅稳定支持 4x（x4plus，写实强）。2x/3x = 4x 超分后 LANCZOS 缩到目标尺寸（细节更丰富）。
# 注：官方 animevideov3-x2/x3 param 是"内部 4x + Resize 缩回"，ncnn-vulkan 实测忽略末尾 Resize → 实际输出 4x，故不按倍数选模型。
_MODEL = "realesrgan-x4plus"


class RealESRGANUtil:
    """Real-ESRGAN 快速超分封装（懒加载无状态，subprocess 调用）。"""

    def __init__(self, bin_dir: Union[str, Path] = _BIN_DIR, output_root: Union[str, Path] = _OUTPUT_ROOT_DEFAULT) -> None:
        self.bin_dir = Path(bin_dir)
        self.output_root = Path(output_root)
        self.exe = self.bin_dir / "realesrgan-ncnn-vulkan.exe"
        if sys.platform.startswith("linux"):
            self.exe = self.bin_dir / "realesrgan-ncnn-vulkan"
        if not self.exe.exists():
            raise FileNotFoundError(f"realesrgan-ncnn-vulkan 不存在: {self.exe}")

    # ------------------------------------------------------------------ #
    # 输出组织
    # ------------------------------------------------------------------ #
    def _make_run_dir(self, run_dir: Optional[Union[str, Path]]) -> Path:
        if run_dir is None:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.output_root / stamp
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _save_record(self, run_dir: Path, inputs: List[Union[str, Path]], params: Optional[dict] = None) -> Path:
        lines = ["[input files]"]
        lines += [f"- {p}" for p in inputs]
        lines.append("")
        if params:
            lines += ["[params]", "\n".join(f"{k}: {v}" for k, v in params.items())]
        record = run_dir / "input_prompt.txt"
        record.write_text("\n".join(lines), encoding="utf-8")
        return record

    # ------------------------------------------------------------------ #
    # 对外 API
    # ------------------------------------------------------------------ #
    def upscale_image(
        self,
        image: Union[str, Path, Image.Image],
        scale: int = 4,
        tile_size: int = 0,  # 0 = ncnn 自动分块；>0 如 256/512 强制分块
        output_dir: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """快速超分放大。返回 {"run_dir", "record", "images"}。

        progress_callback(step, total, phase)：3 阶段（loading/sampling/saving）。
        """
        if not (isinstance(scale, int) and 2 <= scale <= 4):
            raise ValueError(f"不支持的倍数: {scale}，支持 2/3/4")

        def _emit(step: int, phase: str):
            if progress_callback is not None:
                progress_callback(step, 3, phase)

        _emit(1, "sampling")

        # 输入落盘为临时 png（PIL Image 或路径）
        tmp_in = self.output_root / "_realesrgan_input_tmp.png"
        if isinstance(image, (str, Path)):
            src = Path(image)
            if src.suffix.lower() != ".png":
                Image.open(src).convert("RGB").save(tmp_in)
                src = tmp_in
            in_path = src
            in_label = str(image)
        else:
            image.convert("RGB").save(tmp_in)
            in_path = tmp_in
            in_label = "PIL.Image"

        run_dir = self._make_run_dir(output_dir)
        out_path = run_dir / "output_01.png"

        # 原图副本（_ 前缀不参与产物列表）：供放大历史点击后对比回显
        try:
            src_img = Image.open(in_path).convert("RGB")
            src_img.save(run_dir / "_input_original.png")
        except Exception:  # noqa: BLE001
            pass

        cmd = [
            str(self.exe),
            "-i", str(in_path),
            "-o", str(out_path),
            "-n", _MODEL,
        ]
        if tile_size and tile_size > 0:
            cmd += ["-t", str(tile_size)]

        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        elapsed = time.perf_counter() - t0
        _emit(2, "saving")

        if proc.returncode != 0:
            raise RuntimeError(f"realesrgan 失败({proc.returncode}): {proc.stderr[-500:]}")
        if not out_path.exists():
            raise RuntimeError(f"realesrgan 未产出文件: {out_path}")

        # ncnn 原生输出 4x；scale<4 时按目标尺寸 LANCZOS 缩放（4x 细节后再缩，优于直接小倍率）
        in_size = Image.open(in_path).size if not isinstance(image, Image.Image) else image.size
        out_img = Image.open(out_path).convert("RGB")
        if scale != 4:
            target = (in_size[0] * scale, in_size[1] * scale)
            if out_img.size != target:
                out_img = out_img.resize(target, Image.LANCZOS)
                out_img.save(out_path)

        # 清理临时输入
        if tmp_in.exists():
            tmp_in.unlink()

        out_size = out_img.size
        params = {
            "engine": "realesrgan",
            "model": _MODEL,
            "scale": scale,
            "tile_size": tile_size or "auto",
            "input_size": f"{in_size[0]}x{in_size[1]}",
            "output_size": f"{out_size[0]}x{out_size[1]}",
            "elapsed_seconds": round(elapsed, 2),
        }
        record = self._save_record(run_dir, [in_label], params)
        return {"run_dir": run_dir, "record": record, "images": [out_path]}


if __name__ == "__main__":
    util = RealESRGANUtil()
    r = util.upscale_image(r"E:\my_projects\qwen-2.1\outputs\20261024_074648\output_01.png", scale=4)
    print(r["images"])
