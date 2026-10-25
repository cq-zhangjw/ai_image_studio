"""stable-diffusion.cpp (GGUF) 通用 CLI 推理封装。

通过调用官方预编译的 `sd-cli.exe`（子进程）执行任意 GGUF 模型推理，
零 torch / transformers 依赖，天然规避 sd-server HTTP 路由在 Windows
预编译版上的崩溃问题。

支持模型形态：
    - 文生图        （无参考图）
    - 单图编辑      （1 张参考图 `-r`）
    - 多图融合      （多张参考图 `-r`，Qwen-Image 系列最多 10 张，FLUX 系列按模型支持）

输出约定（与 utils/qwen_21_util.py 保持一致）：
    outputs/<YYYYMMDD_hhmmss>/
        ├── input_prompt.txt   # 本次生成的提示词（及参数记录）
        └── output_01.png      # 生成图片

用法示例：
    from utils.sd_cpp_util import SdCppUtil

    util = SdCppUtil(
        diffusion_model="sd_cpp/models/qwen_image_2.1-Q8_0.gguf",
        llm="sd_cpp/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf",
        llm_vision="sd_cpp/models/mmproj-Qwen3VL-8B-Instruct-F16.gguf",
        vae="sd_cpp/models/qwen_image_2.1_vae_bf16.safetensors",
        default_cfg_scale=2.2,
    )
    out = util.text_to_image("a red fox in the snow", seed=42)
    out = util.edit_image("merge both images", images=["a.png", "b.png"])

进度说明：
    sd-cli 不输出逐 denoise step 的文本日志，因此 progress_callback 的
    语义为「完成时回调 (total, total)」；如需真实中途进度，可启用
    preview 模式（见 generate 的 preview_interval 参数）。
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"

# 已知 GGUF 组件文件名 -> 自动发现用（按 key 提供给 _auto_model_paths）
# 模型目录统一为 sd_cpp/models 与 models/gguf（FLUX.2 相关已迁移至 models/gguf）
KNOWN_MODEL_FILES: dict[str, List[str]] = {
    "diffusion_model": [
        "qwen_image_2.1-Q8_0.gguf",
        "qwen_image_2.1-Q4_K.gguf",
        "flux-2-klein-9b-Q8_0.gguf",
    ],
    "llm": [
        "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
        "Qwen3-8B-Q4_K_M.gguf",
    ],
    "llm_vision": ["mmproj-Qwen3VL-8B-Instruct-F16.gguf"],
    "vae": [
        "qwen_image_2.1_vae_bf16.safetensors",
        "flux2-vae.safetensors",
    ],
}

# 自动发现搜索目录（按优先级）：新模型统一放 models/gguf，qwen 系仍在 sd_cpp/models
_MODEL_SEARCH_DIRS = [
    _PROJECT_ROOT / "models" / "gguf",
    _PROJECT_ROOT / "sd_cpp" / "models",
]

_RE_SAMPLING_MS = re.compile(r"sampling completed, taking\s+([\d.]+)s")
_RE_GENERATE_MS = re.compile(r"generate_image completed in\s+([\d.]+)s")


class SdCppUtil:
    """stable-diffusion.cpp 通用推理封装（子进程模式，无状态）。"""

    def __init__(
        self,
        diffusion_model: Optional[Union[str, Path]] = None,
        llm: Optional[Union[str, Path]] = None,
        llm_vision: Optional[Union[str, Path]] = None,
        vae: Optional[Union[str, Path]] = None,
        cli_path: Optional[Union[str, Path]] = None,
        device: str = "cuda",
        cpu_offload: bool = False,
        default_steps: int = 20,
        default_cfg_scale: Optional[float] = None,
        output_root: Union[str, Path] = _DEFAULT_OUTPUT_ROOT,
        extra_args: Optional[dict] = None,
    ) -> None:
        """初始化。

        Args:
            diffusion_model: 主扩散模型 GGUF 路径；None 时在 sd_cpp/models 自动发现
            llm: 文本编码器 GGUF 路径（Qwen-Image 系需 Qwen3-VL，FLUX 系需 Qwen3-4B）
            llm_vision: 视觉塔 mmproj（编辑/多图参考必需；纯文本编码器可省略）
            vae: VAE safetensors 路径（必须与主模型 latent 通道配套）
            cli_path: sd-cli.exe 路径；None 时默认 sd_cpp/bin/sd-cli.exe
            device: "cuda" 或 "cpu"（cuda 自动 fit，20G 显存下 Q8 可全载）
            cpu_offload: 是否加 --offload-to-cpu（显存紧张时使用）
            default_steps: 默认采样步数
            default_cfg_scale: 默认 CFG；None 时不传（用 CLI 内置默认）
            output_root: 输出根目录
            extra_args: 追加固定 CLI 参数 dict（如 {"--batch-count": 1}）
        """
        self.sd_cpp_root = _PROJECT_ROOT / "sd_cpp"
        self.diffusion_model = self._resolve_component(
            "diffusion_model", diffusion_model
        )
        self.llm = self._resolve_component("llm", llm)
        self.llm_vision = self._resolve_component("llm_vision", llm_vision)
        self.vae = self._resolve_component("vae", vae)
        self.cli_path = Path(cli_path) if cli_path else self.sd_cpp_root / "bin" / "sd-cli.exe"
        self.device = device
        self.cpu_offload = cpu_offload
        self.default_steps = default_steps
        self.default_cfg_scale = default_cfg_scale
        self.output_root = Path(output_root)
        self.extra_args = dict(extra_args or {})
        if not self.cli_path.exists():
            raise FileNotFoundError(f"sd-cli 不存在: {self.cli_path}")

    # ------------------------------------------------------------------ #
    # 内部：路径解析
    # ------------------------------------------------------------------ #
    def _resolve_component(
        self, key: str, value: Optional[Union[str, Path]]
    ) -> Optional[str]:
        if value is not None:
            p = Path(value)
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            return str(p)
        # 自动发现：models/gguf 与 sd_cpp/models（按 _MODEL_SEARCH_DIRS 顺序）
        for model_dir in _MODEL_SEARCH_DIRS:
            for name in KNOWN_MODEL_FILES.get(key, []):
                cand = model_dir / name
                if cand.exists():
                    return str(cand)
        return None

    def _require_components(self) -> List[str]:
        missing = [k for k in ("diffusion_model", "llm", "vae") if getattr(self, k) is None]
        if missing:
            raise FileNotFoundError(
                f"缺少必需组件: {missing}，请显式传入或在 sd_cpp/models 放置对应文件"
            )
        return [self.diffusion_model, self.llm, self.vae]

    # ------------------------------------------------------------------ #
    # 内部：命令构建 / 运行 / 日志解析
    # ------------------------------------------------------------------ #
    def _build_command(
        self,
        prompt: str,
        images: Optional[List[str]],
        width: int,
        height: int,
        steps: int,
        seed: Optional[int],
        negative_prompt: Optional[str],
        cfg_scale: Optional[float],
        output_path: Path,
        extra: dict,
    ) -> List[str]:
        self._require_components()
        cmd = [str(self.cli_path)]
        cmd += ["--diffusion-model", self.diffusion_model]
        cmd += ["--llm", self.llm]
        if self.llm_vision:
            cmd += ["--llm_vision", self.llm_vision]
        cmd += ["--vae", self.vae]
        if self.cpu_offload:
            cmd += ["--offload-to-cpu"]
        cmd += ["-p", prompt]
        cmd += ["-H", str(int(height)), "-W", str(int(width))]
        cmd += ["--steps", str(int(steps))]
        if cfg_scale is not None:
            cmd += ["--cfg-scale", str(float(cfg_scale))]
        if seed is not None:
            cmd += ["--seed", str(int(seed))]
        if negative_prompt:
            cmd += ["-n", negative_prompt]
        for img in images or []:
            cmd += ["-r", img]  # 参考图（单图编辑 / 多图融合共用）
        for k, v in {**self.extra_args, **extra}.items():
            cmd += [str(k), str(v)]
        cmd += ["-o", str(output_path)]
        return cmd

    @staticmethod
    def _parse_log(text: str) -> dict:
        m_s = _RE_SAMPLING_MS.search(text)
        m_g = _RE_GENERATE_MS.search(text)
        return {
            "sampling_seconds": float(m_s.group(1)) if m_s else None,
            "generate_seconds": float(m_g.group(1)) if m_g else None,
        }

    def _run_cli(
        self,
        cmd: List[str],
        progress_callback: Optional[Callable[[int, int], None]],
        total_steps: int,
    ) -> str:
        """启动子进程并捕获合并输出；可选 progress 回调。"""
        env = os.environ.copy()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        assert proc.stdout is not None
        chunks: List[str] = []
        for line in proc.stdout:
            chunks.append(line)
        proc.wait()
        text = "".join(chunks)
        if proc.returncode != 0:
            raise RuntimeError(
                f"sd-cli 退出码 {proc.returncode}:\n"
                + "\n".join(text.splitlines()[-25:])
            )
        if progress_callback is not None:
            progress_callback(total_steps, total_steps)
        return text

    # ------------------------------------------------------------------ #
    # 内部：输出落盘（与 qwen_21_util 保持同构）
    # ------------------------------------------------------------------ #
    def _make_run_dir(self, run_dir: Optional[Union[str, Path]]) -> Path:
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
        images: Optional[List[Image.Image]],
        params: Optional[dict],
    ) -> Path:
        lines = ["[prompt]", prompt, ""]
        if images:
            lines += [
                "[input images]",
                "\n".join(f"- {i}: {img.size} mode={img.mode}" for i, img in enumerate(images)),
                "",
            ]
        if params:
            lines += ["[params]", "\n".join(f"{k}: {v}" for k, v in params.items()), ""]
        record = run_dir / "input_prompt.txt"
        record.write_text("\n".join(lines), encoding="utf-8")
        return record

    # ------------------------------------------------------------------ #
    # 对外 API
    # ------------------------------------------------------------------ #
    def generate(
        self,
        prompt: str,
        images: Optional[Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]]] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        cfg_scale: Optional[float] = None,
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "output",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **extra,
    ) -> dict:
        """统一生成入口（签名对齐 utils/qwen_21_util.py 的 generate）。

        - images 为 None        -> 文生图
        - images 为单图/多图    -> 编辑/多图融合（全部作为参考图 `-r` 传入）
        - width/height 为 None 时：默认 1024；编辑模式继承第一张输入图尺寸
        - cfg_scale 为 None 时使用构造时的 default_cfg_scale

        progress_callback(step, total)：sd-cli 无逐 step 文本进度，默认
        仅在完成时回调 (total, total)；如需中途预览进度，传
        preview_interval=N（配合 --preview 启用，见文档）。

        返回 {"run_dir": Path, "prompt_record": Path, "images": List[Path]}
        """
        # 参考图规范化（与旧 util 一致：转 RGB、继承输入图尺寸）
        input_imgs: List[Image.Image] = []
        ref_paths: List[str] = []
        if images is not None:
            img_list = images if isinstance(images, (list, tuple)) else [images]
            for item in img_list:
                if isinstance(item, (str, Path)):
                    p = str(item)
                    ref_paths.append(p)
                    input_imgs.append(Image.open(p).convert("RGB"))
                else:
                    img = item.convert("RGB")
                    input_imgs.append(img)
                    # PIL 对象落临时文件供 CLI 读取
                    tmp = self.output_root / "_sd_cpp_tmp" / f"ref_{len(ref_paths)}.png"
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    img.save(tmp)
                    ref_paths.append(str(tmp))
            if width is None and height is None:
                w, h = input_imgs[0].size
                width, height = w, h

        if width is None:
            width = 1024
        if height is None:
            height = 1024
        steps = self.default_steps if num_inference_steps is None else int(num_inference_steps)
        cfg = self.default_cfg_scale if cfg_scale is None else cfg_scale

        run_dir = self._make_run_dir(output_dir)
        out_path = run_dir / f"{prefix}_01.png"

        # 可选预览进度（preview_interval>0 时启用）
        preview_interval = int(extra.pop("preview_interval", 0) or 0)
        cmd_extra = dict(extra)
        if preview_interval > 0:
            cmd_extra["--preview"] = "vae"
            cmd_extra["--preview-interval"] = str(preview_interval)
            cmd_extra["--preview-path"] = str(run_dir / f"{prefix}_preview_%03d.png")

        cmd = self._build_command(
            prompt=prompt,
            images=ref_paths,
            width=width,
            height=height,
            steps=steps,
            seed=seed,
            negative_prompt=negative_prompt,
            cfg_scale=cfg,
            output_path=out_path,
            extra=cmd_extra,
        )

        t_start = time.perf_counter()
        log_text = self._run_cli(cmd, progress_callback, steps)
        elapsed = time.perf_counter() - t_start
        timing = self._parse_log(log_text)

        params = {
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "seed": seed,
            "cfg_scale": cfg,
            "model": self.diffusion_model,
            "backend": "stable-diffusion.cpp (sd-cli)",
            "device": self.device,
            "cpu_offload": self.cpu_offload,
            "elapsed_seconds": round(elapsed, 2),
            "steps_per_second": round(steps / elapsed, 2) if elapsed else None,
        }
        if timing.get("sampling_seconds"):
            params["sampling_seconds"] = round(timing["sampling_seconds"], 2)
        record = self._save_prompt_record(run_dir, prompt, input_imgs or None, params)
        saved = [out_path] if out_path.exists() else []
        return {"run_dir": run_dir, "prompt_record": record, "images": saved}

    def text_to_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: Optional[int] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **kwargs,
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
            **kwargs,
        )

    def edit_image(
        self,
        prompt: str,
        image: Union[str, Path, Image.Image, List[Union[str, Path, Image.Image]]],
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        **kwargs,
    ) -> dict:
        """图像编辑 / 多图融合（单图或列表，全部作为参考图）。"""
        return self.generate(
            prompt=prompt,
            images=image,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=output_dir,
            **kwargs,
        )

    def reset(self) -> None:
        """子进程模式无持久状态，保留以兼容旧接口（no-op）。"""
        return None

    @staticmethod
    def gpu_memory_info() -> str:
        """返回 nvidia-smi 显存快照（不依赖 torch）。"""
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            used_mb, total_mb = [int(x) for x in out.stdout.strip().split(",")[:2]]
            return f"used={used_mb}MiB total={total_mb}MiB"
        except Exception:
            return "nvidia-smi not available"


def aspect_size(ratio: str) -> tuple[int, int]:
    """按官方宽高比表返回 (width, height)。"""
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"unsupported ratio {ratio!r}, choose from {list(ASPECT_RATIOS)}")
    return ASPECT_RATIOS[ratio]


# 官方推荐宽高比（Qwen-Image-2.1 原生 2K，与 qwen_21_util 一致）
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}
