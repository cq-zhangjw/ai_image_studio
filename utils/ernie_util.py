"""ERNIE-Image-Turbo (FP8, diffusers 格式) 封装：文生图 / 统一输出规范。

接口对齐 utils/flux2_util.py：
    text_to_image / generate / gpu_memory_info
    + 扩散步级 progress_callback（Web SSE 进度用）
输出规范：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png（含耗时记录）

环境：RTX 3080 20G（FP8 权重 13.1GB 全载 GPU；Ampere 无 FP8 tensor core，
PyTorch 按需反量化计算，速度略降但可用——docs/17 测试履历实测）。

模型：szwagros/ernie-image-turbo-fp8（Apache 2.0，百度 ERNIE-Image-Turbo 8B DiT 的
diffusers 社区量化版，高密度文字/结构化布局 SOTA：LTBench 0.9733）。
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

# Turbo 蒸馏版推荐参数（官方步数区间见 docs/17 履历实测）
_DEFAULT_STEPS = 20


class ErnieImageUtil:
    """ERNIE-Image-Turbo 工具类（懒加载单例）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        cpu_offload: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        if model_path is None:
            # 优先 BF16 转换版（FP8 原生格式 diffusers 不认，见 docs/17）
            local = Path(__file__).resolve().parent.parent / "models" / "ERNIE-Image-Turbo-BF16"
            if not local.exists():
                local = Path(__file__).resolve().parent.parent / "models" / "ERNIE-Image-Turbo-FP8"
            model_path = local if local.exists() else "szwagros/ernie-image-turbo-fp8"
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
        from diffusers import ErnieImagePipeline

        t0 = time.perf_counter()
        quant_cfg = Path(self.model_path) / "quantization_config.json"
        if quant_cfg.exists():
            # INT8 量化版（iximbox/ERNIE-Image-INT8）：目录自带 quantization_config.json，
            # diffusers 自动走 quanto 加载 transformer(int8) + text_encoder/pe(bf16)，无需显式 config。
            # 全组件 bf16/int8 合计 ~22GB，20G 卡必须 cpu_offload 逐模块搬移（官方推荐 24G+）。
            pipe = ErnieImagePipeline.from_pretrained(self.model_path, torch_dtype=torch.bfloat16)
            if self.cpu_offload and self.device == "cuda":
                pipe.enable_model_cpu_offload()
            else:
                pipe = pipe.to(self.device)
        else:
            # BF16 全精度版 25GB：20G 显存必须 cpu_offload 逐层搬运（慢但可用）
            pipe = ErnieImagePipeline.from_pretrained(self.model_path, torch_dtype=torch.bfloat16)
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
        print(f"[ernie] model loaded in {self._load_time_seconds:.1f}s")
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
        seed: Optional[int] = None,
        guidance_scale: Optional[float] = None,
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
            "model": "ernie-image-turbo-fp8",
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "seed": seed,
            "elapsed_seconds": round(elapsed, 2),
            "model_load_seconds": round(self._load_time_seconds or 0, 2),
        }
        record = self._save_prompt_record(run_dir, prompt, params)
        paths = self._save_images(run_dir, images)
        print(f"[ernie] generated {len(paths)} image(s) in {elapsed:.1f}s")
        return {"images": paths, "prompt_record": record, "elapsed_seconds": elapsed}

    # ------------------------------------------------------------------ #
    # 兼容接口 / 工具
    # ------------------------------------------------------------------ #
    def generate(self, prompt: str, **kwargs):
        """generate 别名（对齐 qwen util 风格）。"""
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
