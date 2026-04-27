import sqlite3
from typing import List, Optional
from fastapi import HTTPException, status
from pydantic import HttpUrl

from models.llm.config import LLMConfig, LLMConfigUpdate


def create_llm_config_service(db: sqlite3.Connection, user_id: int, config: LLMConfig) -> LLMConfig:
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO llm_config (user_id, base_url, model, api_key) VALUES (?, ?, ?, ?)",
            (user_id, str(config.base_url), config.model, config.api_key),
        )
        db.commit()
        config.id = cursor.lastrowid
        return config
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建配置失败: {e}")


def get_llm_config_service(db: sqlite3.Connection, config_id: int, user_id: int) -> Optional[LLMConfig]:
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, base_url, model, api_key FROM llm_config WHERE id = ? AND user_id = ?",
        (config_id, user_id),
    )
    row = cursor.fetchone()
    return LLMConfig(**row) if row else None


def get_all_llm_config_service(db: sqlite3.Connection, user_id: int) -> List[LLMConfig]:
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, base_url, model, api_key FROM llm_config WHERE user_id = ?",
        (user_id,),
    )
    return [LLMConfig(**row) for row in cursor.fetchall()]


def update_llm_config_service(
    db: sqlite3.Connection, config_id: int, user_id: int, config_update: LLMConfigUpdate
) -> Optional[LLMConfig]:
    cursor = db.cursor()
    updates = {k: v for k, v in config_update.dict(exclude_unset=True).items()}
    if not updates:
        return get_llm_config_service(db, config_id, user_id)

    set_clauses = []
    values = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = ?")
        values.append(str(v) if isinstance(v, HttpUrl) else v)

    query = f"UPDATE llm_config SET {', '.join(set_clauses)} WHERE id = ? AND user_id = ?"
    values.extend([config_id, user_id])

    try:
        cursor.execute(query, tuple(values))
        db.commit()
        if cursor.rowcount == 0:
            return None
        return get_llm_config_service(db, config_id, user_id)
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新配置失败: {e}")


def delete_llm_config_service(db: sqlite3.Connection, config_id: int, user_id: int) -> bool:
    cursor = db.cursor()
    try:
        cursor.execute(
            "DELETE FROM llm_config WHERE id = ? AND user_id = ?",
            (config_id, user_id),
        )
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除配置失败: {e}")
