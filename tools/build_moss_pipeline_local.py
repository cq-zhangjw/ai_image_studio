"""生成注入版 MOSS pipeline：本地拷贝 pipeline_moss_image.py 并注入步级进度回调。

用法：python tools/build_moss_pipeline_local.py
产出：utils/moss_pipeline_local.py（供 moss_util 使用）
"""
from pathlib import Path

SRC = Path(r"E:\my_projects\qwen-2.1\_moss_pipeline.py")
DST = Path(r"E:\my_projects\qwen-2.1\utils\moss_pipeline_local.py")

text = SRC.read_text(encoding="utf-8")

# 1. 签名注入 callback_on_step_end
old_sig = (
    "                 slg_start=0.0, slg_stop=1.0):"
)
new_sig = (
    "                 slg_start=0.0, slg_stop=1.0,\n"
    "                 callback_on_step_end=None):"
)
assert old_sig in text, "signature anchor not found"
text = text.replace(old_sig, new_sig)

# 2. 循环体注入回调调用（scheduler.step 之后、循环末尾）
old_loop = (
    "            latents = self.scheduler.step(prediction, timestep, latents, return_dict=False)[0]\n"
    "        if output_type == 'latent':"
)
new_loop = (
    "            latents = self.scheduler.step(prediction, timestep, latents, return_dict=False)[0]\n"
    "            if callback_on_step_end is not None:\n"
    "                callback_on_step_end(step_index + 1, num_steps)\n"
    "        if output_type == 'latent':"
)
assert old_loop in text, "loop anchor not found"
text = text.replace(old_loop, new_loop)

# 3. 模块头注记
header = (
    "# Local patched copy of OpenMOSS-Team/MOSS-Image-SFT pipeline_moss_image.py (Apache 2.0).\n"
    "# Patch: added callback_on_step_end(step, total) progress hook for Web SSE progress.\n"
)
text = header + text

DST.write_text(text, encoding="utf-8")
print(f"written {DST} ({len(text)} chars)")
