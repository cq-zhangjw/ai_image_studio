"""SANA-Sprint 1.6B 封装：文生图 / 统一输出规范（接口对齐 qwen/flux2/z-image util）。

SANA-Sprint 1.6B（NVIDIA + MIT Han Lab）：
    - 1.6B Linear DiT + DC-AE 32x 压缩 + Gemma-2-2B 文本编码器
    - sCM + LADD 混合蒸馏：1-4 步推理（默认 2 步），1024px 原生、多尺度
    - 支持中英双语 prompt；Sprint pipeline 不支持 negative_prompt（自动忽略）
    - 许可证 NSCL v2-custom（NVIDIA Open Model License，研究用途；商用前需审阅）
    - 已知限制：无法渲染复杂可读文字（模型卡声明），海报文字需实测
输出规范：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png（含耗时记录）
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import torch
from PIL import Image

_DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs"

# Sprint 蒸馏版官方推荐
_DEFAULT_STEPS = 2
_DEFAULT_GUIDANCE = 4.5
_DEFAULT_DTYPE = torch.bfloat16


class SanaSprintUtil:
    """SANA-Sprint 1.6B 工具类（懒加载单例）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        dtype: torch.dtype = _DEFAULT_DTYPE,
        cpu_offload: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        if model_path is None:
            local = Path(__file__).resolve().parent.parent / "models" / "Sana-Sprint-1.6B"
            model_path = local if local.exists() else "Efficient-Large-Model/Sana_Sprint_1.6B_1024px_diffusers"
        self.model_path = str(model_path)
        self.device = device if torch.cuda.is_available() else "cpu"
        self.dtype = dtype
        self.cpu_offload = cpu_offload
        self.output_root = Path(output_root)
        self._pipe = None  # 懒加载
        self._load_time_seconds: Optional[float] = None

    # ------------------------------------------------------------------ #
    def _load_pipe(self):
        if self._pipe is not None:
            return self._pipe
        from diffusers import SanaSprintPipeline

        t0 = time.perf_counter()
        pipe = SanaSprintPipeline.from_pretrained(
            self.model_path,
            dtype=self.dtype,
        )
        if self.cpu_offload and self.device == "cuda":
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        if hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        self._pipe = pipe
        self._load_time_seconds = time.perf_counter() - t0
        print(f"[sana-sprint] model loaded in {self._load_time_seconds:.1f}s")
        return pipe

    @property
    def pipe(self):
        return self._load_pipe()

    # ------------------------------------------------------------------ #
    def _make_run_dir(self, output_dir: Optional[Union[str, Path]]) -> Path:
        if output_dir is not None:
            run_dir = Path(output_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.output_root / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _save_prompt_record(self, run_dir: Path, prompt: str, params: dict) -> Path:
        record = run_dir / "input_prompt.txt"
        lines = [f"[prompt] {prompt}", "", "[params]"]
        for k, v in params.items():
            lines.append(f"{k}: {v}")
        record.write_text("\n".join(lines), encoding="utf-8")
        return record

    def _save_images(self, run_dir: Path, images: List[Image.Image], prefix: str) -> List[Path]:
        saved = []
        for idx, img in enumerate(images):
            path = run_dir / f"{prefix}_{idx + 1:02d}.png"
            img.save(path)
            saved.append(path)
        return saved

    def _make_generator(self, seed: Optional[int] = None) -> Optional[torch.Generator]:
        if seed is None:
            return None
        gen = torch.Generator("cuda") if self.device == "cuda" else torch.Generator()
        gen.manual_seed(seed)
        return gen

    # ------------------------------------------------------------------ #
    def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = _DEFAULT_STEPS,
        guidance_scale: float = _DEFAULT_GUIDANCE,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,  # Sprint 不支持，忽略
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "output",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """统一生成入口（SANA-Sprint 仅文生图；negative_prompt 被忽略）。

        返回 {"run_dir": Path, "prompt_record": Path, "images": List[Path]}
        """
        pipe = self.pipe
        gen = self._make_generator(seed)

        call_kwargs = dict(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
        if gen is not None:
            call_kwargs["generator"] = gen
        if progress_callback is not None:
            def _on_step_end(_pipe, step_index: int, _timestep, callback_kwargs):
                progress_callback(step_index + 1, num_inference_steps)
                return callback_kwargs

            call_kwargs["callback_on_step_end"] = _on_step_end
        call_kwargs.update(pipeline_kwargs)

        t_start = time.perf_counter()
        result = pipe(**call_kwargs)
        elapsed = time.perf_counter() - t_start
        generated = result.images

        run_dir = self._make_run_dir(output_dir)
        params = {
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "model": self.model_path,
            "dtype": str(self.dtype),
            "cpu_offload": self.cpu_offload,
            "elapsed_seconds": round(elapsed, 2),
            "steps_per_second": round(num_inference_steps / elapsed, 2) if elapsed else None,
        }
        if self._load_time_seconds is not None:
            params["model_load_seconds"] = round(self._load_time_seconds, 2)
        record = self._save_prompt_record(run_dir, prompt, params)
        saved = self._save_images(run_dir, generated, prefix)
        return {"run_dir": run_dir, "prompt_record": record, "images": saved}

    def text_to_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = _DEFAULT_STEPS,
        guidance_scale: float = _DEFAULT_GUIDANCE,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """文生图。返回 {"run_dir", "prompt_record", "images"}。"""
        return self.generate(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            progress_callback=progress_callback,
            **pipeline_kwargs,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def gpu_memory_info() -> str:
        if not torch.cuda.is_available():
            return "CUDA not available"
        return (
            f"allocated={torch.cuda.memory_allocated() / 2**20:.0f}MiB "
            f"reserved={torch.cuda.memory_reserved() / 2**20:.0f}MiB "
            f"max_allocated={torch.cuda.max_memory_allocated() / 2**20:.0f}MiB"
        )
