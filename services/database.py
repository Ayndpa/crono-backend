import sqlite3
from threading import Lock
from typing import Iterator

from fastapi import HTTPException
import os


DATABASE_URL = "cronos.db"
_connection = None  # 全局唯一的 SQLite 连接
_connection_lock = Lock()  # 用于线程安全的锁


def initialize_database():
    """
    在包初始化时检查并执行 SQL 脚本以设置数据库。
    """
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row

        sql_dir = "sql"
        for file_name in os.listdir(sql_dir):
            if file_name.endswith(".sql"):
                file_path = os.path.join(sql_dir, file_name)
                with open(file_path, "r", encoding="utf-8") as f:
                    sql_script = f.read()
                conn.executescript(sql_script)
        ensure_schema_migrations(conn)
        conn.commit()
        print("SQL 脚本执行完成。")
    except FileNotFoundError:
        print("错误：无法找到 sql 目录或其中的 SQL 文件。")
    except sqlite3.Error as e:
        print(f"执行 SQL 脚本时出错: {e}")
        raise HTTPException(status_code=500, detail="SQL 脚本执行失败")
    finally:
        conn.close()


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """补齐旧数据库缺失的轻量字段。"""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(article_states)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "ai_translation" not in columns:
        cursor.execute("ALTER TABLE article_states ADD COLUMN ai_translation TEXT")


def get_global_connection() -> sqlite3.Connection:
    """
    获取全局唯一的 SQLite 连接，确保线程安全。
    """
    global _connection
    with _connection_lock:
        if _connection is None:
            _connection = sqlite3.connect(DATABASE_URL, check_same_thread=False)
            _connection.row_factory = sqlite3.Row
        return _connection


def get_db() -> Iterator[sqlite3.Connection]:
    """
    FastAPI 依赖项，提供全局唯一的 SQLite 连接。
    """
    try:
        conn = get_global_connection()
        yield conn
    except sqlite3.Error as e:
        print(f"数据库连接失败: {e}")
        raise HTTPException(status_code=500, detail="数据库连接失败")

# 在模块加载时初始化数据库
initialize_database()
