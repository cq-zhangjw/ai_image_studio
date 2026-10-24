"""复杂构图测试：探测 Qwen-Image-2.1 的构图复杂度上限。

3 组：①数据架构信息图（密集文字+层级结构）②复杂场景构图（多元素多层次）
      ③信息密集海报（多元素+多行文字）
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.qwen_21_util import QwenImage21Util

CASES = [
    (
        "数据架构信息图(横版)",
        1536,
        864,
        (
            "Professional data architecture infographic for a smart agriculture platform, "
            "multi-layer system diagram poster. Top layer: data sources with labels 数据源 "
            "(internal network, internet, e-government network). Middle layers: boxes labeled "
            "数据库 / 数据中台 / 数据资产 connected by arrows downward. "
            "Bottom layer: output applications labeled 数据服务 / 大数据分析 / 应用支撑. "
            "Clean blue tech style, glowing connection lines, clear hierarchy, "
            "modern business presentation, high quality vector-like infographic."
        ),
    ),
    (
        "复杂场景构图(横版)",
        1536,
        864,
        (
            "Bird's eye view of a massive city transport hub at night, multi-level elevated "
            "highways interweaving in complex curves, streams of car headlights and taillights "
            "forming long light trails, metro lines and bridges crossing a wide river, "
            "dense skyscrapers with glowing windows, harbor cranes and ships in the distance, "
            "cinematic aerial photography, extremely detailed complex composition."
        ),
    ),
    (
        "信息密集海报(竖版)",
        1024,
        1536,
        (
            "Busy summer night market street food festival poster, dense layered composition: "
            "rows of food stalls with steaming noodles, grilled skewers, dumplings, juice stands, "
            "colorful hanging lanterns and bunting flags, lively crowd, food price tags, "
            "main title 夏祭り, vibrant warm colors, commercial festival poster design, "
            "high detail, complex layout."
        ),
    ),
]

SEED = 2026


def main():
    util = QwenImage21Util()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = util.output_root / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"[complex composition test] {stamp}", ""]
    from PIL import Image

    for idx, (name, w, h, prompt) in enumerate(CASES, 1):
        print(f"\n=== [{idx}/3] {name} ({w}x{h}) ===")
        result = util.text_to_image(
            prompt=prompt,
            width=w,
            height=h,
            num_inference_steps=20,
            seed=SEED,
        )
        dst = run_dir / f"output_{idx:02d}.png"
        Image.open(result["images"][0]).save(dst)
        print(f"  saved {dst}")
        lines.append(f"[{idx}] {name}")
        lines.append(f"    prompt: {prompt}")
        lines.append(f"    output: {dst.name}")
        lines.append("")

    (run_dir / "input_prompt.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成 -> {run_dir}")


if __name__ == "__main__":
    main()
