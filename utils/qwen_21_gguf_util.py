"""Qwen-Image-2.1 GGUF 推理封装 —— 无缝替代 utils/qwen_21_util.py。

对外暴露与旧实现同名的 `QwenImage21Util` 类与相同的公共方法/签名/
返回结构，调用方无需改动即可切换（diffusers 路径 -> sd.cpp GGUF 路径）。

与旧实现（QwenImage21Pipeline/diffusers）的区别：
    - 底层为 stable-diffusion.cpp 官方 sd-cli.exe（子进程），零 torch 依赖；
    - 多图融合实测 1024² 20 步约 100 秒（旧 diffusers 路径约 1665 秒）；
    - progress_callback 在完成时回调 (total, total)（sd-cli 无逐 step 文本
      进度；如需中途预览进度见 SdCppUtil.generate 的 preview_interval）；
    - dtype / vae_slicing / vae_tiling 等 torch 专属参数保留但忽略。

用法（与旧文件完全一致）：
    from utils.qwen_21_gguf_util import QwenImage21Util

    util = QwenImage21Util()
    out = util.text_to_image("a red fox in the snow", seed=42)
    out = util.edit_image("change the background to a beach", image="a.png")
    out = util.edit_image("merge both images", image=["a.png", "b.png"])
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from PIL import Image

from utils.sd_cpp_util import (
    ASPECT_RATIOS,
    SdCppUtil,
    aspect_size,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"

# Qwen-Image-2.1 GGUF 默认组件（sd_cpp/models 下）
_DEFAULT_DIFFUSION = "sd_cpp/models/qwen_image_2.1-Q8_0.gguf"
_DEFAULT_LLM = "sd_cpp/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf"
_DEFAULT_LLM_VISION = "sd_cpp/models/mmproj-Qwen3VL-8B-Instruct-F16.gguf"
_DEFAULT_VAE = "sd_cpp/models/qwen_image_2.1_vae_bf16.safetensors"


class QwenImage21Util(SdCppUtil):
    """Qwen-Image-2.1 (GGUF/sd.cpp) 推理封装，接口兼容旧 diffusers 实现。

    Args（GGUF 专属）:
        diffusion_model / llm / llm_vision / vae: 覆盖默认 GGUF 组件路径
        cli_path: sd-cli.exe 路径（默认 sd_cpp/bin/sd-cli.exe）
        device / cpu_offload: 推理设备与显存策略
        default_steps: 默认采样步数（Qwen-Image-2.1 建议 20~35）
        default_cfg_scale: 默认 CFG（Qwen-Image-2.1 建议 2.2）
        output_root: 输出根目录（默认项目 outputs/）

    兼容旧签名（保留但忽略或映射）:
        model_path: 旧 diffusers 模型目录；GGUF 模式下忽略（GGUF 由
                    diffusion_model 决定），保留仅为兼容调用方
        device / cpu_offload: 直接透传给 SdCppUtil
        dtype / vae_slicing / vae_tiling: torch 专属，忽略
    """

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        device: str = "cuda",
        dtype=None,  # 兼容旧签名：忽略
        cpu_offload: bool = False,
        vae_slicing=None,  # 兼容旧签名：忽略
        vae_tiling=None,   # 兼容旧签名：忽略
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
        *,
        diffusion_model: Optional[Union[str, Path]] = None,
        llm: Optional[Union[str, Path]] = None,
        llm_vision: Optional[Union[str, Path]] = None,
        vae: Optional[Union[str, Path]] = None,
        cli_path: Optional[Union[str, Path]] = None,
        default_steps: int = 20,
        default_cfg_scale: Optional[float] = 2.2,
        extra_args: Optional[dict] = None,
    ) -> None:
        super().__init__(
            diffusion_model=diffusion_model or _DEFAULT_DIFFUSION,
            llm=llm or _DEFAULT_LLM,
            llm_vision=llm_vision or _DEFAULT_LLM_VISION,
            vae=vae or _DEFAULT_VAE,
            cli_path=cli_path,
            device=device,
            cpu_offload=cpu_offload,
            default_steps=default_steps,
            default_cfg_scale=default_cfg_scale,
            output_root=output_root,
            extra_args=extra_args,
        )

    # ------------------------------------------------------------------ #
    # 兼容旧实现：文本编辑入口（outpaint / precise_edit / draw_circle_mark）
    # 均为纯 PIL 逻辑，与推理引擎无关，直接复用旧实现逻辑。
    # ------------------------------------------------------------------ #
    def outpaint(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image],
        target_ratio: str = "16:9",
        direction: str = "right",
        canvas_fill: str = "white",
        num_inference_steps: Optional[int] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **pipeline_kwargs,
    ) -> dict:
        """图像扩充（outpainting）：把原图扩展到目标画幅，补全扩展区域。

        返回：与 generate 一致 {"run_dir", "prompt_record", "images"}
        """
        w, h = aspect_size(target_ratio)
        canvas = self._build_outpaint_canvas(image, w, h, direction, canvas_fill)
        position_word = {"right": "left", "left": "right", "down": "top", "up": "bottom"}[direction]
        extend_word = {
            "right": "to the right", "left": "to the left",
            "down": "downward", "up": "upward",
        }[direction]
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
        if isinstance(image, (str, Path)):
            src = Image.open(image).convert("RGB")
        else:
            src = image.convert("RGB")

        if direction in ("right", "left"):
            scale = canvas_h / src.height
        else:
            scale = canvas_w / src.width
        new_w = round(src.width * scale)
        new_h = round(src.height * scale)
        src = src.resize((new_w, new_h), Image.LANCZOS)
        if new_w > canvas_w:
            src = src.crop(((new_w - canvas_w) // 2, 0, (new_w + canvas_w) // 2, new_h))
            new_w, new_h = src.size
        if new_h > canvas_h:
            src = src.crop((0, (new_h - canvas_h) // 2, new_w, (new_h + canvas_h) // 2))
            new_w, new_h = src.size

        if canvas_fill == "edge":
            canvas = src.resize((canvas_w, canvas_h), Image.LANCZOS)
        else:
            color = {"white": (255, 255, 255), "gray": (128, 128, 128)}[canvas_fill]
            canvas = Image.new("RGB", (canvas_w, canvas_h), color)

        if direction == "right":
            canvas.paste(src, (0, (canvas_h - new_h) // 2))
        elif direction == "left":
            canvas.paste(src, (canvas_w - new_w, (canvas_h - new_h) // 2))
        elif direction == "down":
            canvas.paste(src, ((canvas_w - new_w) // 2, 0))
        else:  # up
            canvas.paste(src, ((canvas_w - new_w) // 2, canvas_h - new_h))
        return canvas

    def precise_edit(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image],
        mark: Optional[Union[str, Path, Image.Image]] = None,
        mask: Optional[Union[str, Path, Image.Image]] = None,
        annotation_style: str = "circle",
        num_inference_steps: Optional[int] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        composite: bool = True,
        feather: int = 16,
        **pipeline_kwargs,
    ) -> dict:
        """精确编辑：标注编辑区域 + 提示说明，只修改标注区域（含区域合成）。"""
        from PIL import ImageFilter

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
        """在原图上画红色圆圈标注（与旧实现一致）。"""
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
