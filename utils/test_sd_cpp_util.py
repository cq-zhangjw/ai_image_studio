# -*- coding: utf-8 -*-
"""sd_cpp_util / qwen_21_gguf_util 快速验证。"""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

t0 = time.perf_counter()
try:
    import torch  # noqa
    has_torch = True
except Exception:
    has_torch = False
import_sec = time.perf_counter() - t0
print(f"[0] 导入耗时 {import_sec:.2f}s, torch 可用={has_torch}")

from utils.qwen_21_gguf_util import QwenImage21Util
from utils.sd_cpp_util import SdCppUtil, aspect_size, ASPECT_RATIOS

print("[1] import 成功（无 torch 依赖）")
print(f"    aspect_size('16:9') = {aspect_size('16:9')}")
print(f"    ASPECT_RATIOS keys = {list(ASPECT_RATIOS)}")

util = QwenImage21Util()
print(f"[2] util 就绪 cli={util.cli_path.name}")

# --- 文生图（快速档：8 步） ---
print("[3] 文生图 768x768 8 步 ...")
r1 = util.text_to_image("a red fox in the snow", width=768, height=768,
                        num_inference_steps=8, seed=42)
print(f"    run_dir={r1['run_dir'].name}")
print(f"    prompt_record exists={r1['prompt_record'].exists()}")
print(f"    images={[p.name for p in r1['images']]} 存在={all(p.exists() for p in r1['images'])}")

# --- 单图编辑（1 张参考图） ---
print("[4] 单图编辑（换背景）8 步 ...")
r2 = util.edit_image("change the background to a beach at sunset",
                     image=str(ROOT.parent / "outputs" / "20261025_010213" / "_input_original.png"),
                     width=768, height=768, num_inference_steps=8, seed=7)
print(f"    images={[p.name for p in r2['images']]} 存在={all(p.exists() for p in r2['images'])}")

# --- 多图融合（2 张参考图） ---
print("[5] 多图融合（2 张 ref）8 步 ...")
r3 = util.edit_image(
    "merge both reference images into one coherent product scene",
    image=[
        str(ROOT.parent / "outputs" / "20261025_010213" / "_input_original.png"),
        str(ROOT.parent / "outputs" / "20261025_010213" / "_input_original_1.png"),
    ],
    width=768, height=768, num_inference_steps=8, seed=11,
)
print(f"    images={[p.name for p in r3['images']]} 存在={all(p.exists() for p in r3['images'])}")

# --- prompt_record 内容抽查 ---
print("[6] prompt_record 内容（r3）：")
print("    " + r3["prompt_record"].read_text(encoding="utf-8").replace("\n", "\n    "))

# --- 兼容性：旧签名参数透传 ---
print("[7] 旧签名构造（model_path 忽略、cpu_offload=False）...")
util_legacy = QwenImage21Util(model_path="ignored/legacy/path", device="cuda",
                              dtype=None, cpu_offload=False,
                              vae_slicing=True, vae_tiling=True)
print(f"    OK diffusion={Path(util_legacy.diffusion_model).name}")

print("[8] gpu_memory_info:", util.gpu_memory_info())
print("ALL OK")
