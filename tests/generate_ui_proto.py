"""UI 原型图生成：为 utils 工具集设计桌面端界面原型，交 Qwen-Image-2.1 渲染。"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.qwen_21_util import QwenImage21Util

CASES = [
    (
        "UI原型-文生图主界面",
        1536,
        864,
        (
            "High-fidelity UI design mockup of a desktop AI image generation studio, "
            "widescreen 16:9 layout, modern dark theme with blue accent, professional product design. "
            "Top navigation bar: app logo with text 'AI 图像工作站' on the left, settings and help icons on the right. "
            "Left sidebar: model selection card with two rows, row one 'Qwen-Image-2.1' with green badge '已加载', "
            "row two 'FLUX.2 [klein] 4B' with gray badge '已就绪'; below it a GPU status card titled 'GPU 状态' "
            "showing 'RTX 3080 20G' and a horizontal memory bar at 68% labeled '显存 13.6GB / 20GB'. "
            "Main workspace with tab bar: tabs '文生图', '图像编辑', '图像放大', '图像扩图', first tab active highlighted in blue. "
            "Text-to-image panel: left control column with a large prompt input box containing placeholder text, "
            "a smaller negative prompt field, aspect ratio dropdown '2:3', steps slider, seed input, "
            "and a large primary button '开始生成'. "
            "Right preview area: 2x2 grid of generated summer drink poster thumbnails, "
            "each with a small download icon, one cell shows a loading spinner with text '正在生成'. "
            "Bottom status bar: '耗时 46.2s | 2.21 steps/s | 模型加载 21s'. "
            "Crisp clean interface, consistent spacing, rounded corners, high detail UI rendering."
        ),
    ),
]

SEED = 2026


def main():
    util = QwenImage21Util()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = util.output_root / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"[UI prototype test] {stamp}", ""]
    from PIL import Image

    for idx, (name, w, h, prompt) in enumerate(CASES, 1):
        print(f"\n=== [{idx}/{len(CASES)}] {name} ({w}x{h}) ===")
        result = util.text_to_image(
            prompt=prompt,
            width=w,
            height=h,
            num_inference_steps=24,
            seed=SEED,
        )
        dst = run_dir / f"output_{idx:02d}.png"
        Image.open(result["images"][0]).save(dst)
        lines.append(f"[{idx}] {name}\n    prompt: {prompt}\n    output: {dst.name}\n")

    (run_dir / "input_prompt.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成 -> {run_dir}")


if __name__ == "__main__":
    main()
