"""Qwen-Image-2.1 文生图 / 图像编辑工具封装。

基于 Hugging Face Diffusers 的 QwenImage21Pipeline，统一封装：
    - text_to_image(): 文生图
    - edit_image():    图像编辑（支持单图/多参考图，由 image 参数传入 PIL.Image 或列表）
    - generate():      统一入口（按是否传入 image 自动路由）

针对 RTX 3080 20G 显存环境的内置优化：
    1. 权重使用 bfloat16，减半显存占用；
    2. enable_model_cpu_offload()：文本编码器 / DiT / VAE 按需从 CPU 卸载到 GPU，
       峰值显存大幅下降（20G 显存下必须开启）；
    3. enable_vae_slicing() + enable_vae_tiling()：降低 VAE 解码峰值显存；
    4. 默认 1024x1024 生成分辨率（官方原生 2K，按需通过 width/height 调高）；
    5. 提供显存峰值查看（torch.cuda.max_memory_allocated）便于排查 OOM。

输出约定：
    outputs/<YYYYMMDD_hhmmss>/
        ├── input_prompt.txt   # 本次生成的提示词（及参数记录）
        └── output_xx.png      # 生成图片

用法示例：
    from utils.qwen_21_util import QwenImage21Util

    util = QwenImage21Util(model_path="models/Qwen-Image-2.1")
    out = util.text_to_image("a red fox in the snow", seed=42)
    out = util.edit_image("change the background to a beach", image="path/to/img.png")
"""

from __future__ import annotations

import datetime
import os
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import torch
from PIL import Image

# 官方推荐宽高比（原生 2K）
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}

_DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs"


class QwenImage21Util:
    """Qwen-Image-2.1 推理封装（懒加载单例 pipe）。"""

    def __init__(
        self,
        model_path: Union[str, Path, None] = None,
        device: str = "cuda",
        dtype: torch.dtype = torch.bfloat16,
        cpu_offload: bool = True,
        vae_slicing: bool = True,
        vae_tiling: bool = True,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
    ) -> None:
        # 默认优先使用本地 models/ 目录，其次回退到 HF repo id
        if model_path is None:
            local = Path(__file__).resolve().parent.parent / "models" / "Qwen-Image-2.1"
            model_path = local if local.exists() else "Qwen/Qwen-Image-2.1"
        self.model_path = str(model_path)
        self.device = device if torch.cuda.is_available() else "cpu"
        self.dtype = dtype
        self.cpu_offload = cpu_offload
        self.vae_slicing = vae_slicing
        self.vae_tiling = vae_tiling
        self.output_root = Path(output_root)
        self._pipe = None  # 懒加载
        self._load_time_seconds: Optional[float] = None  # 模型加载耗时

    # ------------------------------------------------------------------ #
    # 内部：pipe 加载与显存优化
    # ------------------------------------------------------------------ #
    def _load_pipe(self):
        if self._pipe is not None:
            return self._pipe
        t0 = time.perf_counter()
        try:
            from diffusers import QwenImage21Pipeline
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "当前 diffusers 版本不支持 QwenImage21Pipeline，请升级：\n"
                "  pip install -U diffusers  (或 pip install git+https://github.com/huggingface/diffusers)"
            ) from e

        pipe = QwenImage21Pipeline.from_pretrained(
            self.model_path,
            dtype=self.dtype,
        )
        if self.cpu_offload:
            # offload 模式下不要再 .to(device)，accelerate 会按需搬运模块
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(self.device)

        # QwenImage21Pipeline 部分版本未实现 VAE slicing/tiling，做能力探测
        if self.vae_slicing and hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        if self.vae_tiling and hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        self._pipe = pipe
        self._load_time_seconds = time.perf_counter() - t0
        return pipe

    @property
    def pipe(self):
        return self._load_pipe()

    def reset(self) -> None:
        """释放模型与显存（下次调用会重新加载）。"""
        if self._pipe is not None:
            self._pipe = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------ #
    # 内部：输出目录组织
    # ------------------------------------------------------------------ #
    def _make_run_dir(self, run_dir: Optional[Union[str, Path]] = None) -> Path:
        if run_dir is None:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.output_root / stamp
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _save_prompt_record(
        self,
        run_dir: Path,
        prompt: str,
        images: Optional[List[Image.Image]] = None,
        params: Optional[dict] = None,
    ) -> Path:
        lines = ["[prompt]", prompt, ""]
        if images:
            lines += ["[input images]", "\n".join(f"- {i}: {img.size} mode={img.mode}" for i, img in enumerate(images)), ""]
        if params:
            lines += ["[params]", "\n".join(f"{k}: {v}" for k, v in params.items()), ""]
        record = run_dir / "input_prompt.txt"
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
        num_inference_steps: int = 20,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "output",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """统一生成入口。

        - images 为 None            -> 文生图
        - images 为单图/多图列表     -> 图像编辑（多参考图组合）
        - width/height 为 None 时：文生图默认 1024；编辑模式继承第一张输入图尺寸
        - progress_callback(step, total)：扩散每步回调（step 从 1 开始），供 Web 进度条使用

        返回 {"run_dir": Path, "prompt_record": Path, "images": List[Path]}
        """
        pipe = self.pipe
        gen = self._make_generator(seed)

        # 编辑模式：优先继承输入图宽高比
        input_imgs: List[Image.Image] = []
        if images is not None:
            img_list = images if isinstance(images, (list, tuple)) else [images]
            for item in img_list:
                if isinstance(item, (str, Path)):
                    # 参考图统一转 RGB：避免 RGBA 触发模型"透明图层"语义干扰编辑
                    input_imgs.append(Image.open(item).convert("RGB"))
                else:
                    input_imgs.append(item.convert("RGB"))
            if width is None and height is None:
                w, h = input_imgs[0].size
                width, height = w, h  # 保持输入图比例
        if width is None:
            width = 1024
        if height is None:
            height = 1024

        call_kwargs = dict(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
        )
        if negative_prompt is not None:
            call_kwargs["negative_prompt"] = negative_prompt
        if gen is not None:
            call_kwargs["generator"] = gen
        if input_imgs:
            call_kwargs["image"] = input_imgs if len(input_imgs) > 1 else input_imgs[0]
        if progress_callback is not None:
            # diffusers callback_on_step_end: on_step_end(pipe, step_index, timestep, callback_kwargs)
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
        num_inference_steps: int = 20,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """文生图。返回 {"run_dir", "prompt_record", "images"}。"""
        return self.generate(
            prompt=prompt,
            images=None,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            **pipeline_kwargs,
        )

    def edit_image(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]],
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: int = 20,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """图像编辑（单图或多参考图）。

        未指定 width/height 时自动继承输入图尺寸。
        """
        return self.generate(
            prompt=prompt,
            images=image,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            **pipeline_kwargs,
        )

    # ------------------------------------------------------------------ #
    # 对外 API：图像扩充（outpainting）
    # ------------------------------------------------------------------ #
    def outpaint(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image],
        target_ratio: str = "16:9",
        direction: str = "right",
        canvas_fill: str = "white",
        num_inference_steps: int = 20,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """图像扩充（outpainting）：把原图扩展到目标画幅，补全扩展区域。

        做法（Qwen-Image-2.1 官方推荐的画布引导式编辑）：
            1. 将原图等比缩放后放置到目标画布（如 16:9）的指定一侧；
            2. 其余区域用 canvas_fill 填充（white/gray/edge）；
            3. 组装扩图 prompt（保持原图不变 + 无缝衔接扩展区域）；
            4. 以画布图作为参考图调用编辑模式，显式指定目标 width/height。

        参数：
            prompt: 对扩展区域内容的描述（如 "a desert with dunes to the horizon"）
            target_ratio: 目标画幅，取自官方宽高比表（1:1/4:3/3:4/3:2/2:3/16:9/9:16）
            direction: 原图在画布中的位置 = 扩展方向（right/left/up/down）
            canvas_fill: 留白填充方式（white=纯白 / gray=中性灰 / edge=边缘拉伸延伸）
        返回：与 generate 一致 {"run_dir", "prompt_record", "images"}
        """
        w, h = aspect_size(target_ratio)
        canvas = self._build_outpaint_canvas(image, w, h, direction, canvas_fill)
        position_word = {"right": "left", "left": "right", "down": "top", "up": "bottom"}[direction]
        extend_word = {"right": "to the right", "left": "to the left", "down": "downward", "up": "upward"}[direction]

        full_prompt = (
            f"The image on the {position_word} is the original image. "
            f"Extend the image {extend_word} to create a seamless {target_ratio} scene: {prompt}. "
            "Keep the original content unchanged, and seamlessly match its lighting, colors, texture and style."
        )
        return self.generate(
            prompt=full_prompt,
            images=canvas,
            width=w,
            height=h,
            num_inference_steps=num_inference_steps,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            **pipeline_kwargs,
        )

    @staticmethod
    def _build_outpaint_canvas(
        image: Union[str, Path, Image.Image],
        canvas_w: int,
        canvas_h: int,
        direction: str,
        canvas_fill: str,
    ) -> Image.Image:
        """构建扩图底图：原图等比缩放贴到画布一侧，其余区域填充。"""
        from PIL import Image as _Image

        if isinstance(image, (str, Path)):
            src = _Image.open(image).convert("RGB")
        else:
            src = image.convert("RGB")

        # 按方向等比缩放原图：横向扩展 -> 高度适配；纵向扩展 -> 宽度适配
        if direction in ("right", "left"):
            scale = canvas_h / src.height
        else:
            scale = canvas_w / src.width
        new_w = round(src.width * scale)
        new_h = round(src.height * scale)
        src = src.resize((new_w, new_h), _Image.LANCZOS)
        # 超出画布则裁剪
        if new_w > canvas_w:
            src = src.crop(((new_w - canvas_w) // 2, 0, (new_w + canvas_w) // 2, new_h))
            new_w, new_h = src.size
        if new_h > canvas_h:
            src = src.crop((0, (new_h - canvas_h) // 2, new_w, (new_h + canvas_h) // 2))
            new_w, new_h = src.size

        # 底图填充
        if canvas_fill == "edge":
            # 边缘拉伸延伸：整图拉伸铺满画布作底，再覆盖正确比例的缩放原图
            canvas = src.resize((canvas_w, canvas_h), _Image.LANCZOS)
        else:
            color = {"white": (255, 255, 255), "gray": (128, 128, 128)}[canvas_fill]
            canvas = _Image.new("RGB", (canvas_w, canvas_h), color)

        # 放置原图
        if direction == "right":
            canvas.paste(src, (0, (canvas_h - new_h) // 2))
        elif direction == "left":
            canvas.paste(src, (canvas_w - new_w, (canvas_h - new_h) // 2))
        elif direction == "down":
            canvas.paste(src, ((canvas_w - new_w) // 2, 0))
        else:  # up
            canvas.paste(src, ((canvas_w - new_w) // 2, canvas_h - new_h))
        return canvas

    # ------------------------------------------------------------------ #
    # 对外 API：精确编辑（标注引导）
    # ------------------------------------------------------------------ #
    def precise_edit(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image],
        mark: Optional[Union[str, Path, Image.Image]] = None,
        mask: Optional[Union[str, Path, Image.Image]] = None,
        annotation_style: str = "circle",
        num_inference_steps: int = 24,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        composite: bool = True,
        feather: int = 16,
        **pipeline_kwargs,
    ) -> dict:
        """精确编辑：标注编辑区域 + 提示说明，只修改标注区域。

        Qwen-Image-2.1 的编辑本质是"参考图引导的全图重绘"，为避免模型把标注区外的
        细节也重绘模糊，本方法在生成后做**区域合成**（composite）：
            - mask 内（编辑区）使用模型生成的新内容；
            - mask 外强制替换回原图（100% 保真）；
            - 羽化过渡消除接缝。

        参数：
            prompt: 修改意图描述（如 "add a glowing full moon in the marked area"）
            image: 原图
            mark: 标注图（画圈/涂鸦后的图，作为模型参考）
            mask: 分离 mask（白=编辑区，黑=保留区）。**推荐提供**，合成保真依赖它；
                  可用 draw_circle_mark(..., return_mask=True) 生成。
            annotation_style: circle=画圈 / paint=涂鸦 / mask=分离mask
            composite: 是否做区域合成（mask 外替换回原图），默认 True
            feather: 合成边缘羽化半径（像素），越大过渡越柔
        返回：与 generate 一致 {"run_dir", "prompt_record", "images"}
        """
        from PIL import ImageFilter

        # 构建参考图列表与标注描述
        refs: List[Image.Image] = []
        if mark is not None:
            if isinstance(mark, (str, Path)):
                refs.append(Image.open(mark).convert("RGB"))
            else:
                refs.append(mark.convert("RGB"))
        else:
            if isinstance(image, (str, Path)):
                refs.append(Image.open(image).convert("RGB"))
            else:
                refs.append(image.convert("RGB"))

        if mask is not None:
            if isinstance(mask, (str, Path)):
                refs.append(Image.open(mask).convert("L"))
            else:
                refs.append(mask.convert("L"))
            full_prompt = (
                "The first image is the original image. The second image is a binary mask "
                f"(white areas indicate the regions to edit). Edit ONLY the masked regions as instructed: {prompt}. "
                "Keep everything outside the mask unchanged."
            )
        else:
            style_desc = {
                "circle": "the red circles",
                "paint": "the painted strokes",
            }.get(annotation_style, "the marked regions")
            full_prompt = (
                f"In the provided image, {style_desc} are annotation marks indicating the regions to edit. "
                f"The annotation marks themselves must NOT appear in the output image. "
                f"Modify ONLY the marked regions as instructed: {prompt}. "
                "Keep everything else exactly unchanged, including details, texture and colors."
            )

        result = self.generate(
            prompt=full_prompt,
            images=refs if len(refs) > 1 else refs[0],
            num_inference_steps=num_inference_steps,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            **pipeline_kwargs,
        )

        # 区域合成：mask 外强制替换回原图，消除全图重绘导致的模糊
        if composite and mask is not None:
            out_path = result["images"][0]
            gen = Image.open(out_path).convert("RGB")
            orig = (
                Image.open(image) if isinstance(image, (str, Path)) else image
            ).convert("RGB").resize(gen.size, Image.LANCZOS)
            m = (
                Image.open(mask) if isinstance(mask, (str, Path)) else mask
            ).convert("L").resize(gen.size, Image.LANCZOS)
            if feather > 0:
                m = m.filter(ImageFilter.GaussianBlur(radius=feather))
            final = Image.composite(gen, orig, m)
            final.save(out_path)
            # 追加合成说明到记录文件
            record = result["prompt_record"]
            with record.open("a", encoding="utf-8") as fh:
                fh.write(f"\n[composite] mask_outside_replaced=True feather={feather}\n")
        return result

    @staticmethod
    def draw_circle_mark(
        image: Union[str, Path, Image.Image],
        center_xy: tuple[int, int],
        radius: int,
        color: tuple[int, int, int] = (255, 0, 0),
        line_width: int = 4,
        return_mask: bool = False,
    ) -> Union[Image.Image, tuple[Image.Image, Image.Image]]:
        """在原图上画红色圆圈标注。

        return_mask=True 时返回 (标注图, mask图)：mask 为圆内白色（=编辑区），
        可直接传给 precise_edit 的 mask 参数做区域合成。
        """
        from PIL import ImageDraw

        if isinstance(image, (str, Path)):
            img = Image.open(image).convert("RGB")
        else:
            img = image.convert("RGB")
        draw = ImageDraw.Draw(img)
        x, y = center_xy
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            outline=color,
            width=line_width,
        )
        if not return_mask:
            return img
        mask_img = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask_img).ellipse(
            [x - radius, y - radius, x + radius, y + radius], fill=255
        )
        return img, mask_img

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


def aspect_size(ratio: str) -> tuple[int, int]:
    """按官方宽高比表返回 (width, height)。"""
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"unsupported ratio {ratio!r}, choose from {list(ASPECT_RATIOS)}")
    return ASPECT_RATIOS[ratio]
