"""批量生成 100 组随机提示词文生图（docs/14 §3）。

流程：
  1) 调 /api/prompt/random 批量生成 100 条 AI 提示词（分类/风格/文字轮换注入）
  2) 按分配表提交 text-to-image 任务（模型×尺寸×分类）
  3) 轮询 /api/tasks 直到全部终态，输出统计与报告

用法：
  .venv\\Scripts\\python.exe tools/batch_gen.py [--base http://127.0.0.1:8001]
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8001"

CATEGORIES = [
    "landscape", "portrait", "animal", "architecture", "food",
    "sci-fi", "fantasy", "retro", "minimal", "cyberpunk",
]
STYLES = [
    "水彩", "油画", "摄影写实", "国风水墨", "赛博霓虹", "极简留白",
    "蒸汽朋克", "吉卜力动画风", "黑白胶片", "浮世绘", "超现实", "暗黑哥特",
]
# 模型 -> 尺寸列表（保证成功率与尺寸覆盖）
MODEL_SIZES = {
    "qwen-image-2.1": [
        (1024, 1024), (1024, 1536), (896, 1216), (1536, 864), (864, 1536),
    ] * 8,  # 40 组，5 尺寸轮换
    "flux2-klein-4b": [
        (1024, 1024), (1024, 1536), (896, 1216), (1536, 864), (864, 1536),
    ] * 4,  # 20 组
    "z-image-turbo": [(1024, 1024)] * 10 + [(768, 1024)] * 10,
    "sana-sprint-1.6b": [(1024, 1024)] * 10 + [(768, 1024)] * 10,
}
MODEL_STEPS = {"qwen-image-2.1": 20, "flux2-klein-4b": 4, "z-image-turbo": 8, "sana-sprint-1.6b": 2}


def http_json(path: str, method: str = "GET", body=None, timeout: int = 600) -> dict:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def build_plan() -> list[dict]:
    """生成 100 组任务计划：模型/尺寸/分类/是否文字/风格。"""
    plan = []
    cat_i = 0
    for model, sizes in MODEL_SIZES.items():
        for size in sizes:
            with_text = False
            if model == "qwen-image-2.1":
                # qwen 40 组：前 30 组含文字，后 10 组无文字
                with_text = len([p for p in plan if p["model"] == model]) < 30
            plan.append(
                {
                    "model": model,
                    "width": size[0],
                    "height": size[1],
                    "category": CATEGORIES[cat_i % len(CATEGORIES)],
                    "with_text": with_text,
                    "style": STYLES[(cat_i // len(CATEGORIES)) % len(STYLES)],
                }
            )
            cat_i += 1
    return plan


def gen_prompts(plan: list[dict]) -> list[str]:
    """批量生成提示词：按 (分类, 文字) 分组调 random（count=5），减少 LLM 调用次数。"""
    groups: dict[tuple, list[int]] = {}
    for i, t in enumerate(plan):
        key = (t["category"], t["with_text"])
        groups.setdefault(key, []).append(i)

    prompts: list[str] = [""] * len(plan)
    for (cat, wt), idxs in groups.items():
        style = plan[idxs[0]]["style"]
        for start in range(0, len(idxs), 5):
            chunk = idxs[start : start + 5]
            n = len(chunk)
            try:
                r = http_json(
                    "/api/prompt/random",
                    "POST",
                    {"category": cat, "style": style, "with_text": wt, "count": n},
                )
                for j, it in enumerate(r.get("items", [])):
                    if j < len(chunk) and it.get("prompt"):
                        prompts[chunk[j]] = it["prompt"]
            except Exception as e:  # noqa: BLE001
                print(f"[gen] batch fail {cat}/{wt}: {e}")
            time.sleep(0.3)
    return prompts


def submit_all(plan: list[dict], prompts: list[str]) -> list[str]:
    """提交 100 个任务，返回 task_id 列表。"""
    ids = []
    for i, t in enumerate(plan):
        body = {
            "prompt": prompts[i] or f"a beautiful {t['category']} scene, {t['style']} style",
            "model": t["model"],
            "category": t["category"],
            "width": t["width"],
            "height": t["height"],
            "num_inference_steps": MODEL_STEPS[t["model"]],
        }
        for attempt in range(3):
            try:
                r = http_json("/api/tasks/text-to-image", "POST", body, timeout=60)
                ids.append(r["task_id"])
                print(f"[submit {i+1}/100] {t['model']} {t['width']}x{t['height']} {t['category']} text={t['with_text']} -> {r['task_id'][:8]}")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    print(f"[submit FAIL {i+1}] {t['model']}: {e}")
                    ids.append("")
                else:
                    time.sleep(5)
    return ids


def wait_all(plan: list[dict], ids: list[str]) -> dict:
    """轮询任务状态直到全部终态；返回统计。"""
    total = len(ids)
    done = 0
    stats = {"total": total, "succeeded": 0, "failed": 0, "cancelled": 0, "pending": total}
    per_model = {m: {"ok": 0, "fail": 0} for m in MODEL_SIZES}
    per_cat = {c: {"ok": 0, "fail": 0} for c in CATEGORIES}
    fails = []
    t0 = time.time()
    while done < total:
        try:
            r = http_json(f"/api/tasks?limit={total}", "GET", timeout=60)
            tasks = {t["id"]: t for t in r.get("tasks", [])}
        except Exception as e:  # noqa: BLE001
            print(f"[poll] error: {e}")
            time.sleep(10)
            continue
        done = 0
        for i, tid in enumerate(ids):
            t = tasks.get(tid)
            if not t:
                continue
            status = t.get("status", "queued")
            if status == "succeeded":
                done += 1
                stats["succeeded"] += 1
                stats["pending"] -= 1
                per_model[plan[i]["model"]]["ok"] += 1
                per_cat[plan[i]["category"]]["ok"] += 1
            elif status in ("failed", "cancelled"):
                done += 1
                stats[status] += 1
                stats["pending"] -= 1
                per_model[plan[i]["model"]]["fail"] += 1
                per_cat[plan[i]["category"]]["fail"] += 1
                fails.append(
                    {"i": i + 1, "model": plan[i]["model"], "category": plan[i]["category"],
                     "error": (t.get("error") or "")[:200]}
                )
        elapsed = round(time.time() - t0)
        print(f"[{elapsed}s] done {done}/{total} ok={stats['succeeded']} fail={stats['failed']} pending={stats['pending']}")
        if done < total:
            time.sleep(30)
    stats["elapsed_seconds"] = round(time.time() - t0)
    stats["per_model"] = per_model
    stats["per_category"] = per_cat
    stats["fails"] = fails
    return stats


def main() -> None:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    BASE = args.base

    plan = build_plan()
    print(f"PLAN: {len(plan)} tasks, models: { {m: len([p for p in plan if p['model']==m]) for m in MODEL_SIZES} }")
    print(f"  with_text: {sum(1 for p in plan if p['with_text'])} (all qwen), sizes: {sorted({(p['width'],p['height']) for p in plan})}")

    t_gen = time.time()
    prompts = gen_prompts(plan)
    print(f"[prompts] {sum(1 for p in prompts if p)}/{len(prompts)} generated in {round(time.time()-t_gen)}s")

    ids = submit_all(plan, prompts)
    print(f"[submit] {sum(1 for i in ids if i)}/{len(ids)} queued")

    stats = wait_all(plan, ids)
    print("\n==== BATCH REPORT ====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    out = Path(__file__).resolve().parent.parent / "outputs" / "_batch_report.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
