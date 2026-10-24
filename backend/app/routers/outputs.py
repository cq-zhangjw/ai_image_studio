"""历史输出画廊接口。"""

import datetime
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import config
from ..gallery_store import get_gallery_store

router = APIRouter(prefix="/api/outputs", tags=["outputs"])

_STAMP_RE = re.compile(r"^\d{8}_\d{6}$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _parse_prompt_file(prompt_file: Path) -> tuple[str, dict | None]:
    """解析 input_prompt.txt。

    支持三种格式：
      1) 纯提示词文本 → prompt=原文, params=None
      2) "[prompt] X [params] k1: v1 k2: v2 ..." → 拆出纯提示词与参数字典
      3) "X\n\n[params]\nkey: value\n..." → 拆出纯提示词与参数字典
    """

    def kv(s: str) -> dict:
        params: dict = {}
        for line in s.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                params[k.strip()] = v.strip()
        return params

    try:
        text = prompt_file.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return "", None
    if not text:
        return "", None
    if text.startswith("[prompt]"):
        rest = text[len("[prompt]") :].strip()
    else:
        rest = text
    # 换行 [params]（兼容 "X\n\n[params]\nkey: v" 与 "[prompt] X\n\n[params]..."）
    m = re.split(r"\n?\[params\]\s*\n?", rest, maxsplit=1, flags=re.IGNORECASE)
    if len(m) == 2:
        return m[0].strip(), kv(m[1]) or None
    # 单行 "[prompt] X [params] k: v"
    if text.startswith("[prompt]"):
        marker = " [params]"
        if marker in rest:
            p_part, _, param_part = rest.partition(marker)
            prompt = p_part.strip()
            return prompt, kv(param_part) or None
    return rest.strip(), None


@router.get("")
def list_outputs(
    limit: int = Query(50, ge=1, le=200),
    pinned: int = Query(0, ge=0, le=1),
    category: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
):
    """历史输出画廊。

    主数据源：db 作品库（works 记录，图片在 db/images，pinned 状态在 images_pinned）；
    兼容数据源：outputs/ 历史批次（未收编的遗留目录）。
    """
    from ..works_store import get_works_store

    ws = get_works_store()
    runs = []
    total = 0  # 完整匹配数（不随 limit 截断，供前端统计展示）
    seen_stamps: set[str] = set()

    # 1) db 作品库（正式产物）：一次取足（500 上限覆盖当前规模），收集后统一截断，total 为真实完整数
    for rec in ws.list_records(500, pinned_only=bool(pinned), type_=type):
        stamp = str(rec.get("stamp", ""))
        if not stamp:
            continue
        if category and rec.get("category") != category:
            continue
        seen_stamps.add(stamp)
        images_all = [i for i in (rec.get("images") or []) if ws.resolve_image(stamp, i)]
        if not images_all:
            continue
        img_pin: dict = rec.get("images_pinned") or {}
        # 默认收录状态取记录级 pinned（新生成默认 False → 不收录，手动 ★ 后 True）
        default_pin = bool(rec.get("pinned", True))
        pins = [img_pin.get(i, default_pin) for i in images_all]
        shown = images_all if not pinned else [i for i, ok in zip(images_all, pins) if ok]
        if not shown:
            continue
        total += 1
        # 原图副本（编辑/放大任务收编时保存 _input_original[_N].png，_ 前缀不进产物列表）：
        # 单图任务 1 张；多图融合按 _input_original.png / _1 / _2 … 收集，供对比回显与素材还原
        sources: list[str] = []
        for idx in range(10):
            cand = "_input_original.png" if idx == 0 else f"_input_original_{idx}.png"
            if ws.resolve_image(stamp, cand) or (config.OUTPUT_DIR / stamp / cand).is_file():
                sources.append(cand)
            else:
                break
        source = sources[0] if sources else ""
        runs.append(
            {
                "stamp": stamp,
                "path": f"/api/outputs/{stamp}",
                "images": shown,
                "pinned": pins if not pinned else [True] * len(shown),
                "prompt": rec.get("prompt", ""),
                "params": rec.get("params") or None,
                "category": rec.get("category", "landscape"),
                "created_at": rec.get("created_at", ""),
                "source": source,
                "sources": sources,
            }
        )

    # 2) 遗留 outputs/ 批次（未收编；无类型标记，type 过滤时跳过）
    if type:
        return {"runs": runs[:limit], "total": total}
    output_dir = config.OUTPUT_DIR
    if output_dir.is_dir():
        unpinned_all = get_gallery_store().unpinned_set()
        for d in sorted(output_dir.iterdir(), reverse=True):
            if not d.is_dir() or not _STAMP_RE.match(d.name) or d.name in seen_stamps:
                continue
            images = sorted(p.name for p in d.iterdir() if p.suffix.lower() in _IMAGE_EXTS and not p.name.startswith("_"))
            if not images:
                continue
            pins = [(img, (d.name, img) not in unpinned_all) for img in images]
            if pinned:
                images = [img for img, ok in pins if ok]
                if not images:
                    continue
            total += 1
            prompt = ""
            params = None
            prompt_file = d / "input_prompt.txt"
            if prompt_file.exists():
                prompt, params = _parse_prompt_file(prompt_file)
            runs.append(
                {
                    "stamp": d.name,
                    "path": f"/api/outputs/{d.name}",
                    "images": images,
                    "pinned": [ok for _, ok in pins] if not pinned else [True] * len(images),
                    "prompt": prompt,
                    "params": params,
                    "created_at": _stamp_to_iso(d.name),
                }
            )
            if len(runs) >= limit:
                break
    return {"runs": runs[:limit], "total": total}


def _stamp_to_iso(stamp: str) -> str:
    try:
        dt = datetime.datetime.strptime(stamp, "%Y%m%d_%H%M%S")
        return dt.isoformat(timespec="seconds")
    except ValueError:
        return stamp
