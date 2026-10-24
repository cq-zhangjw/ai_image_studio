"""AI 图像工作站 · FastAPI 入口。"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import gallery, models, outputs, prompt, tasks
from .task_manager import TaskManager

app = FastAPI(title="AI 图像工作站", version="0.1.0")

# CORS（开发时前端 5173 直连；生产走 Vite 代理则命中同源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任务管理器（单 worker）
tasks.manager = TaskManager(executor=tasks.execute_task)

# 路由
app.include_router(models.router)
app.include_router(tasks.router)
app.include_router(outputs.router)
app.include_router(gallery.router)
app.include_router(prompt.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/outputs/{stamp}/{image}")
def output_file(stamp: str, image: str):
    """图片文件服务：db/images 优先，回退 outputs 目录（历史批次）。"""
    from .works_store import get_works_store

    path = get_works_store().resolve_image(stamp, image)
    if path is None:
        raise HTTPException(404, "图片不存在")
    return FileResponse(path)


# 静态：前端产物（生产单端口部署，可选挂载）
if config.FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")
