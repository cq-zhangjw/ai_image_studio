# -*- coding: utf-8 -*-
"""Lumina-Image-2.0 冒烟测试：加载 + 1024x1024 出图，记录耗时与显存。"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.lumina_util import LuminaImageUtil

def main():
    u = LuminaImageUtil()
    t0 = time.time()
    r = u.text_to_image(
        prompt="一只橘猫坐在窗台上，黄昏金色光线，逆光剪影，摄影写实",
        width=1024,
        height=1024,
        num_inference_steps=30,
        seed=42,
    )
    elapsed = time.time() - t0
    print(f"[smoke] images: {r['images']}")
    print(f"[smoke] record: {r.get('record_path', '')}")
    print(f"[smoke] elapsed: {elapsed:.2f}s")
    if "stats" in r:
        print(f"[smoke] stats: {r['stats']}")

if __name__ == "__main__":
    main()
