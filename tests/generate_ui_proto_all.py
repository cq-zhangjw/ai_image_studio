"""UI 原型图生成（全功能版）：为 util 每个功能模块生成对应界面原型。

4 张：文生图（已完成）/ 图像编辑 / 图像放大 / 图像扩图 —— 统一设计语言。
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.qwen_21_util import QwenImage21Util

# 统一设计骨架（每张复用）
SKELETON = (
    "High-fidelity UI design mockup of a desktop AI image generation studio, "
    "widescreen 16:9 layout, modern dark theme with blue accent, professional product design. "
    "Top navigation bar: app logo with text 'AI 图像工作站' on the left, "
    "tabs '文生图', '图像编辑', '图像放大', '图像扩图' in the middle, settings and help icons on the right. "
    "Left sidebar: model selection card with two rows, row one 'Qwen-Image-2.1' with green badge '已加载', "
    "row two 'FLUX.2 [klein] 4B' with gray badge '已就绪'; below it a GPU status card titled 'GPU 状态' "
    "showing 'RTX 3080 20G' and a horizontal memory bar at 68% labeled '显存 13.6GB / 20GB'. "
    "Bottom status bar: '耗时 46.2s | 2.21 steps/s | 模型加载 21s'. "
    "Crisp clean interface, consistent spacing, rounded corners, high detail UI rendering."
)

CASES = [
    (
        "UI原型-图像编辑页",
        "the '图像编辑' tab is active highlighted in blue; "
        "main edit panel: left control column with an original image upload box "
        "showing a red fox night scene thumbnail and button '上传原图', "
        "annotation method selector with options '画圈' / '涂鸦' / 'Mask', "
        "a prompt input box with placeholder text, a feather slider, "
        "and a large primary button '开始编辑'. "
        "Right side: side-by-side before/after comparison, "
        "left panel labeled '原图' showing the red fox aurora scene, "
        "right panel labeled '结果' showing the same scene with a bright full moon added.",
    ),
    (
        "UI原型-图像放大页",
        "the '图像放大' tab is active highlighted in blue; "
        "main upscale panel: left control column with an input folder field '输入目录', "
        "an output folder field '输出目录', model dropdown 'Qwen-Image-2.1', "
        "target resolution dropdown '1920×1080', batch and single toggle buttons, "
        "and a large primary button '开始放大'. "
        "Right side: batch progress list with three file rows "
        "'output_01.png 完成', 'output_02.png 完成', 'output_03.png 处理中' with progress bars; "
        "below a before/after comparison of a cat photo, left side smaller and blurry, "
        "right side larger and sharper.",
    ),
    (
        "UI原型-图像扩图页",
        "the '图像扩图' tab is active highlighted in blue; "
        "main outpaint panel: left control column with an original image upload box, "
        "target ratio buttons '16:9' '9:16' '1:1', "
        "extend direction option chips '向左' '向右' '向上' '向下' '四周', "
        "a prompt input box, and a large primary button '开始扩图'. "
        "Right side: large preview showing the original square fox image on the left "
        "of a wide 16:9 canvas, with newly generated desert landscape extending to the right "
        "labeled '扩展区域', a subtle dashed line marking the original canvas boundary.",
    ),
]

SEED = 2026


def main():
    util = QwenImage21Util()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = util.output_root / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"[UI prototype - all features] {stamp}", ""]
    from PIL import Image

    for idx, (name, body) in enumerate(CASES, 1):
        prompt = SKELETON.replace(
            "the '文生图'", f"the active tab is"
        ) + " " + body
        # 修正：骨架里没有文生图 tab 高亮描述，直接拼接
        prompt = SKELETON + " " + body
        print(f"\n=== [{idx}/{len(CASES)}] {name} ===")
        result = util.text_to_image(
            prompt=prompt,
            width=1536,
            height=864,
            num_inference_steps=24,
            seed=SEED,
        )
        dst = run_dir / f"output_{idx:02d}.png"
        Image.open(result["images"][0]).save(dst)
        lines.append(f"[{idx}] {name}\n    output: {dst.name}\n    prompt: {prompt}\n")

    (run_dir / "input_prompt.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成 -> {run_dir}")


if __name__ == "__main__":
    main()
