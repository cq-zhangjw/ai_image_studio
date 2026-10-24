"""模型 / GPU 状态接口。"""

import torch
from fastapi import APIRouter, Query

from .. import config
from ..db_store import get_store
from ..services import (
    ernie_service,
    flux2_service,
    lumina_service,
    moss_service,
    qwen_service,
    sana_sprint_service,
    z_image_service,
)

router = APIRouter(prefix="/api/models", tags=["models"])

# 最近一次推理统计（service 写回，供前端展示）
last_stats: dict = {
    "elapsed_seconds": None,
    "steps_per_second": None,
    "model_load_seconds": None,
}


@router.get("")
def get_models():
    gpu = {
        "available": torch.cuda.is_available(),
        "name": None,
        "total_mb": None,
        "used_mb": None,
        "percent": None,
        "max_allocated_mb": None,
    }
    if gpu["available"]:
        gpu["name"] = torch.cuda.get_device_name(0)
        gpu["total_mb"] = int(torch.cuda.get_device_properties(0).total_memory / 2**20)
        allocated = torch.cuda.memory_allocated() / 2**20
        reserved = torch.cuda.memory_reserved() / 2**20
        gpu["used_mb"] = int(allocated)
        gpu["max_allocated_mb"] = int(torch.cuda.max_memory_allocated() / 2**20)
        gpu["percent"] = round(allocated / gpu["total_mb"] * 100, 1)

    return {
        "models": [
            {
                "id": "qwen-image-2.1",
                "name": "Qwen-Image-2.1",
                "status": "loaded" if qwen_service.is_loaded() else "ready",
                "loaded": qwen_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "ernie-image",
                "name": "ERNIE-Image Turbo",
                "status": "loaded" if ernie_service.is_loaded() else "ready",
                "loaded": ernie_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "lumina-image-2.0",
                "name": "Lumina-Image 2.0",
                "status": "loaded" if lumina_service.is_loaded() else "ready",
                "loaded": lumina_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "moss-image-sft",
                "name": "MOSS-Image SFT",
                "status": "loaded" if moss_service.is_loaded() else "ready",
                "loaded": moss_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "flux2-klein-4b",
                "name": "FLUX.2 [klein] 4B",
                "status": "loaded" if flux2_service.is_loaded() else "ready",
                "loaded": flux2_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "z-image-turbo",
                "name": "Z-Image Turbo",
                "status": "loaded" if z_image_service.is_loaded() else "ready",
                "loaded": z_image_service.is_loaded(),
                "load_seconds": None,
            },
            {
                "id": "sana-sprint-1.6b",
                "name": "SANA-Sprint 1.6B",
                "status": "loaded" if sana_sprint_service.is_loaded() else "ready",
                "loaded": sana_sprint_service.is_loaded(),
                "load_seconds": None,
            },
        ],
        "gpu": gpu,
        "last_stats": last_stats,
        "config": {
            "output_dir": str(config.OUTPUT_DIR),
            "max_upload_mb": config.MAX_UPLOAD_MB,
        },
    }


@router.get("/stats")
def get_stats(limit: int = Query(50, ge=1, le=200)):
    """推理统计历史（moofile 持久化，docs/09 §3.2）。"""
    try:
        rows = get_store().recent_stats(limit=limit)
    except Exception:  # noqa: BLE001
        rows = []
    return {"stats": rows}
