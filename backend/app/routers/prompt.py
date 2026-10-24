"""提示词路由：POST /api/prompt/optimize（优化）、POST /api/prompt/random（AI 随机生成）。

同步推理放入线程池执行，避免阻塞 uvicorn 事件循环。
"""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import llm_service

router = APIRouter(prefix="/api/prompt", tags=["prompt"])

VALID_TARGETS = {"auto", "qwen-image-2.1", "flux2-klein-4b", "z-image-turbo", "sana-sprint-1.6b", "moss-image-sft"}

# 内容分类（docs/14 §2，docs/20 新增 设计/工作/3D/动漫）
CATEGORIES = [
    "landscape",
    "portrait",
    "animal",
    "architecture",
    "food",
    "sci-fi",
    "fantasy",
    "retro",
    "minimal",
    "cyberpunk",
    "design",
    "work",
    "3d",
    "anime",
]


class OptimizeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    target_model: str = Field("auto")
    layout: bool = False


class RandomRequest(BaseModel):
    category: str = Field("landscape")
    style: str = Field("", max_length=100)
    with_text: bool = False
    count: int = Field(1, ge=1, le=10)


@router.post("/optimize")
async def optimize(req: OptimizeRequest):
    if req.target_model not in VALID_TARGETS:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PARAM", "message": f"不支持的目标模型: {req.target_model}"},
        )
    llm_service.ensure_ready()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, llm_service.optimize, req.prompt, req.target_model, req.layout)


@router.post("/random")
async def random_prompt(req: RandomRequest):
    if req.category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PARAM", "message": f"不支持的分类: {req.category}，可选: {CATEGORIES}"},
        )
    llm_service.ensure_ready()
    loop = asyncio.get_running_loop()

    def _gen():
        return llm_service.random_prompt(category=req.category, style=req.style, with_text=req.with_text)

    items = []
    for _ in range(req.count):
        items.append(await loop.run_in_executor(None, _gen))
    return {"items": items}
