"""MooFile 本地存储封装（对齐 deepagents_acp / moofile_base 规范）。

纯表用法，不引入 embedding 栈。所有写操作由调用方保证串行（进程级锁）。
"""

import os
import uuid

from moofile import Collection


class MooFileUtil:
    """管理 moofile BSON 集合（普通表，非向量）。"""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    # ---------------- 库级操作 ----------------
    def create_database(self, db_name: str) -> str:
        os.makedirs(self.root_dir, exist_ok=True)
        db_path = self.get_database_path(db_name)
        if os.path.exists(db_path):
            raise FileExistsError(f"Database '{db_name}' already exists.")
        with Collection(db_path):
            pass
        return db_path

    def delete_database(self, db_name: str) -> None:
        db_path = self.get_database_path(db_name)
        if not os.path.isfile(db_path):
            raise FileNotFoundError(f"Database '{db_name}' does not exist.")
        os.remove(db_path)
        meta_path = f"{db_path}.meta"
        if os.path.exists(meta_path):
            os.remove(meta_path)

    def list_databases(self) -> list[str]:
        if not os.path.isdir(self.root_dir):
            return []
        return sorted(
            os.path.splitext(name)[0]
            for name in os.listdir(self.root_dir)
            if name.endswith(".bson") and os.path.isfile(os.path.join(self.root_dir, name))
        )

    def database_exists(self, db_name: str) -> bool:
        return os.path.isfile(self.get_database_path(db_name))

    def get_database_path(self, db_name: str) -> str:
        filename = db_name if db_name.endswith(".bson") else f"{db_name}.bson"
        return os.path.join(self.root_dir, filename)

    def valid_database(self, db_name: str) -> None:
        if not self.database_exists(db_name):
            raise FileNotFoundError(f"Database '{db_name}' does not exist.")

    # ---------------- 数据操作 ----------------
    def insert_data(self, db_name: str, data: list[dict], indexes: list) -> None:
        """批量插入记录。indexes 为索引字段名列表（小数据集可空）。"""
        self.valid_database(db_name)
        db_path = self.get_database_path(db_name)
        with Collection(db_path, indexes=indexes) as db:
            db.insert_many(data)

    def query_data(self, db_name: str, query: dict, indexes: list) -> list[dict]:
        """按条件查询，返回全部匹配记录。query 为空返回全表。"""
        self.valid_database(db_name)
        db_path = self.get_database_path(db_name)
        if not query:
            query = {}
        with Collection(db_path, indexes=indexes) as db:
            return db.find(query).to_list()

    def update_data(self, db_name: str, query: dict, update: dict, indexes: list) -> None:
        """对匹配记录应用字段更新（set 语义）。"""
        self.valid_database(db_name)
        db_path = self.get_database_path(db_name)
        if not query:
            query = {}
        with Collection(db_path, indexes=indexes) as db:
            db.update_many(query, set=update)

    def delete_data(self, db_name: str, query: dict, indexes: list) -> None:
        """删除匹配记录。query 为空清空全表。"""
        self.valid_database(db_name)
        db_path = self.get_database_path(db_name)
        if not query:
            query = {}
        with Collection(db_path, indexes=indexes) as db:
            db.delete_many(query)

    def count_data(self, db_name: str, query: dict, indexes: list) -> int:
        self.valid_database(db_name)
        db_path = self.get_database_path(db_name)
        if not query:
            query = {}
        with Collection(db_path, indexes=indexes) as db:
            return db.count(query)

    @staticmethod
    def generate_id(prefix: str = "") -> str:
        return f"id_{prefix}_{str(uuid.uuid4())[0:8]}"
