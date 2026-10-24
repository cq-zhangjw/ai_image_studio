"""FLUX.2 [klein] 4B 封装：文生图 / 图像编辑（单参考与多参考）/ 统一输出规范。

接口对齐 utils/qwen_21_util.py：
    text_to_image / edit_image / generate / gpu_memory_info
    + 扩散步级 progress_callback（Web SSE 进度用）
输出规范：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png（含耗时记录）

环境：RTX 3080 20G 可跑（官方 ~13GB VRAM；bf16 + cpu_offload 更稳）。
模型：black-forest-labs/FLUX.2-klein-4B（Apache 2.0，蒸馏版默认 4 steps、guidance 1.0）。
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import torch
from PIL import Image

_DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs"

# klein 蒸馏版官方推荐参数
_DEFAULT_STEPS = 4
_DEFAULT_GUIDANCE = 1.0
# 官方示例为 bf16 + cpu_offload，20G 卡推荐
_DEFAULT_DTYPE = torch.bfloat16


class Flux2KleinUtil:
    """FLUX.2 [klein] 4B 工具类（懒加载单例）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        dtype: torch.dtype = _DEFAULT_DTYPE,
        cpu_offload: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        if model_path is None:
            local = Path(__file__).resolve().parent.parent / "models" / "FLUX.2-klein-4B"
            model_path = local if local.exists() else "black-forest-labs/FLUX.2-klein-4B"
        self.model_path = str(model_path)
        self.device = device if torch.cuda.is_available() else "cpu"
        self.dtype = dtype
        self.cpu_offload = cpu_offload
        self.output_root = Path(output_root)
        self._pipe = None  # 懒加载
        self._load_time_seconds: Optional[float] = None

    # ------------------------------------------------------------------ #
    # 内部：pipe 加载与显存优化
    # ------------------------------------------------------------------ #
    def _load_pipe(self):
        if self._pipe is not None:
            return self._pipe
        from diffusers import Flux2KleinPipeline

        t0 = time.perf_counter()
        pipe = Flux2KleinPipeline.from_pretrained(
            self.model_path,
            dtype=self.dtype,
        )
        if self.cpu_offload and self.device == "cuda":
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)
        # hasattr 防御：版本差异时自动跳过
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        if hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        self._pipe = pipe
        self._load_time_seconds = time.perf_counter() - t0
        print(f"[flux2] model loaded in {self._load_time_seconds:.1f}s")
        return pipe

    @property
    def pipe(self):
        return self._load_pipe()

    # ------------------------------------------------------------------ #
    # 内部：输出规范
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

    def _save_prompt_record(
        self,
        run_dir: Path,
        prompt: str,
        input_images: Optional[List[Image.Image]],
        params: dict,
    ) -> Path:
        record = run_dir / "input_prompt.txt"
        lines = [
            f"[prompt] {prompt}",
            "",
            "[params]",
        ]
        for k, v in params.items():
            lines.append(f"{k}: {v}")
        if input_images:
            lines.append("")
            lines.append("[input_images]")
            for idx, img in enumerate(input_images, 1):
                lines.append(f"- input_{idx:02d}.png ({img.size[0]}x{img.size[1]})")
                img.save(run_dir / f"input_{idx:02d}.png")
        record.write_text("\n".join(lines), encoding="utf-8")
        return record

    def _save_images(
        self,
        run_dir: Path,
        images: List[Image.Image],
        prefix: str = "output",
    ) -> List[Path]:
        saved = []
        for idx, img in enumerate(images):
            path = run_dir / f"{prefix}_{idx + 1:02d}.png"
            img.save(path)
            saved.append(path)
        return saved

    def _make_generator(self, seed: Optional[int] = None) -> Optional[torch.Generator]:
        if seed is None:
            return None
        if self.device == "cuda":
            gen = torch.Generator("cuda")
        else:
            gen = torch.Generator()
        gen.manual_seed(seed)
        return gen

    # ------------------------------------------------------------------ #
    # 对外 API
    # ------------------------------------------------------------------ #
    def generate(
        self,
        prompt: str,
        images: Optional[Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]]] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: int = _DEFAULT_STEPS,
        guidance_scale: float = _DEFAULT_GUIDANCE,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "output",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """统一生成入口。

        - images 为 None            -> 文生图
        - images 为单图/多图列表     -> 图像编辑（单参考 / 多参考合成）
        - 未指定宽高时：文生图默认 1024x1024；编辑模式继承第一张输入图尺寸
        - progress_callback(step, total)：扩散每步回调

        返回 {"run_dir": Path, "prompt_record": Path, "images": List[Path]}
        """
        pipe = self.pipe
        gen = self._make_generator(seed)

        input_imgs: List[Image.Image] = []
        if images is not None:
            img_list = images if isinstance(images, (list, tuple)) else [images]
            for item in img_list:
                if isinstance(item, (str, Path)):
                    input_imgs.append(Image.open(item).convert("RGB"))
                else:
                    input_imgs.append(item.convert("RGB"))
            if width is None and height is None:
                w, h = input_imgs[0].size
                width, height = w, h
        if width is None:
            width = 1024
        if height is None:
            height = 1024

        call_kwargs = dict(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
        if negative_prompt is not None:
            call_kwargs["negative_prompt"] = negative_prompt
        if gen is not None:
            call_kwargs["generator"] = gen
        if input_imgs:
            # klein 单模型统一支持单参考/多参考编辑
            call_kwargs["image"] = input_imgs if len(input_imgs) > 1 else input_imgs[0]
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
        record = self._save_prompt_record(run_dir, prompt, input_imgs or None, params)
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
            images=None,
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

    def edit_image(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]],
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: int = _DEFAULT_STEPS,
        guidance_scale: float = _DEFAULT_GUIDANCE,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """图像编辑（单参考或多参考合成）。未指定宽高时继承输入图尺寸。"""
        return self.generate(
            prompt=prompt,
            images=image,
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
    # 显存诊断
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
