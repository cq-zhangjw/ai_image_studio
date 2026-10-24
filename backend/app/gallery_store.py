"""gallery（主页收录）moofile 存储服务。

布局：db/db_gallery_<hash8>/{db.bson,meta.json}
语义：只存「取消主页」的条目（pinned:false）；无记录 = 默认已收录主页。
所有写操作走进程级锁串行化。
"""

import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = _PROJECT_ROOT / "db"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 常驻单例
_store: Optional["GalleryStore"] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_meta(root: Path, name: str) -> None:
    meta_file = root / "meta.json"
    if meta_file.is_file():
        return
    meta = {
        "id": root.name,
        "name": name,
        "type": "normal",
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
        "trashed": False,
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        import json

        json.dump(meta, f, ensure_ascii=False, indent=2)


class GalleryStore:
    """gallery 库封装：unpinned 记录 CRUD。"""

    _DB = "db"
    _PREFIX = "db_gallery_"
    _INDEXES: list[str] = []  # 小数据集，全表扫描足够

    def __init__(self, db_root: Path):
        self.db_root = db_root
        self.root = self._resolve_root(db_root)
        self._lock = threading.Lock()
        from utils.moofile_util import MooFileUtil

        self.util = MooFileUtil(str(self.root))
        self._ensure_all()

    @staticmethod
    def _resolve_root(db_root: Path) -> Path:
        if db_root.is_dir():
            matches = sorted(p for p in db_root.glob(f"{GalleryStore._PREFIX}*") if p.is_dir())
            if matches:
                return matches[0]
        root = db_root / f"{GalleryStore._PREFIX}{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ensure_all(self) -> None:
        if not self.util.database_exists(self._DB):
            self.util.create_database(self._DB)
        _ensure_meta(self.root, "gallery")

    # ---------------- 查询 ----------------
    def unpinned_set(self) -> set[tuple[str, str]]:
        """返回所有 (stamp, image) 取消收录集合。"""
        with self._lock:
            rows = self.util.query_data(self._DB, {"pinned": False}, self._INDEXES)
        return {(str(r.get("stamp", "")), str(r.get("image", ""))) for r in rows}

    def is_unpinned(self, stamp: str, image: str) -> bool:
        return (stamp, image) in self.unpinned_set()

    # ---------------- 写操作 ----------------
    def unpin(self, stamp: str, image: str) -> None:
        """取消主页收录（upsert pinned:false）。"""
        with self._lock:
            self.util.delete_data(self._DB, {"stamp": stamp, "image": image}, self._INDEXES)
            self.util.insert_data(
                self._DB,
                [
                    {
                        "id": self.util.generate_id("gid"),
                        "stamp": stamp,
                        "image": image,
                        "pinned": False,
                        "created_at": _now_iso(),
                        "recordType": "record",
                    }
                ],
                self._INDEXES,
            )

    def pin(self, stamp: str, image: str) -> None:
        """加入主页收录（删除 unpinned 记录，恢复默认）。"""
        with self._lock:
            self.util.delete_data(self._DB, {"stamp": stamp, "image": image}, self._INDEXES)

    def remove(self, stamp: str, image: str) -> None:
        """删除收录记录（配合文件删除）。"""
        with self._lock:
            self.util.delete_data(self._DB, {"stamp": stamp, "image": image}, self._INDEXES)


def get_gallery_store() -> GalleryStore:
    global _store
    if _store is None:
        _store = GalleryStore(DB_DIR)
    return _store
