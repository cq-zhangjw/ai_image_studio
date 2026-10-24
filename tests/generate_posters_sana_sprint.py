"""SANA-Sprint 1.6B 多语言海报生图测试：中 / 日 / 英 及混用（与 Qwen/FLUX2/Z-Image 同 CASES）。

统一主题：夏日冰饮促销海报（竖版 2:3，1024x1536）。
SANA-Sprint 参数：2 步 / guidance 4.5（官方推荐），支持中英 prompt。
注意：Sprint 不支持 negative prompt；官方声明无法渲染复杂可读文字——海报文字为本次观察重点。

运行（项目根目录）：
    .venv\\Scripts\\python.exe tests\\generate_posters_sana_sprint.py

输出：outputs/YYYYMMDD_hhmmss/
    ├── input_prompt.txt
    └── output_01.png ~ output_06.png
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.sana_sprint_util import SanaSprintUtil

# 视觉主体描述（与其他模型测试保持一致）
VISUAL = (
    "Professional advertising poster design for a summer ice drink festival. "
    "Fresh summer theme, vibrant gradient background in cyan and orange, "
    "ice cream cones and cups, fresh watermelon and orange slices, ice cubes splashing, "
    "sunny summer atmosphere, clean commercial typography layout, high quality, vertical poster."
)

# 6 组测试：语言 / 主标题 / 副标题
CASES = [
    ("中文", "夏日冰饮节", "冰爽一夏"),
    ("日文", "夏のアイス祭り", "ひんやりスイーツ"),
    ("英文", "SUMMER ICE FESTIVAL", "CHILL & REFRESH"),
    ("中英混用", "SUMMER ICE FESTIVAL", "夏日冰饮节"),
    ("中日混用", "夏のアイス祭り", "冰爽一夏"),
    ("英日混用", "ICE FESTIVAL", "夏の祭り"),
]

SEED = 2026
STEPS = 2
GUIDANCE = 4.5


def main():
    util = SanaSprintUtil()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = util.output_root / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"[poster test sana-sprint] {stamp}", ""]
    saved = []
    for idx, (lang, title, subtitle) in enumerate(CASES, 1):
        prompt = (
            f"The main title text reads: {title}. The subtitle text reads: {subtitle}. "
            f"{VISUAL}"
        )
        print(f"\n=== [{idx}/6] {lang}: {title} / {subtitle} ===")
        result = util.text_to_image(
            prompt=prompt,
            width=1024,
            height=1536,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE,
            seed=SEED,
        )
        img_path = result["images"][0]
        dst = run_dir / f"output_{idx:02d}.png"
        from PIL import Image
        Image.open(img_path).save(dst)
        saved.append(dst)
        lines.append(f"[{idx}] 语言: {lang}")
        lines.append(f"    prompt: {prompt}")
        lines.append(f"    output: {dst.name}")
        lines.append("")

    record = run_dir / "input_prompt.txt"
    record.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成：{len(saved)} 张海报 -> {run_dir}")
    for p in saved:
        print(f"  {p}")


if __name__ == "__main__":
    main()
