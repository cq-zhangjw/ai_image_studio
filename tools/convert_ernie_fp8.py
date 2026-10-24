"""ERNIE-Image-Turbo 一键构建脚本：FP8 仓库 -> BF16 标准 diffusers 仓库。

背景（docs/17）：szwagros/ernie-image-turbo-fp8 仓库有 3 个坑：
1. safetensors 文件名非标准（ernie_transformer_fp8.safetensors / ernie_text_encoder_fp8.safetensors）
   -> 需复制为 diffusion_pytorch_model.safetensors（diffusers）与 model.safetensors（transformers）
2. 权重为 PyTorch 原生 FP8 动态量化格式（weight._data + weight._scale），diffusers/transformers
   不支持该格式（加载时权重被忽略 -> 随机初始化），需反量化为 bf16
3. model_index.json 声明了 pe（prompt encoder），但仓库未带权重 -> 需移除声明

本脚本完成全部修复，输出标准 bf16 diffusers 仓库（可直接 from_pretrained 加载）。

用法（模型已下载时）：
    python tools/convert_ernie_fp8.py
输出：models/ERNIE-Image-Turbo-BF16/（标准结构 + 标准文件名 + bf16 权重）
"""

import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

SRC = Path(r"E:\my_projects\qwen-2.1\models\ERNIE-Image-Turbo-FP8")
DST = Path(r"E:\my_projects\qwen-2.1\models\ERNIE-Image-Turbo-BF16")

# 需要转换并重命名的权重文件（源 -> 目标）
WEIGHT_FILES = [
    ("transformer/ernie_transformer_fp8.safetensors", "transformer/diffusion_pytorch_model.safetensors"),
    ("text_encoder/ernie_text_encoder_fp8.safetensors", "text_encoder/model.safetensors"),
    ("vae/diffusion_pytorch_model.safetensors", "vae/diffusion_pytorch_model.safetensors"),
]

# 原样复制的非权重文件
COPY_FILES = [
    "model_index.json", "scheduler/scheduler_config.json",
    "text_encoder/config.json", "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json", "transformer/config.json", "vae/config.json",
]


def convert_file(src_path: Path, dst_path: Path) -> dict:
    """读 FP8 safetensors，反量化 _data*_scale -> bf16，其余键保留，写标准文件。"""
    print(f"  reading {src_path.name} ({src_path.stat().st_size/1e9:.1f}GB) ...")
    sd = load_file(str(src_path))
    out: dict = {}
    n_fp8 = 0
    for key, tensor in sd.items():
        if key.endswith("._data"):
            base = key[: -len("._data")]
            scale_key = base + "._scale"
            scale = sd.get(scale_key)
            if scale is None:
                continue
            # fp8 反量化：value = data.float() * scale
            w = tensor.float() * scale.float()
            out[base] = w.to(torch.bfloat16)
            n_fp8 += 1
        elif key.endswith("._scale"):
            continue  # 已并入对应 _data
        else:
            # 非量化权重（norm/bias/embedding 等）原样转 bf16
            out[key] = tensor.to(torch.bfloat16) if tensor.dtype.is_floating_point else tensor
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    save_file(out, str(dst_path))
    print(f"  wrote {dst_path.name} ({dst_path.stat().st_size/1e9:.1f}GB), fp8 tensors: {n_fp8}")
    return {"file": dst_path.name, "fp8_tensors": n_fp8, "total_tensors": len(out)}


def fix_model_index(dst: Path) -> None:
    """移除 pe / pe_tokenizer 组件声明（仓库未带权重，保留会导致加载失败）。"""
    p = dst / "model_index.json"
    d = json.load(open(p, encoding="utf-8"))
    removed = []
    for key in ("pe", "pe_tokenizer"):
        if key in d:
            d.pop(key)
            removed.append(key)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  model_index.json: removed {removed}")


def main() -> None:
    if not SRC.is_dir():
        sys.exit(f"source not found: {SRC}（请先下载 FP8 仓库到该目录，见 docs/17 §下载）")
    DST.mkdir(parents=True, exist_ok=True)
    report = []
    for rel_src, rel_dst in WEIGHT_FILES:
        src = SRC / rel_src
        if not src.exists():
            print(f"  SKIP missing {rel_src}")
            continue
        report.append(convert_file(src, DST / rel_dst))
    for rel in COPY_FILES:
        src = SRC / rel
        if src.exists():
            dst = DST / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    fix_model_index(DST)
    print("DONE:", report)


if __name__ == "__main__":
    main()
