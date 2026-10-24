"""ERNIE-Image-INT8 冒烟测试：加载 + 小图生成（512x512, 10 步）。"""
import sys
import time
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT))
sys.path.insert(0, str(_PROJECT / "utils"))

from utils.ernie_util import ErnieImageUtil  # noqa: E402

MODEL = _PROJECT / "models" / "ERNIE-Image-INT8"


def main():
    t0 = time.perf_counter()
    u = ErnieImageUtil(model_path=str(MODEL), cpu_offload=True)
    print(f"[smoke] init {time.perf_counter() - t0:.1f}s, loading pipe...")
    r = u.text_to_image(
        prompt="一只橘猫坐在窗台上，黄昏金色光线，逆光剪影，摄影写实",
        width=512,
        height=512,
        num_inference_steps=10,
        seed=42,
    )
    print("[smoke] images:", [str(p) for p in r["images"]])
    print("[smoke] record:", r["prompt_record"])
    print("[smoke] gpu:", u.gpu_memory_info())
    print("[smoke] elapsed:", r["elapsed_seconds"])


if __name__ == "__main__":
    main()
