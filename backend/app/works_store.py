"""作品库：生成产物的统一存储（docs/12 §7b）。

布局：db/db_works_<hash8>/{db.bson,meta.json,images/<stamp>/<image>}
语义：生成产物图片存 db 目录 images/ 下，元数据（stamp/type/model/prompt/params/images/pinned）存 works 表。
outputs/ 仅作为内部测试与历史兼容来源（resolve 时回退）。
"""

import json
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 独立于 app 包（无相对导入）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = _PROJECT_ROOT / "db"
OUTPUT_DIR = _PROJECT_ROOT / "outputs"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 常驻单例
_store: Optional["WorksStore"] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp_to_iso(stamp: str) -> str:
    """批次号 YYYYMMDD_HHMMSS → ISO 时间（生成真实时刻），解析失败回退当前时间。"""
    try:
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return _now_iso()


def _ensure_meta(root: Path, name: str) -> None:
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


class WorksStore:
    """作品库封装：works 记录 + db/images 图片文件管理。"""

    _DB = "db"
    _PREFIX = "db_works_"
    _INDEXES: list[str] = []  # 小数据集，全表扫描

    def __init__(self, db_root: Path):
        self.db_root = db_root
        self.root = self._resolve_root(db_root)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        from utils.moofile_util import MooFileUtil

        self.util = MooFileUtil(str(self.root))
        self._ensure_all()

    @staticmethod
    def _resolve_root(db_root: Path) -> Path:
        if db_root.is_dir():
            matches = sorted(p for p in db_root.glob(f"{WorksStore._PREFIX}*") if p.is_dir())
            if matches:
                return matches[0]
        root = db_root / f"{WorksStore._PREFIX}{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ensure_all(self) -> None:
        if not self.util.database_exists(self._DB):
            self.util.create_database(self._DB)
        _ensure_meta(self.root, "works")

    # ---------------- 图片文件 ----------------
    def image_file(self, stamp: str, image: str) -> Path:
        return self.images_dir / stamp / image

    def legacy_file(self, stamp: str, image: str) -> Path:
        """历史兼容：outputs/<stamp>/<image>。"""
        return OUTPUT_DIR / stamp / image

    def resolve_image(self, stamp: str, image: str) -> Optional[Path]:
        """db/images 优先，回退 outputs 目录（历史批次）。"""
        p = self.image_file(stamp, image)
        if p.is_file():
            return p
        legacy = self.legacy_file(stamp, image)
        if legacy.is_file():
            return legacy
        return None

    # ---------------- 记录 ----------------
    def add(
        self,
        stamp: str,
        type_: str,
        model: str,
        prompt: str,
        params: dict,
        images: list[str],
        created_at: Optional[str] = None,
        pinned: bool = True,
    ) -> None:
        with self._lock:
            rows = self.util.query_data(self._DB, {"stamp": stamp}, self._INDEXES)
            if rows:
                self.util.delete_data(self._DB, {"stamp": stamp}, self._INDEXES)
            self.util.insert_data(
                self._DB,
                [
                    {
                        "id": self.util.generate_id("wid"),
                        "stamp": stamp,
                        "type": type_,
                        "model": model or "",
                        "category": (params or {}).get("category", "landscape"),
                        "prompt": str(prompt or "")[:2000],
                        "params": params or {},
                        "images": list(images),
                        "pinned": pinned,
                        "created_at": created_at or _now_iso(),
                        "recordType": "record",
                    }
                ],
                self._INDEXES,
            )

    def list_records(self, limit: int = 50, pinned_only: bool = False, type_: Optional[str] = None) -> list[dict]:
        with self._lock:
            rows = self.util.query_data(self._DB, {}, self._INDEXES)
        seen: set[str] = set()
        out: list[dict] = []
        for r in sorted(rows, key=lambda x: str(x.get("created_at", "")), reverse=True):
            s = str(r.get("stamp", ""))
            if not s or s in seen:
                continue
            seen.add(s)
            if type_ and str(r.get("type", "")) != type_:
                continue
            if pinned_only and not r.get("pinned", True):
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def find(self, stamp: str) -> Optional[dict]:
        with self._lock:
            rows = self.util.query_data(self._DB, {"stamp": stamp}, self._INDEXES)
        return rows[0] if rows else None

    def stamps(self) -> set[str]:
        with self._lock:
            rows = self.util.query_data(self._DB, {}, self._INDEXES)
        return {str(r.get("stamp", "")) for r in rows}

    def set_pinned(self, stamp: str, image: str, pinned: bool) -> bool:
        """更新作品收录状态；图片级标记存 images_pinned（True=收录，False=不收录）。

        批次默认收录状态在记录级 pinned 字段（新生成默认 False = 不收录）。
        手动 ★：显式写该图 True（批次默认 False 时仍收录）；取消：写 False。
        """
        with self._lock:
            rows = self.util.query_data(self._DB, {"stamp": stamp}, self._INDEXES)
            if not rows:
                return False
            rec = rows[0]
            img_pin: dict = dict(rec.get("images_pinned") or {})
            img_pin[image] = pinned
            rec["images_pinned"] = img_pin
            rec["pinned"] = not any(v is False for v in img_pin.values()) if img_pin else True
            self.util.delete_data(self._DB, {"stamp": stamp}, self._INDEXES)
            self.util.insert_data(self._DB, [rec], self._INDEXES)
            return True

    def set_category(self, stamp: str, category: str) -> bool:
        """更新批次作品分类（主页筛选用）。"""
        with self._lock:
            rows = self.util.query_data(self._DB, {"stamp": stamp}, self._INDEXES)
            if not rows:
                return False
            rec = rows[0]
            rec["category"] = category
            self.util.delete_data(self._DB, {"stamp": stamp}, self._INDEXES)
            self.util.insert_data(self._DB, [rec], self._INDEXES)
            return True

    def remove_image(self, stamp: str, image: str) -> bool:
        """从作品记录移除一张图；记录空则整批删除。"""
        with self._lock:
            rows = self.util.query_data(self._DB, {"stamp": stamp}, self._INDEXES)
            if not rows:
                return False
            rec = rows[0]
            imgs = list(rec.get("images", []))
            if image not in imgs:
                return False
            imgs.remove(image)
            if imgs:
                rec["images"] = imgs
                img_pin: dict = dict(rec.get("images_pinned") or {})
                img_pin.pop(image, None)
                rec["images_pinned"] = img_pin
                self.util.delete_data(self._DB, {"stamp": stamp}, self._INDEXES)
                self.util.insert_data(self._DB, [rec], self._INDEXES)
            else:
                self.util.delete_data(self._DB, {"stamp": stamp}, self._INDEXES)
            return True

    # ---------------- 产物收编 ----------------
    def ingest_batch(self, stamp: str, images: list[str], prompt: str, params: dict, type_: str, model: str, pinned: bool = True) -> None:
        """把 outputs/<stamp> 的图片复制进 db/images 并登记 works（幂等，可重刷记录）。"""
        # 生成时间以批次号（YYYYMMDD_HHMMSS）为准，避免用迁移/收编时刻
        created_at = _stamp_to_iso(stamp)
        copied: list[str] = []
        for img in images:
            dest = self.image_file(stamp, img)
            if dest.exists():
                copied.append(img)
                continue
            src = OUTPUT_DIR / stamp / img
            if src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied.append(img)
        if copied:
            self.add(stamp, type_, model, prompt, params, copied, created_at, pinned=pinned)

    def remove_files(self, stamp: str, image: str) -> None:
        """删除 db/images 与 outputs 下的图片文件（含空目录回收）。"""
        for p in (self.image_file(stamp, image), self.legacy_file(stamp, image)):
            try:
                if p.is_file():
                    p.unlink()
                parent = p.parent
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass

    # ---------------- 历史迁移 ----------------
    def migrate_legacy(self) -> int:
        """把 outputs/ 历史批次收编进 works 库（幂等，启动时重刷 prompt/params）。"""
        import re

        stamp_re = re.compile(r"^\d{8}_\d{6}$")
        img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        count = 0
        if not OUTPUT_DIR.is_dir():
            return 0
        for d in sorted(OUTPUT_DIR.iterdir()):
            if not d.is_dir() or not stamp_re.match(d.name):
                continue
            # 已收编的批次跳过：任务收编带类型（upscale/text-to-image），避免启动时被覆盖为 unknown
            if self.find(d.name):
                continue
            images = sorted(p.name for p in d.iterdir() if p.suffix.lower() in img_exts and not p.name.startswith("_"))
            if not images:
                continue
            prompt, params = "", {}
            pf = d / "input_prompt.txt"
            if pf.exists():
                prompt, params = self._parse_prompt_file(pf)
            self.ingest_batch(d.name, images, prompt, params or {}, "unknown", "")
            count += 1
        if count:
            print(f"[works] synced {count} batch(es) into works db")
        return count

    @staticmethod
    def _parse_prompt_file(prompt_file: Path) -> tuple[str, dict]:
        """解析 input_prompt.txt。

        三种格式：
          1) 纯文本提示词 → prompt=原文, params={}
          2) "[prompt] X [params] k1: v1 k2: v2" → 拆 prompt + params
          3) "X\n\n[params]\nkey: value\n..."（换行分隔）→ 拆 prompt + params
        """
        import re

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
            return "", {}
        if not text:
            return "", {}
        if text.startswith("[prompt]"):
            rest = text[len("[prompt]") :].strip()
        else:
            rest = text
        # 换行 [params]（兼容 "X\n\n[params]\nkey: v" 与 "[prompt] X\n\n[params]..."）
        m = re.split(r"\n?\[params\]\s*\n?", rest, maxsplit=1, flags=re.IGNORECASE)
        if len(m) == 2:
            return m[0].strip(), kv(m[1])
        # 单行 "[prompt] X [params] k: v"
        if text.startswith("[prompt]"):
            marker = " [params]"
            if marker in rest:
                p_part, _, param_part = rest.partition(marker)
                return p_part.strip(), kv(param_part)
        return rest.strip(), {}


def get_works_store() -> WorksStore:
    global _store
    if _store is None:
        _store = WorksStore(DB_DIR)
    return _store
