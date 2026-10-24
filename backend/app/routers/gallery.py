"""gallery（主页收录）管理接口：加入/取消主页、删除历史图片。

优先级：db 作品库（works）记录优先；未收编的遗留 outputs 批次走 gallery_store（unpinned 集合）。
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import config
from ..gallery_store import get_gallery_store
from ..works_store import get_works_store

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

_STAMP_RE = re.compile(r"^\d{8}_\d{6}$")
_IMAGE_RE = re.compile(r"^[\w\-.]+\.(png|jpg|jpeg|webp|bmp)$", re.IGNORECASE)


def _safe_path(stamp: str, image: str) -> Path:
    """校验并返回批次内图片绝对路径，防路径穿越。"""
    if not _STAMP_RE.match(stamp):
        raise HTTPException(400, "非法批次号")
    if not _IMAGE_RE.match(image) or ".." in image or "/" in image or "\\" in image:
        raise HTTPException(400, "非法文件名")
    return config.OUTPUT_DIR / stamp / image


def _pinned_ops(stamp: str, image: str, pinned: bool):
    """写入收录状态：works 优先，遗留批次走 gallery_store。"""
    ws = get_works_store()
    if ws.find(stamp):
        ws.set_pinned(stamp, image, pinned)
        return
    get_gallery_store().pin(stamp, image) if pinned else get_gallery_store().unpin(stamp, image)


@router.post("/pin")
def pin_image(body: dict):
    stamp = str(body.get("stamp", ""))
    image = str(body.get("image", ""))
    _safe_path(stamp, image)
    _pinned_ops(stamp, image, True)
    return {"ok": True, "stamp": stamp, "image": image, "pinned": True}


@router.post("/unpin")
def unpin_image(body: dict):
    stamp = str(body.get("stamp", ""))
    image = str(body.get("image", ""))
    _safe_path(stamp, image)
    _pinned_ops(stamp, image, False)
    return {"ok": True, "stamp": stamp, "image": image, "pinned": False}


# 作品分类白名单（与 prompt.py CATEGORIES 保持一致）
_CATEGORIES = {
    "landscape", "portrait", "animal", "architecture", "food", "sci-fi", "fantasy",
    "retro", "minimal", "cyberpunk", "design", "work", "3d", "anime",
}


@router.post("/category")
def set_category(body: dict):
    """更新作品分类（主页筛选用），仅 works 已收编批次。"""
    stamp = str(body.get("stamp", ""))
    category = str(body.get("category", ""))
    if not _STAMP_RE.match(stamp):
        raise HTTPException(400, "非法批次号")
    if category not in _CATEGORIES:
        raise HTTPException(400, f"不支持的分类: {category}，可选: {sorted(_CATEGORIES)}")
    ws = get_works_store()
    if not ws.set_category(stamp, category):
        raise HTTPException(404, "批次不存在或未收编")
    return {"ok": True, "stamp": stamp, "category": category}


@router.delete("/{stamp}/{image}")
def delete_image(stamp: str, image: str):
    _safe_path(stamp, image)
    ws = get_works_store()
    if not ws.resolve_image(stamp, image):
        raise HTTPException(404, "文件不存在")
    try:
        ws.remove_files(stamp, image)  # db/images + outputs 双位置删除（含空目录回收）
        ws.remove_image(stamp, image)  # works 记录移除
        get_gallery_store().remove(stamp, image)  # 遗留 unpinned 记录清理
    except OSError as exc:  # noqa: BLE001
        raise HTTPException(500, f"删除失败: {exc}") from exc
    return {"ok": True, "stamp": stamp, "image": image, "deleted": True}
