"""Pydantic 请求/响应模型。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class TextToImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: Optional[str] = None
    model: str = Field("qwen-image-2.1", pattern="^(qwen-image-2.1|ernie-image|moss-image-sft|flux2-klein-4b|z-image-turbo|sana-sprint-1.6b|lumina-image-2.0)$")
    category: str = Field(
        "landscape",
        pattern="^(landscape|portrait|animal|architecture|food|sci-fi|fantasy|retro|minimal|cyberpunk|design|work|3d|anime)$",
    )
    width: int = Field(1024, ge=256, le=2048)
    height: int = Field(1024, ge=256, le=2048)
    num_inference_steps: int = Field(20, ge=1, le=100)
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1)


class TaskProgress(BaseModel):
    step: int = 0
    total: int = 1
    percent: int = 0
    phase: str = "queued"


class TaskDetail(BaseModel):
    id: str
    type: str
    status: str  # queued | running | succeeded | failed | cancelled
    progress: TaskProgress = TaskProgress()
    message: str = ""
    model: Optional[str] = None
    prompt: Optional[str] = None
    params: Optional[dict] = None
    outputs: List[str] = []
    elapsed_seconds: Optional[float] = None
    steps_per_second: Optional[float] = None
    model_load_seconds: Optional[float] = None
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
