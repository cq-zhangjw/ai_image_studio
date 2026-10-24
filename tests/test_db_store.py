"""moofile 本地存储测试：目录布局 / 任务落库 / 统计落库 / 重启恢复。

用法：
    & ".venv\Scripts\python.exe" tests\test_db_store.py
"""

import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "app"))

from db_store import DbStore  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_root = Path(tmp) / "db"
        print("=== 1. 首次初始化（自动建库 + meta.json）===")
        store = DbStore(db_root)
        print("tasks_root:", store.tasks_root.name)
        print("stats_root:", store.stats_root.name)
        meta = (store.tasks_root / "meta.json").read_text(encoding="utf-8")
        assert '"name": "tasks"' in meta and '"type": "normal"' in meta, meta
        assert store.tasks_util.list_databases() == ["db"], store.tasks_util.list_databases()
        print("  目录与 meta.json OK")

        print("=== 2. 任务落库（成功/失败/取消 + 统计）===")
        now = datetime.datetime.now().isoformat(timespec="seconds")
        store.save_task(
            {
                "id": "task_test_ok",
                "type": "text-to-image",
                "status": "succeeded",
                "model": "z-image-turbo",
                "prompt": "test poster",
                "params": {"width": 1024, "height": 1536, "num_inference_steps": 8},
                "outputs": ["/api/outputs/20261022_000000/output_01.png"],
                "elapsed_seconds": 24.8,
                "steps_per_second": 0.32,
                "model_load_seconds": 12.4,
                "error": None,
                "created_at": now,
                "finished_at": now,
            }
        )
        store.save_task(
            {
                "id": "task_test_fail",
                "type": "edit",
                "status": "failed",
                "model": "qwen-image-2.1",
                "prompt": "broken",
                "params": {},
                "outputs": [],
                "elapsed_seconds": None,
                "steps_per_second": None,
                "model_load_seconds": None,
                "error": "RuntimeError: oom",
                "created_at": now,
                "finished_at": now,
            }
        )
        store.save_stat(
            {
                "id": "id_stat_abc12345",
                "model": "z-image-turbo",
                "elapsed_seconds": 24.8,
                "steps_per_second": 0.32,
                "model_load_seconds": 12.4,
                "created_at": now,
            }
        )
        tasks = store.load_tasks()
        assert len(tasks) == 2, tasks
        assert all(r.get("recordType") == "record" for r in tasks), tasks
        stats = store.recent_stats()
        assert len(stats) == 1 and stats[0]["id"] == "id_stat_abc12345", stats
        print("  任务/统计落库 + recordType OK")

        print("=== 3. 重启恢复（同目录重新初始化 → 数据仍在）===")
        store2 = DbStore(db_root)  # 模拟服务重启
        tasks2 = store2.load_tasks()
        assert len(tasks2) == 2, tasks2
        by_id = {r["id"]: r for r in tasks2}
        assert by_id["task_test_ok"]["status"] == "succeeded"
        assert by_id["task_test_fail"]["error"].startswith("RuntimeError")
        print("  重启恢复 OK，记录数 =", len(tasks2))

        print("=== 4. upsert（同 id 覆盖）===")
        store.save_task(
            {
                "id": "task_test_ok",
                "type": "text-to-image",
                "status": "succeeded",
                "model": "z-image-turbo",
                "prompt": "test poster v2",
                "params": {},
                "outputs": ["/api/outputs/x.png"],
                "elapsed_seconds": 20.0,
                "steps_per_second": 0.4,
                "model_load_seconds": 12.0,
                "error": None,
                "created_at": now,
                "finished_at": now,
            }
        )
        assert len(store.load_tasks()) == 2, store.load_tasks()
        assert store.get_task("task_test_ok")["prompt"] == "test poster v2"
        print("  upsert OK（不重复插入）")

    print("\n全部测试通过 ✔")


if __name__ == "__main__":
    main()
