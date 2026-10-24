"""UI 原型图生成测试：Qwen-Image-2.1 直出各功能页高保真原型。

用法：
    & ".venv\Scripts\python.exe" tests\generate_ui_prototypes.py

输出：outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_0X.png（每功能一张）
"""

import datetime
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.qwen_21_util import QwenImage21Util  # noqa: E402

# 统一深色专业工具风格，各功能页布局分区
STYLE = (
    "专业AI图像工作站桌面软件界面设计稿，深色主题，背景色#0f1419，面板色#1a222b，"
    "主按钮蓝色#3b82f6，圆角卡片、细边框、现代无衬线中文界面，布局为左侧窄导航栏+中间主操作区+右侧结果区，"
    "干净留白，高保真UI设计图，横屏16:9，无摄影元素，无真实人物"
)

CASES = [
    (
        "text_to_image",
        STYLE
        + "。左侧导航栏：顶部Logo「AI图像工作站」，下方四个导航项「文生图(高亮选中)」「编辑」「放大」「扩图」。"
        "中间操作卡片：模型选择下拉框(显示Qwen-Image-2.1)、大文本框(右上角有蓝色「AI优化」胶囊按钮)、"
        "负面提示词输入框、比例按钮组(1:1/2:3/3:4/16:9/9:16)、步数与种子数字输入、底部蓝色「开始生成」大按钮。"
        "右侧画廊区：展示两张竖向海报缩略图，带输出文件列表。",
    ),
    (
        "edit",
        STYLE
        + "。左侧导航栏「文生图」「编辑(高亮选中)」「放大」「扩图」。"
        "中间操作区：左侧上传原图缩略图(一只狐狸图片)，标注方式选择「画圈/涂鸦/Mask」三个选项按钮，"
        "编辑说明大文本框(右上角蓝色「AI优化」胶囊按钮)、「区域合成」开关、羽化滑杆、蓝色「开始编辑」按钮。"
        "右侧展示「编辑前vs编辑后」左右对比预览图。",
    ),
    (
        "upscale",
        STYLE
        + "。左侧导航栏「文生图」「编辑」「放大(高亮选中)」「扩图」。"
        "中间操作卡片：输入目录路径输入框+「浏览」按钮、目标面积下拉(1920x1080/2560x1440/Auto)、"
        "「DIT显存优化」开关、蓝色「批量放大」大按钮、下方绿色进度条。"
        "右侧文件列表表格：文件名/原尺寸/目标尺寸/状态(成功绿色对勾)/耗时，下方两张放大结果缩略图。",
    ),
    (
        "outpaint",
        STYLE
        + "。左侧导航栏「文生图」「编辑」「放大」「扩图(高亮选中)」。"
        "中间操作区：居中展示上传的原图缩略图(雪山极光风景)，四周有「上/下/左/右/四周」方向选择按钮(选中态蓝色高亮)，"
        "扩图描述文本框、蓝色「开始扩图」按钮。右侧展示原图与扩图结果16:9宽幅对比。",
    ),
    (
        "prompt_modal",
        STYLE
        + "。中央模态弹窗「提示词优化」：顶部标题栏+右上角关闭按钮+模型徽标「qwen3.5-4b」与耗时「7.3s」，"
        "中间左右分栏：左侧「原文」只读面板(短文本)，右侧「优化结果」可编辑大文本域(长段落文本)，"
        "底部三个按钮「复制」「关闭」「应用回填(蓝色主按钮)」，背景半透明遮罩。",
    ),
]


def main() -> None:
    out_dir = ROOT / "outputs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    util = QwenImage21Util()
    with (out_dir / "input_prompt.txt").open("w", encoding="utf-8") as f:
        f.write("ui_prototypes test (qwen-image-2.1)\n")

    for i, (name, prompt) in enumerate(CASES, start=1):
        print(f"[{i}/{len(CASES)}] {name} ...")
        t0 = time.perf_counter()
        res = util.text_to_image(
            prompt,
            width=1024,
            height=1536,
            num_inference_steps=20,
            seed=20261022,
            output_dir=out_dir,
        )
        dt = time.perf_counter() - t0
        first = res["images"][0]
        img = Image.open(first) if isinstance(first, (str, Path)) else first
        out_path = out_dir / f"output_{i:02d}_{name}.png"
        img.save(out_path)
        print(f"  saved {out_path.name} in {dt:.1f}s")
        with (out_dir / "input_prompt.txt").open("a", encoding="utf-8") as f:
            f.write(f"{name}\t{prompt[:80]}...\telapsed={dt:.1f}s\n")

    print(f"\n完成，输出目录: {out_dir}")


if __name__ == "__main__":
    main()
