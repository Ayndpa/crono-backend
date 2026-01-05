import sqlite3
from typing import List, Optional
from fastapi import HTTPException, status
from pydantic import HttpUrl

from models.llm.config import LLMConfig, LLMConfigUpdate


def create_llm_config_service(db: sqlite3.Connection, config: LLMConfig) -> LLMConfig:
    """
    在数据库中创建一个新的 OpenAI API 配置。
    """
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO llm_config (base_url, model, api_key) VALUES (?, ?, ?)",
            (str(config.base_url), config.model, config.api_key)
        )
        db.commit()
        config_id = cursor.lastrowid
        config.id = config_id
        return config
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建配置失败: {e}")

def get_llm_config_service(db: sqlite3.Connection, config_id: int) -> Optional[LLMConfig]:
    """
    根据 ID 从数据库中获取一个 OpenAI API 配置。
    """
    cursor = db.cursor()
    cursor.execute("SELECT id, base_url, model, api_key FROM llm_config WHERE id = ?", (config_id,))
    row = cursor.fetchone()
    if row:
        return LLMConfig(**row)
    return None

def get_all_llm_config_service(db: sqlite3.Connection) -> List[LLMConfig]:
    """
    从数据库中获取所有 OpenAI API 配置。
    """
    cursor = db.cursor()
    cursor.execute("SELECT id, base_url, model, api_key FROM llm_config")
    return [LLMConfig(**row) for row in cursor.fetchall()]

def update_llm_config_service(db: sqlite3.Connection, config_id: int, config_update: LLMConfigUpdate) -> Optional[LLMConfig]:
    """
    更新数据库中现有的 OpenAI API 配置。
    """
    cursor = db.cursor()
    # 构建更新语句，只更新非 None 的字段
    updates = {k: v for k, v in config_update.dict(exclude_unset=True).items()}
    if not updates:
        return get_llm_config_service(db, config_id) # 没有要更新的字段，直接返回当前配置

    set_clauses = []
    values = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = ?")
        values.append(str(v) if isinstance(v, HttpUrl) else v) # HttpUrl 需要转为字符串

    query = f"UPDATE llm_config SET {', '.join(set_clauses)} WHERE id = ?"
    values.append(config_id)

    try:
        cursor.execute(query, tuple(values))
        db.commit()
        if cursor.rowcount == 0:
            return None # 没有找到要更新的配置
        return get_llm_config_service(db, config_id)
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新配置失败: {e}")

def delete_llm_config_service(db: sqlite3.Connection, config_id: int) -> bool:
    """
    从数据库中删除一个 OpenAI API 配置。
    """
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM llm_config WHERE id = ?", (config_id,))
        db.commit()
        return cursor.rowcount > 0 # 如果删除了行，则返回 True
    except sqlite3.Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除配置失败: {e}")