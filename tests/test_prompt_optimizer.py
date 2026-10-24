"""提示词优化 LLM 功能测试：Qwen3.5-4B GPU 推理 + 卸载方案。

用法：
    & ".venv\Scripts\python.exe" tests\test_prompt_optimizer.py

输出到 outputs/YYYYMMDD_hhmmss/input_prompt.txt + output_xx.txt，并打印耗时。
"""

import datetime
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.llm_prompt_optimizer import PromptOptimizer  # noqa: E402

MODEL_DIR = ROOT / "models" / "Qwen3.5-4B-Instruct"

CASES = [
    ("zh_short", "auto", "夏日冰饮节海报"),
    ("en_short", "auto", "a red fox in snowy forest at dusk"),
    ("zh_poster", "z-image-turbo", "中秋月饼礼盒主视觉：国风插画、玉兔与满月、烫金工艺感"),
    ("en_poster", "flux2-klein-4b", "futuristic cyberpunk city street at night, neon signs"),
]


def main() -> None:
    out_dir = ROOT / "outputs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("模型加载（GPU BF16，懒加载单例）")
    t0 = time.perf_counter()
    opt = PromptOptimizer(model_path=str(MODEL_DIR))
    _ = opt.optimize("test warmup", max_new_tokens=8)
    load_s = time.perf_counter() - t0
    print(f"  加载+预热: {load_s:.1f}s  显存: {opt.gpu_memory_info()}")

    # 卸载测试
    print("  卸载测试: unload() ->", end=" ")
    opt.unload()
    print(f"loaded={opt.loaded}  显存释放")

    # 重新加载（模拟"优化请求到达时 LLM 未加载"场景）
    t0 = time.perf_counter()
    _ = opt.optimize("test warmup2", max_new_tokens=8)
    load2_s = time.perf_counter() - t0
    print(f"  二次加载+预热: {load2_s:.1f}s")

    with (out_dir / "input_prompt.txt").open("w", encoding="utf-8") as f:
        f.write("prompt_optimizer test\n")
        f.write(f"model=Qwen3.5-4B-Instruct load_seconds={load_s:.1f} reload_seconds={load2_s:.1f}\n")

    for name, target, prompt in CASES:
        print(f"\n[{name}] target={target}")
        print(f"  原文: {prompt}")
        t0 = time.perf_counter()
        r = opt.optimize(prompt, target_model=target)
        dt = time.perf_counter() - t0
        print(f"  优化 ({dt:.2f}s):")
        print(f"  {r['optimized'][:300]}")
        (out_dir / f"output_{name}.txt").write_text(
            f"target={target}\noriginal={prompt}\nelapsed={r['elapsed_seconds']}s\n\n{r['optimized']}\n",
            encoding="utf-8",
        )
        with (out_dir / "input_prompt.txt").open("a", encoding="utf-8") as f:
            f.write(f"{name}\ttarget={target}\tprompt={prompt}\telapsed={dt:.2f}s\n")

    print("\n显存峰值: " + opt.gpu_memory_info())
    print(f"输出目录: {out_dir}")


if __name__ == "__main__":
    main()
