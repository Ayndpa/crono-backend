from sqlite3 import Connection
from typing import List, Optional
from models.config import Config


def ensure_user_defaults(db: Connection, user_id: int) -> None:
    """
    为新用户插入默认配置（幂等）。
    """
    defaults = [
        ('llm_config_id', None),
    ]
    cursor = db.cursor()
    for key, value in defaults:
        cursor.execute(
            "INSERT OR IGNORE INTO config (user_id, key, value) VALUES (?, ?, ?)",
            (user_id, key, value),
        )
    db.commit()


def get_config(db: Connection, user_id: int, key: str) -> Optional[Config]:
    cursor = db.cursor()
    cursor.execute(
        "SELECT key, value FROM config WHERE user_id = ? AND key = ?",
        (user_id, key),
    )
    row = cursor.fetchone()
    if row:
        return Config(key=row["key"], value=row["value"])
    return None


def update_config(db: Connection, user_id: int, key: str, value: str) -> Config:
    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE config SET value = ? WHERE user_id = ? AND key = ?",
            (value, user_id, key),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Config key '{key}' does not exist for this user.")
        db.commit()
        return Config(key=key, value=value)
    except Exception as e:
        db.rollback()
        raise ValueError(f"Failed to update config: {e}")


def list_configs(db: Connection, user_id: int) -> List[Config]:
    cursor = db.cursor()
    cursor.execute(
        "SELECT key, value FROM config WHERE user_id = ?",
        (user_id,),
    )
    rows = cursor.fetchall()
    return [Config(key=row["key"], value=row["value"]) for row in rows]
