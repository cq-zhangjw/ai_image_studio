"""FLUX.2 [klein] 9B (GGUF/sd.cpp) 推理封装，接口兼容旧 diffusers 实现。

替换 flux2-4b（diffusers 驻留式）为 flux2-9b GGUF 子进程推理：
    - 模型：flux-2-klein-9b-Q8_0.gguf + Qwen3-8B-Q4_K_M.gguf（文本编码器）+ flux2-vae.safetensors
    - 引擎：sd-cli.exe 子进程（utils.sd_cpp_util），零驻留显存、与图像模型天然共存
    - 文生图 / 单图编辑 / 多图融合 均复用 SdCppUtil.generate（参考图 -r）

用法示例：
    from utils.flux2_gguf_util import Flux2KleinUtil

    util = Flux2KleinUtil(output_root=config.OUTPUT_DIR)
    out = util.text_to_image("a cat eat a apple", width=1024, height=1024,
                             num_inference_steps=20, seed=42)
    out = util.edit_image("merge both images", image=["a.png", "b.png"])
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Union

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.sd_cpp_util import (  # noqa: E402
    KNOWN_MODEL_FILES,
    SdCppUtil,
    _DEFAULT_OUTPUT_ROOT,
)


def _pick(name: str) -> str:
    """在 models/gguf 与 sd_cpp/models 中定位组件文件。"""
    for d in (_PROJECT_ROOT / "models" / "gguf", _PROJECT_ROOT / "sd_cpp" / "models"):
        cand = d / name
        if cand.exists():
            return str(cand)
    raise FileNotFoundError(
        f"缺少 FLUX.2 组件 {name}，请放置到 models/gguf/ 或 sd_cpp/models/（见 docs/27、docs/26）"
    )


_DEFAULT_DIFFUSION = _pick("flux-2-klein-9b-Q8_0.gguf")
_DEFAULT_LLM = _pick("Qwen3-8B-Q4_K_M.gguf")
_DEFAULT_VAE = _pick("flux2-vae.safetensors")


class Flux2KleinUtil(SdCppUtil):
    """FLUX.2 [klein] 9B (GGUF/sd.cpp) 推理封装。

    Args（GGUF 专属）:
        diffusion_model / llm / vae: 覆盖默认 GGUF 组件路径（默认指向 models/gguf）
        cli_path: sd-cli.exe 路径（默认 sd_cpp/bin/sd-cli.exe）
        device / cpu_offload: 推理设备与显存策略
        default_steps: 默认采样步数（FLUX.2 klein 建议 4~20）
        default_cfg_scale: 默认 CFG（None = 不传，用 sd.cpp 内置）
        output_root: 输出根目录（默认项目 outputs/）

    兼容旧签名（保留但忽略或映射）:
        model_path: 旧 diffusers 模型目录；GGUF 模式下忽略
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
        vae: Optional[Union[str, Path]] = None,
        cli_path: Optional[Union[str, Path]] = None,
        default_steps: int = 20,
        default_cfg_scale: Optional[float] = None,
        extra_args: Optional[dict] = None,
    ) -> None:
        super().__init__(
            diffusion_model=diffusion_model or _DEFAULT_DIFFUSION,
            llm=llm or _DEFAULT_LLM,
            llm_vision=None,  # FLUX.2 无需视觉塔（参考图由 sd.cpp 直接处理）
            vae=vae or _DEFAULT_VAE,
            cli_path=cli_path,
            device=device,
            cpu_offload=cpu_offload,
            default_steps=default_steps,
            default_cfg_scale=default_cfg_scale,
            output_root=output_root,
            extra_args=extra_args,
        )
