"""MOSS-Image-SFT（OpenMOSS 5B DiT + Qwen3.5-9B TE，diffusers 格式）封装：文生图 / 统一输出规范。

接口对齐 utils/ernie_util.py：
    text_to_image / generate / gpu_memory_info / unload
    + 扩散步级 progress_callback（Web SSE 进度用）
输出规范：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png（含耗时记录）

环境：RTX 3080 20G。全量 bf16 27.2GB（text_encoder Qwen3.5-9B ~16.8GB + DiT 5B ~10.2GB
+ FLUX.2 VAE 0.25GB）20G 装不下 → cpu_offload（pipeline 内置 text_encoder->transformer->vae
搬运序列）；后续可量化（DiT int8 5.4GB + TE 4bit 7.3GB ≈ 12.7GB 全载）提速。

模型：OpenMOSS/MOSS-Image-SFT（Apache 2.0，5B DiT，原生 JSON 布局控制 + 强中英文本渲染，
4K tokens 提示词；ModelScope 官方仓库国内直下）。docs/18 集成履历。

进度回调：MOSS pipeline 为标准 diffusers 无 callback 参数的自定义 pipeline，本 util 使用
utils/moss_pipeline_local.py（本地注入版，支持 callback_on_step_end(step, total)），
并在加载时将该注入版覆盖模型目录内 pipeline_moss_image.py 以保证 from_pretrained 命中。
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

# SFT 推荐步数（官方默认 50；社区常用 25-30 兼顾速度——docs/18 测试后定）
_DEFAULT_STEPS = 30
# 官方默认 CFG：3.0（uncond_skip_layers=(22,) 已内置于 pipeline 默认）
_DEFAULT_GUIDANCE = 3.0


class MossImageUtil:
    """MOSS-Image-SFT 工具类（懒加载单例）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        cpu_offload: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        if model_path is None:
            local = Path(__file__).resolve().parent.parent / "models" / "MOSS-Image-SFT"
            model_path = local if local.exists() else "OpenMOSS/MOSS-Image-SFT"
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
        from utils.moss_pipeline_local import MOSSImagePipeline

        t0 = time.perf_counter()
        # 将注入版 pipeline 覆盖模型目录内原版，保证 from_pretrained 动态模块命中注入版
        try:
            src = Path(__file__).resolve().parent / "moss_pipeline_local.py"
            dst = Path(self.model_path) / "pipeline_moss_image.py"
            if dst.exists() and src.read_text(encoding="utf-8") != dst.read_text(encoding="utf-8"):
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        # bf16 全精度 27.2GB：20G 显存必须 cpu_offload（内置搬运序列 text_encoder->transformer->vae）
        pipe = MOSSImagePipeline.from_pretrained(
            self.model_path, torch_dtype=torch.bfloat16, trust_remote_code=True
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
        print(f"[moss] model loaded in {self._load_time_seconds:.1f}s")
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

        # 步级进度回调（注入版 pipeline 的 callback_on_step_end）
        cb_state = {"last": 0}

        def _step_cb(step: int, total: int):
            cb_state["last"] = step
            if progress_callback is not None:
                progress_callback(min(step, total), total)

        kwargs["callback_on_step_end"] = _step_cb

        result = pipe(**kwargs)
        images = result.images

        elapsed = time.perf_counter() - t0
        params = {
            "model": "moss-image-sft",
            "width": width,
            "height": height,
            "steps": num_inference_steps,
            "seed": seed,
            "guidance_scale": guidance_scale if guidance_scale is not None else _DEFAULT_GUIDANCE,
            "elapsed_seconds": round(elapsed, 2),
            "model_load_seconds": round(self._load_time_seconds, 2) if self._load_time_seconds else None,
        }
        self._save_prompt_record(run_dir, prompt, params)
        paths = self._save_images(run_dir, images)
        return {"images": paths, "prompt_record": run_dir / "input_prompt.txt"}

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
