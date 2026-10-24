"""任务提交 / 查询 / SSE 进度接口。"""

import asyncio
import datetime
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from .. import config
from ..schemas import TextToImageRequest
from ..services import (
    ernie_service,
    flux2_service,
    llm_service,
    lumina_service,
    moss_service,
    qwen_service,
    sana_sprint_service,
    upscale_service,
    z_image_service,
)
from .models import last_stats

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# 由 main.py 注入的单例
manager = None  # type: ignore


_STAMP_RE = re.compile(r"(\d{8}_\d{6})")


def _to_web_paths(paths) -> list[str]:
    """本地绝对路径 -> /api/outputs/<stamp>/<filename> 可访问 URL。

    产物现统一收编进 db 作品库（图片在 db/images），文件服务按 stamp+filename 解析。
    """
    out = []
    for p in paths:
        s = str(p).replace("\\", "/")
        m = _STAMP_RE.search(s)
        if m:
            out.append(f"/api/outputs/{m.group(1)}/{s.rstrip('/').rsplit('/', 1)[-1]}")
        else:
            out.append(s)
    return out


def _save_upload(upload: UploadFile, task_id: str, name: str) -> Path:
    """校验并保存上传图片到 outputs/_uploads/<task_id>/。"""
    suffix = Path(upload.filename or "image.png").suffix.lower()
    if suffix not in config.ALLOWED_IMAGE_EXTS:
        raise HTTPException(status_code=400, detail={"code": "UPLOAD_INVALID", "message": f"不支持的图片格式: {suffix}"})
    dest_dir = config.UPLOAD_DIR / task_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{name}{suffix}"
    data = upload.file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": "UPLOAD_INVALID", "message": f"图片超过 {config.MAX_UPLOAD_MB}MB"})
    dest.write_bytes(data)
    return dest


def _resolve_src(src_stamp: str, src_image: str) -> Path:
    """引用服务端作品文件（历史跳转带入）：db/images 优先，兼容 outputs/<stamp> 遗留。"""
    from ..works_store import get_works_store

    p = get_works_store().resolve_image(src_stamp, src_image)
    if not p or not p.is_file():
        legacy = config.OUTPUT_DIR / src_stamp / src_image
        if legacy.is_file():
            return legacy
        raise HTTPException(status_code=404, detail={"code": "SRC_NOT_FOUND", "message": f"找不到历史图片: {src_stamp}/{src_image}"})
    return p


def _check_size(width: int, height: int):
    if width * height > config.MAX_TASK_PIXELS:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PARAM", "message": f"生成面积 {width}x{height} 超过上限（防 OOM），请降低尺寸"},
        )


# ---------------- 提交 ----------------
@router.post("/text-to-image")
def submit_text_to_image(req: TextToImageRequest):
    _check_size(req.width, req.height)
    task = manager.submit("text-to-image", req.model_dump())
    return {"task_id": task.id, "status": task.status}


@router.post("/edit")
async def submit_edit(
    prompt: str = Form(..., min_length=1, max_length=4000),
    image: Optional[UploadFile] = File(None),
    images: Optional[List[UploadFile]] = File(None),  # 多图融合（多张上传）
    src_stamp: Optional[str] = Form(None),
    src_image: Optional[str] = Form(None),
    mark: Optional[UploadFile] = File(None),
    mask: Optional[UploadFile] = File(None),
    annotation_style: str = Form("circle"),
    num_inference_steps: int = Form(24),
    seed: Optional[int] = Form(None),
    composite: bool = Form(True),
    feather: int = Form(20),
    model: str = Form("qwen-image-2.1"),
):
    if model not in ("qwen-image-2.1", "flux2-klein-4b"):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": f"不支持的模型: {model}"})
    has_single = image is not None or (src_stamp and src_image)
    multi = [f for f in (images or []) if f is not None]
    if not has_single and not multi:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": "需要上传图片或指定 src_stamp/src_image"})
    # 先落盘上传文件，再提交任务（避免 worker 竞态读到未写入的文件路径）
    pre_task = manager.pre_register("edit")
    try:
        if multi:
            image_paths = [_save_upload(f, pre_task.id, f"img{i}") for i, f in enumerate(multi)]
            mark_path = mask_path = None
        else:
            image_paths = []
            image_path = _save_upload(image, pre_task.id, "image") if image else _resolve_src(src_stamp, src_image)
            mark_path = _save_upload(mark, pre_task.id, "mark") if mark else None
            mask_path = _save_upload(mask, pre_task.id, "mask") if mask else None
        payload = {
            "prompt": prompt,
            "model": model,
            "annotation_style": annotation_style,
            "num_inference_steps": num_inference_steps,
            "seed": seed,
            "composite": composite,
            "feather": feather,
        }
        if multi:
            payload["_image_paths"] = [str(p) for p in image_paths]
        else:
            payload["_image_path"] = str(image_path)
            payload["_mark_path"] = str(mark_path) if mark_path else None
            payload["_mask_path"] = str(mask_path) if mask_path else None
        task = manager.submit(
            "edit",
            payload,
            task_id=pre_task.id,
        )
    except Exception:
        # 提交失败时清理占位任务，避免 queued 残留卡住前端"任务执行中"
        manager.drop(pre_task.id)
        raise
    return {"task_id": task.id, "status": task.status}


@router.post("/outpaint")
async def submit_outpaint(
    image: Optional[UploadFile] = File(None),
    src_stamp: Optional[str] = Form(None),
    src_image: Optional[str] = Form(None),
    prompt: str = Form("", max_length=4000),
    target_ratio: str = Form("16:9"),
    direction: str = Form("right"),
    fill: str = Form("edge"),
    num_inference_steps: int = Form(20),
    seed: Optional[int] = Form(None),
):
    if target_ratio not in ("16:9", "9:16", "1:1", "4:3", "3:4"):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": f"不支持的目标比例: {target_ratio}"})
    if direction not in ("left", "right", "up", "down", "all"):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": f"不支持的方向: {direction}"})
    if image is None and not (src_stamp and src_image):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": "需要上传图片或指定 src_stamp/src_image"})
    pre_task = manager.pre_register("outpaint")
    try:
        image_path = _save_upload(image, pre_task.id, "image") if image else _resolve_src(src_stamp, src_image)
        task = manager.submit(
            "outpaint",
            {
                "prompt": prompt,
                "target_ratio": target_ratio,
                "direction": direction,
                "fill": fill,
                "num_inference_steps": num_inference_steps,
                "seed": seed,
                "_image_path": str(image_path),
            },
            task_id=pre_task.id,
        )
    except Exception:
        manager.drop(pre_task.id)
        raise
    return {"task_id": task.id, "status": task.status}


@router.post("/upscale")
async def submit_upscale(
    image: Optional[UploadFile] = File(None),
    src_stamp: Optional[str] = Form(None),
    src_image: Optional[str] = Form(None),
    engine: str = Form("realesrgan"),
    scale: int = Form(2),
):
    if engine != "realesrgan":
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": f"不支持的放大引擎: {engine}"})
    if scale not in (2, 3, 4):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": "Real-ESRGAN 倍数仅支持 2/3/4"})
    if image is None and not (src_stamp and src_image):
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAM", "message": "需要上传图片或指定 src_stamp/src_image"})
    pre_task = manager.pre_register("upscale")
    try:
        image_path = _save_upload(image, pre_task.id, "image") if image else _resolve_src(src_stamp, src_image)
        payload = {
            "engine": engine,
            "scale": scale,
            "_image_path": str(image_path),
        }
        task = manager.submit(
            "upscale",
            payload,
            task_id=pre_task.id,
        )
    except Exception:
        manager.drop(pre_task.id)
        raise
    return {"task_id": task.id, "status": task.status}


# ---------------- 查询 / SSE ----------------
@router.get("")
def list_tasks(limit: int = Query(20, ge=1, le=100)):
    tasks = manager.list_recent(limit)
    result = []
    for t in tasks:
        d = t.to_detail().model_dump()
        d["outputs"] = _to_web_paths(t.outputs)
        result.append(d)
    return {"tasks": result}


@router.get("/{task_id}")
def get_task(task_id: str):
    task = manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"任务不存在: {task_id}"})
    d = task.to_detail().model_dump()
    d["outputs"] = _to_web_paths(task.outputs)
    return d


@router.get("/{task_id}/events")
async def task_events(task_id: str):
    task = manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"任务不存在: {task_id}"})

    async def event_gen():
        last_version = -1
        while True:
            t = manager.get(task_id)
            if t is None:
                yield {"event": "done", "data": '{"task_id": "%s"}' % task_id}
                break
            if t.version != last_version:
                last_version = t.version
                d = t.to_detail().model_dump()
                if t.status in ("queued", "running"):
                    yield {
                        "event": "progress",
                        "data": f'{{"step": {t.progress.step}, "total": {t.progress.total}, "percent": {t.progress.percent}, "phase": "{t.progress.phase}", "status": "{t.status}"}}',
                    }
                elif t.status in ("succeeded", "failed", "cancelled"):
                    import json

                    yield {
                        "event": "status",
                        "data": json.dumps(
                            {
                                "status": t.status,
                                "outputs": _to_web_paths(t.outputs),
                                "elapsed_seconds": t.elapsed_seconds,
                                "steps_per_second": t.steps_per_second,
                                "model_load_seconds": t.model_load_seconds,
                                "error": t.error,
                            },
                            ensure_ascii=False,
                        ),
                    }
                    # 回写最近统计
                    last_stats.update(
                        {
                            "elapsed_seconds": t.elapsed_seconds,
                            "steps_per_second": t.steps_per_second,
                            "model_load_seconds": t.model_load_seconds,
                        }
                    )
                    yield {"event": "done", "data": '{"task_id": "%s"}' % task_id}
                    break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_gen())


# ---------------- 执行器（worker 调用） ----------------
def execute_task(task) -> list[Path]:
    """TaskManager worker 的 executor：按类型 + 模型分发到 service。

    显存策略：20G 卡不足同时驻留 Qwen(~14GB) + Klein(~8GB)，
    切模型前先 unload 另一模型（gc + empty_cache）。
    """
    model = task.payload.get("model", "qwen-image-2.1")
    # LLM 显存共存策略（docs/06 §3）：大模型任务先卸 LLM，klein/sana 可共存
    if task.type in ("outpaint", "upscale", "upscale-folder") or llm_service.should_unload_for(model):
        llm_service.unload()
    if task.type == "text-to-image":
        if model == "ernie-image":
            qwen_service.unload()
            flux2_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            return ernie_service.text_to_image(task)
        if model == "lumina-image-2.0":
            qwen_service.unload()
            flux2_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            ernie_service.unload()
            return lumina_service.text_to_image(task)
        if model == "moss-image-sft":
            qwen_service.unload()
            flux2_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            ernie_service.unload()
            return moss_service.text_to_image(task)
        if model == "flux2-klein-4b":
            qwen_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            return flux2_service.text_to_image(task)
        if model == "z-image-turbo":
            qwen_service.unload()
            flux2_service.unload()
            sana_sprint_service.unload()
            return z_image_service.text_to_image(task)
        if model == "sana-sprint-1.6b":
            qwen_service.unload()
            flux2_service.unload()
            z_image_service.unload()
            return sana_sprint_service.text_to_image(task)
            qwen_service.unload()
            flux2_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            ernie_service.unload()
            lumina_service.unload()
        flux2_service.unload()
        z_image_service.unload()
        sana_sprint_service.unload()
        return qwen_service.text_to_image(task)
    if task.type == "edit":
        if model == "flux2-klein-4b":
            qwen_service.unload()
            z_image_service.unload()
            sana_sprint_service.unload()
            return flux2_service.edit_image(
                task,
                Path(task.payload["_image_path"]) if task.payload.get("_image_path") else None,
            )
        flux2_service.unload()
        z_image_service.unload()
        sana_sprint_service.unload()
        return qwen_service.edit_image(
            task,
            Path(task.payload["_image_path"]) if task.payload.get("_image_path") else None,
            Path(task.payload["_mark_path"]) if task.payload.get("_mark_path") else None,
            Path(task.payload["_mask_path"]) if task.payload.get("_mask_path") else None,
        )
    if task.type == "outpaint":
        flux2_service.unload()
        z_image_service.unload()
        sana_sprint_service.unload()
        return qwen_service.outpaint(task, Path(task.payload["_image_path"]))
    if task.type == "upscale":
        return upscale_service.upscale_image_realesrgan(task, Path(task.payload["_image_path"]))
    raise ValueError(f"未知任务类型: {task.type}")
