"""任务队列：单 worker 串行推理 + SSE 进度广播。"""

import datetime
import queue
import threading
import time
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

from .schemas import TaskDetail, TaskProgress


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class TaskInfo:
    """单个任务的可变状态（线程间共享，GIL 保证字段更新原子性）。"""

    def __init__(self, task_id: str, task_type: str, payload: dict):
        self.id = task_id
        self.type = task_type
        self.payload = payload
        self.status = "queued"
        self.progress = TaskProgress()
        self.message = "排队中…"
        self.outputs: list[str] = []
        self.elapsed_seconds: Optional[float] = None
        self.steps_per_second: Optional[float] = None
        self.model_load_seconds: Optional[float] = None
        self.error: Optional[str] = None
        self.created_at = _now()
        self.finished_at: Optional[str] = None
        self.version = 0  # SSE 轮询用：每次变更自增

    def bump(self):
        self.version += 1

    def set_progress(self, step: int, total: int, phase: str, percent: Optional[int] = None):
        if percent is None:
            percent = int(round(step / total * 100)) if total else 0
        self.progress = TaskProgress(step=step, total=total, percent=min(100, max(0, percent)), phase=phase)
        self.message = phase
        self.bump()

    def to_detail(self) -> TaskDetail:
        return TaskDetail(
            id=self.id,
            type=self.type,
            status=self.status,
            progress=self.progress,
            message=self.message,
            model=self.payload.get("model"),
            prompt=self.payload.get("prompt"),
            params=dict(self.payload),
            outputs=self.outputs,
            elapsed_seconds=self.elapsed_seconds,
            steps_per_second=self.steps_per_second,
            model_load_seconds=self.model_load_seconds,
            error=self.error,
            created_at=self.created_at,
            finished_at=self.finished_at,
        )


class TaskManager:
    """单 worker 队列：提交 -> 排队 -> 串行执行 -> 完成/失败。

    任务终态（succeeded/failed/cancelled）通过 moofile 落库（db_store），
    启动时从 db 恢复历史；残留的 queued/running 标记为 interrupted。
    """

    def __init__(self, executor: Callable[[TaskInfo], Any]):
        self._executor = executor
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._tasks: Dict[str, TaskInfo] = {}
        self._history: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        self._restore_history()
        self._migrate_works()
        self._worker = threading.Thread(target=self._loop, name="task-worker", daemon=True)
        self._worker.start()
        # 进度落库线程：运行中任务每 2s 写一次进度到 db（docs/16 §1，前端刷新后轮询可恢复）
        self._flusher = threading.Thread(target=self._progress_flusher, name="task-flusher", daemon=True)
        self._flusher.start()

    def _progress_flusher(self) -> None:
        """节流持久化 running/queued 任务的实时进度。"""
        while True:
            time.sleep(2)
            try:
                with self._lock:
                    active = [t for t in self._tasks.values() if t.status in ("queued", "running")]
                for t in active:
                    try:
                        self._persist_task(t)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass

    # ---------------- 持久化 ----------------
    def _restore_history(self) -> None:
        """启动时从 moofile 恢复历史任务（docs/09 §5）。"""
        try:
            from .db_store import get_store

            rows = get_store().load_tasks(limit=500)
        except Exception:  # noqa: BLE001
            rows = []
        restored = 0
        for row in rows:
            tid = row.get("id", "")
            if not tid or tid in self._history:
                continue
            task = TaskInfo(tid, row.get("type", "unknown"), row.get("params") or {})
            raw_status = row.get("status", "interrupted")
            # 启动清理：上次服务残留的 queued/running 一律标记 interrupted（"服务重启中断"），
            # 并同步落库永久清空，避免前端 activeCount 卡死"开始"按钮
            if raw_status in ("queued", "running"):
                raw_status = "interrupted"
                try:
                    from .db_store import get_store

                    get_store().save_task({**row, "status": "interrupted", "finished_at": _now()})
                except Exception:  # noqa: BLE001
                    pass
            task.status = raw_status
            task.message = {"succeeded": "完成", "failed": "失败", "cancelled": "已取消"}.get(
                task.status, "服务重启中断"
            )
            pr = row.get("progress")
            if isinstance(pr, dict):
                task.progress = TaskProgress(
                    step=int(pr.get("step", 0) or 0),
                    total=int(pr.get("total", 1) or 1),
                    percent=int(pr.get("percent", 0) or 0),
                    phase=str(pr.get("phase", "") or ""),
                )
            task.outputs = list(row.get("outputs") or [])
            task.elapsed_seconds = row.get("elapsed_seconds")
            task.steps_per_second = row.get("steps_per_second")
            task.model_load_seconds = row.get("model_load_seconds")
            task.error = row.get("error")
            task.created_at = row.get("created_at") or _now()
            task.finished_at = row.get("finished_at")
            # payload 补全 prompt/model 以便详情展示
            task.payload = {
                "prompt": row.get("prompt", ""),
                "model": row.get("model", ""),
                **task.payload,
            }
            self._history[tid] = task
            restored += 1
        if restored:
            print(f"[task-manager] restored {restored} history task(s) from db")

    def _persist_task(self, task: "TaskInfo") -> None:
        """任务落库（docs/09 §3.1 + docs/16 §1：含实时进度）；成功任务顺带写推理统计（§3.2）。"""
        try:
            from .db_store import get_store

            store = get_store()
            store.save_task(
                {
                    "id": task.id,
                    "type": task.type,
                    "status": task.status,
                    "model": task.payload.get("model", ""),
                    "prompt": str(task.payload.get("prompt", ""))[:2000],
                    "params": task.payload,
                    "progress": {
                        "step": task.progress.step,
                        "total": task.progress.total,
                        "percent": task.progress.percent,
                        "phase": task.progress.phase,
                    },
                    "outputs": task.outputs,
                    "elapsed_seconds": task.elapsed_seconds,
                    "steps_per_second": task.steps_per_second,
                    "model_load_seconds": task.model_load_seconds,
                    "error": task.error,
                    "created_at": task.created_at,
                    "finished_at": task.finished_at,
                }
            )
            if task.status == "succeeded" and task.elapsed_seconds is not None:
                store.save_stat(
                    {
                        "id": store.stats_util.generate_id("stat"),
                        "model": task.payload.get("model", ""),
                        "elapsed_seconds": task.elapsed_seconds,
                        "steps_per_second": task.steps_per_second,
                        "model_load_seconds": task.model_load_seconds,
                        "created_at": _now(),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[task-manager] persist task {task.id} failed: {exc}")

    def _migrate_works(self) -> None:
        """启动时把 outputs/ 历史批次收编进 db 作品库（docs/12 §7b）。"""
        try:
            from .works_store import get_works_store

            get_works_store().migrate_legacy()
        except Exception as exc:  # noqa: BLE001
            print(f"[works] migrate_legacy failed: {exc}")

    def _ingest_works(self, task: "TaskInfo") -> None:
        """任务成功后：产物收编进 db 作品库（图片复制到 db/images + works 记录）。"""
        import re

        try:
            from .works_store import get_works_store

            stamp_re = re.compile(r"(\d{8}_\d{6})")
            stamp = ""
            images: list[str] = []
            for p in task.outputs:
                s = str(p).replace("\\", "/")
                m = stamp_re.search(s)
                if m:
                    stamp = m.group(1)
                images.append(s.rstrip("/").rsplit("/", 1)[-1])
            if not stamp or not images:
                return
            get_works_store().ingest_batch(
                stamp=stamp,
                images=images,
                prompt=str(task.payload.get("prompt", ""))[:2000],
                params=dict(task.payload),
                type_=task.type,
                model=str(task.payload.get("model", "")),
                # 新生成默认不加入主页（收编但不 pin；主页 = pinned_only），质量合格由用户手动收录
                pinned=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[works] ingest task {task.id} failed: {exc}")

    # ---------------- 公开接口 ----------------
    def pre_register(self, task_type: str) -> TaskInfo:
        """预注册任务（占位 ID，用于上传文件落盘目录），submit 时覆盖同 ID。"""
        task_id = f"task_{uuid.uuid4().hex[:16]}"
        task = TaskInfo(task_id, task_type, {})
        with self._lock:
            self._tasks[task_id] = task
        return task

    def drop(self, task_id: str) -> None:
        """删除未入队的占位任务（上传失败时清理）。"""
        with self._lock:
            self._tasks.pop(task_id, None)

    def submit(self, task_type: str, payload: dict, task_id: Optional[str] = None) -> TaskInfo:
        if task_id is None:
            task_id = f"task_{uuid.uuid4().hex[:16]}"
        task = TaskInfo(task_id, task_type, payload)
        with self._lock:
            self._tasks[task_id] = task
        self._queue.put(task_id)
        return task

    def get(self, task_id: str) -> Optional[TaskInfo]:
        with self._lock:
            return self._tasks.get(task_id) or self._history.get(task_id)

    def list_recent(self, limit: int = 20) -> list[TaskInfo]:
        with self._lock:
            # 活动任务 + 历史任务（含 db 恢复的）合并，按创建时间倒序
            tasks = list(self._tasks.values()) + list(self._history.values())
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None or task.status not in ("queued", "running"):
            return False
        # 串行 worker 无法安全中断推理线程，仅取消排队中的任务
        task.status = "cancelled"
        task.message = "已取消"
        task.finished_at = _now()
        task.bump()
        return True

    # ---------------- worker 循环 ----------------
    def _loop(self):
        while True:
            task_id = self._queue.get()
            task = self.get(task_id)
            if task is None:
                continue
            if task.status == "cancelled":
                self._persist_task(task)
                continue
            task.status = "running"
            task.set_progress(0, 1, "loading model")
            task.bump()
            try:
                outputs = self._executor(task)
                task.outputs = [str(p) for p in outputs]
                task.status = "succeeded"
                task.message = "完成"
                # 产物收编进 db 作品库（图片复制 db/images + works 记录）
                self._ingest_works(task)
                # 耗时统计由 executor 内部写回（含 steps_per_second 等）
            except Exception as exc:  # noqa: BLE001
                task.status = "failed"
                task.message = "失败"
                task.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            task.finished_at = _now()
            task.bump()
            self._persist_task(task)
            with self._lock:
                self._history[task_id] = task
                self._tasks.pop(task_id, None)
