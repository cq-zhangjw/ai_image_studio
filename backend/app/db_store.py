"""moofile 本地存储服务：任务记录 + 推理统计。

布局（docs/09）：db/db_tasks_<hash8>/{db.bson,meta.json}、db/db_stats_<hash8>/
所有写操作走进程级锁串行化（moofile 为文件型 BSON）。
"""

import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 独立于 app 包（无相对导入），保证可脱离 FastAPI 单独测试
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = _PROJECT_ROOT / "db"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 常驻单例
_store: "DbStore | None" = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_meta(root: Path, name: str) -> None:
    """写 meta.json（moofile_base 布局：每个库目录带 meta 描述）。"""
    meta_file = root / "meta.json"
    if meta_file.is_file():
        return
    now = _now_iso()
    meta = {
        "id": root.name,
        "name": name,
        "type": "normal",
        "createdAt": now,
        "updatedAt": now,
        "trashed": False,
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


class DbStore:
    """任务/统计两个 moofile 库的封装。"""

    _TASKS_DB = "db"
    _STATS_DB = "db"
    _TASKS_PREFIX = "db_tasks_"
    _STATS_PREFIX = "db_stats_"
    _INDEXES: list[str] = []  # 小数据集，全表扫描足够

    def __init__(self, db_root: Path):
        self.db_root = db_root
        self.tasks_root = self._resolve_root(db_root, self._TASKS_PREFIX, "tasks")
        self.stats_root = self._resolve_root(db_root, self._STATS_PREFIX, "stats")
        self._lock = threading.Lock()
        # 延迟 import，避免无 moofile 环境直接炸
        from utils.moofile_util import MooFileUtil

        self.tasks_util = MooFileUtil(str(self.tasks_root))
        self.stats_util = MooFileUtil(str(self.stats_root))
        self._ensure_all()

    @staticmethod
    def _resolve_root(db_root: Path, prefix: str, name: str) -> Path:
        if db_root.is_dir():
            matches = sorted(p for p in db_root.glob(f"{prefix}*") if p.is_dir())
            if matches:
                return matches[0]
        root = db_root / f"{prefix}{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ensure_all(self) -> None:
        if not self.tasks_util.database_exists(self._TASKS_DB):
            self.tasks_util.create_database(self._TASKS_DB)
        _ensure_meta(self.tasks_root, "tasks")
        if not self.stats_util.database_exists(self._STATS_DB):
            self.stats_util.create_database(self._STATS_DB)
        _ensure_meta(self.stats_root, "stats")

    # ---------------- 任务 ----------------
    def save_task(self, task: dict) -> None:
        """upsert 一条任务终态记录（按 id 匹配，存在则替换）。"""
        record = {**task, "recordType": "record"}
        with self._lock:
            rows = self.tasks_util.query_data(self._TASKS_DB, {"id": task["id"]}, self._INDEXES)
            if rows:
                self.tasks_util.delete_data(self._TASKS_DB, {"id": task["id"]}, self._INDEXES)
            self.tasks_util.insert_data(self._TASKS_DB, [record], self._INDEXES)

    def load_tasks(self, limit: int = 200) -> list[dict]:
        """全部任务记录，按 created_at 倒序。"""
        with self._lock:
            rows = self.tasks_util.query_data(self._TASKS_DB, {}, self._INDEXES)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            rows = self.tasks_util.query_data(self._TASKS_DB, {"id": task_id}, self._INDEXES)
        return rows[0] if rows else None

    # ---------------- 统计 ----------------
    def save_stat(self, stat: dict) -> None:
        record = {**stat, "recordType": "record"}
        with self._lock:
            self.stats_util.insert_data(self._STATS_DB, [record], self._INDEXES)

    def recent_stats(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.stats_util.query_data(self._STATS_DB, {}, self._INDEXES)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]


def get_store() -> DbStore:
    global _store
    if _store is None:
        _store = DbStore(DB_DIR)
    return _store
