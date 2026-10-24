"""Qwen-Image-2.1 工具封装测试。

覆盖：
    - aspect_size 宽高比工具
    - text_to_image 文生图（输出结构：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png）
    - edit_image 图像编辑（单图输入，自动继承输入尺寸）

运行（项目根目录）：
    .venv\\Scripts\\python.exe -m pytest tests -v -s

说明：
    - session 级 fixture 共享一次模型加载（懒加载），文生图产物同时供编辑测试复用，
      整轮测试共 1 次文生图 + 1 次图像编辑，避免重复加载模型。
    - 显存策略：bf16 + CPU offload + VAE slicing/tiling，默认 1024x1024，适配 3080 20G。
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

# 保证可 import 项目根下的 utils 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.qwen_21_util import QwenImage21Util, aspect_size  # noqa: E402


@pytest.fixture(scope="session")
def util():
    """会话级共享实例：自动加载 models/Qwen-Image-2.1（存在则用本地，否则走 HF）。"""
    u = QwenImage21Util()
    print(f"\n[fixture] model_path={u.model_path} device={u.device}")
    yield u
    u.reset()  # 释放显存


@pytest.fixture(scope="session")
def generated_t2i(util):
    """文生图一次，供文生图断言与图像编辑测试复用。"""
    result = util.text_to_image(
        prompt="A red fox sitting in the snow under the aurora, cinematic lighting, high detail",
        width=1024,
        height=1024,
        num_inference_steps=20,
        seed=42,
    )
    print(f"\n[t2i] run_dir={result['run_dir']}")
    print(f"[t2i] images={result['images']}")
    return result


# --------------------------------------------------------------------------- #
# 单元：工具函数
# --------------------------------------------------------------------------- #
def test_aspect_size():
    assert aspect_size("1:1") == (2048, 2048)
    assert aspect_size("16:9") == (2752, 1536)
    with pytest.raises(ValueError):
        aspect_size("5:4")


# --------------------------------------------------------------------------- #
# 集成：文生图
# --------------------------------------------------------------------------- #
def test_text_to_image_output_structure(generated_t2i):
    """输出必须符合 outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.png。"""
    run_dir = generated_t2i["run_dir"]
    # 目录名形如 YYYYMMDD_hhmmss（14 位数字）
    parts = run_dir.name.split("_")
    assert len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 8
    assert parts[1].isdigit() and len(parts[1]) == 6

    prompt_record = generated_t2i["prompt_record"]
    assert prompt_record.name == "input_prompt.txt"
    text = prompt_record.read_text(encoding="utf-8")
    assert "A red fox sitting in the snow" in text  # prompt 已记录

    img_path = generated_t2i["images"][0]
    assert img_path.name.startswith("output_") and img_path.suffix == ".png"
    assert img_path.exists() and img_path.stat().st_size > 0

    img = Image.open(img_path)
    assert img.size == (1024, 1024)


# --------------------------------------------------------------------------- #
# 集成：图像编辑
# --------------------------------------------------------------------------- #
def test_image_edit(util, generated_t2i):
    """编辑文生图产物：应成功输出且自动继承输入尺寸。"""
    src = generated_t2i["images"][0]
    result = util.edit_image(
        prompt="Change the snowy background to a lush green meadow in spring, keep the fox",
        image=str(src),
        seed=123,
    )
    print(f"\n[edit] run_dir={result['run_dir']}")
    print(f"[edit] images={result['images']}")

    img_path = result["images"][0]
    assert img_path.exists() and img_path.stat().st_size > 0
    assert result["prompt_record"].exists()

@pytest.fixture(scope="session")
def multi_ref_images(util):
    """生成 3 张不同主体的参考图（768x768，15 steps），供多参考融合测试使用。"""
    prompts = [
        "A cute orange tabby cat sitting, studio lighting, plain gray background",
        "A happy golden retriever dog sitting, studio lighting, plain gray background",
        "A white rabbit sitting, studio lighting, plain gray background",
    ]
    paths = []
    for i, p in enumerate(prompts, 1):
        r = util.text_to_image(prompt=p, width=768, height=768, num_inference_steps=15, seed=100 + i)
        print(f"\n[ref{i}] {r['images'][0]}")
        paths.append(r["images"][0])
    return paths


# --------------------------------------------------------------------------- #
# 集成：多参考图融合
# --------------------------------------------------------------------------- #
def test_multi_reference_edit(util, multi_ref_images):
    """多参考图融合：3 张独立主体 -> 一张合照（Qwen-Image-2.1 最多支持 10 张）。"""
    assert len(multi_ref_images) == 3
    result = util.edit_image(
        prompt="These three animals are sitting together around a campfire in a forest at dusk, group photo style, all three fully visible",
        image=[str(p) for p in multi_ref_images],
        seed=200,
    )
    print(f"\n[multi-ref] run_dir={result['run_dir']}")
    print(f"[multi-ref] images={result['images']}")

    img_path = result["images"][0]
    assert img_path.exists() and img_path.stat().st_size > 0
    assert result["prompt_record"].exists()

    fused = Image.open(img_path)
    assert fused.size == (768, 768)  # 未指定宽高时继承第一张参考图尺寸

    text = result["prompt_record"].read_text(encoding="utf-8")
    assert "These three animals" in text
    assert "[input images]" in text
    assert text.count("- ") >= 3  # 记录了 3 张输入参考图

