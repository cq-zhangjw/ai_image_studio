"""Lumina-Image-2.0 (Alpha-VLLM, diffusers Lumina2Pipeline) 封装：文生图 / 统一输出规范。

模型：Alpha-VLLM/Lumina-Image-2.0（2.6B Flag-DiT + Gemma-2-2B TE + FLUX VAE，Apache 2.0）
支持中英双语提示词、多分辨率（1024 基准，最高 2048）；中英文字排版/高密度文字能力强。

显存：BF16 全载 ~14-16GB（1024x1024），RTX 3080 20G 可直接跑；
稳妥起见默认 enable_model_cpu_offload()（逐模块搬移，峰值更低）。

接口对齐 utils/ernie_util.py：
    text_to_image / generate / gpu_memory_info / unload
    + 扩散步级 progress_callback（Web SSE 进度用）
输出规范：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png（含耗时记录）
"""

from __future__ import annotations

import datetime
import gc
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import torch
from PIL import Image

_DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs"

# Lumina-2.0 推荐参数（官方 demo：40 步、CFG 4.0）
_DEFAULT_STEPS = 40
_DEFAULT_GUIDANCE = 4.0


class LuminaImageUtil:
    """Lumina-Image-2.0 工具类（懒加载单例）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        cpu_offload: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        if model_path is None:
            local = Path(__file__).resolve().parent.parent / "models" / "Lumina-Image-2.0"
            model_path = local if local.exists() else "Alpha-VLLM/Lumina-Image-2.0"
        self.model_path = str(model_path)
        self.device = device if torch.cuda.is_available() else "cpu"
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
        from diffusers import Lumina2Pipeline

        t0 = time.perf_counter()
        pipe = Lumina2Pipeline.from_pretrained(self.model_path, torch_dtype=torch.bfloat16)
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
        print(f"[lumina] model loaded in {self._load_time_seconds:.1f}s")
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

    def _save_prompt_record(self, run_dir: Path, prompt: str, params: dict) -> Path:
        record = run_dir / "input_prompt.txt"
        lines = [f"[prompt] {prompt}", "", "[params]"]
        for k, v in params.items():
            lines.append(f"{k}: {v}")
        record.write_text("\n".join(lines), encoding="utf-8")
        return record

    def _save_images(self, run_dir: Path, images: List[Image.Image]) -> List[Path]:
        paths: List[Path] = []
        for idx, img in enumerate(images, 1):
            p = run_dir / f"output_{idx:02d}.png"
            img.save(p)
            paths.append(p)
        return paths

    # ------------------------------------------------------------------ #
    # 对外：文生图
    # ------------------------------------------------------------------ #
    def text_to_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = _DEFAULT_STEPS,
        guidance_scale: Optional[float] = _DEFAULT_GUIDANCE,
        seed: Optional[int] = None,
        output_dir: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """生成 -> 落盘 -> 返回 {"images": [...], "prompt_record": Path}。"""
        pipe = self.pipe
        run_dir = self._make_run_dir(output_dir)
        t0 = time.perf_counter()

        generator = None
        if seed is not None:
            generator = torch.Generator(self.device).manual_seed(seed)

        kwargs: dict = dict(
            prompt=prompt,
            height=height,
            width=width,
            num_inference_steps=num_inference_steps,
            generator=generator,
        )
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
        if guidance_scale is not None:
            kwargs["guidance_scale"] = guidance_scale

        # 步级进度回调（diffusers 通用接口）
        cb_state = {"last": 0}

        def _step_cb(pipe, step, timestep, callback_kwargs):
            total = num_inference_steps
            cb_state["last"] = step
            if progress_callback is not None:
                progress_callback(min(step + 1, total), total)
            return callback_kwargs

        if progress_callback is not None:
            kwargs["callback_on_step_end"] = _step_cb

        try:
            result = pipe(**kwargs)
        except TypeError:
            # 版本差异兜底：去掉 callback 重试
            kwargs.pop("callback_on_step_end", None)
            result = pipe(**kwargs)
        if progress_callback is not None and cb_state["last"] < num_inference_steps:
            progress_callback(num_inference_steps, num_inference_steps)

        images: List[Image.Image] = result.images

        elapsed = time.perf_counter() - t0
        params = {
            "model": "lumina-image-2.0",
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "seed": seed,
            "elapsed_seconds": round(elapsed, 2),
            "model_load_seconds": round(self._load_time_seconds or 0, 2),
        }
        record = self._save_prompt_record(run_dir, prompt, params)
        paths = self._save_images(run_dir, images)
        print(f"[lumina] generated {len(paths)} image(s) in {elapsed:.1f}s")
        return {"images": paths, "prompt_record": record, "elapsed_seconds": elapsed}

    # ------------------------------------------------------------------ #
    # 兼容接口 / 工具
    # ------------------------------------------------------------------ #
    def generate(self, prompt: str, **kwargs):
        """generate 别名（对齐其它 util 风格）。"""
        return self.text_to_image(prompt, **kwargs)

    def gpu_memory_info(self) -> dict:
        """当前显存占用概览（对齐其它 util）。"""
        if not torch.cuda.is_available():
            return {"device": "cpu"}
        allocated = torch.cuda.memory_allocated() / 2**20
        reserved = torch.cuda.memory_reserved() / 2**20
        total = torch.cuda.get_device_properties(0).total_memory / 2**20
        return {
            "device": "cuda",
            "allocated_mb": int(allocated),
            "reserved_mb": int(reserved),
            "total_mb": int(total),
            "percent": round(allocated / total * 100, 1),
        }

    def unload(self) -> None:
        """释放显存（切换模型时由 service 调用）。"""
        self._pipe = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
