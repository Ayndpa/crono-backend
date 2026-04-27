from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
import sqlite3

from models.llm.config import LLMConfig, LLMConfigUpdate
from services.auth import get_current_user
from services.database import get_db
from services.llm.config import (
    create_llm_config_service,
    delete_llm_config_service,
    get_all_llm_config_service,
    get_llm_config_service,
    update_llm_config_service,
)

router = APIRouter(prefix="/llm", tags=["LLMs"])


@router.post("/llm_config", response_model=LLMConfig, status_code=status.HTTP_201_CREATED)
def create_llm_config(
    config: LLMConfig,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return create_llm_config_service(db, current_user["id"], config)


@router.get("/llm_config", response_model=List[LLMConfig])
def get_all_llm_config(
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_all_llm_config_service(db, current_user["id"])


@router.get("/llm_config/{config_id}", response_model=LLMConfig)
def get_llm_config(
    config_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    config = get_llm_config_service(db, config_id, current_user["id"])
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenAI 配置未找到")
    return config


@router.patch("/llm_config/{config_id}", response_model=LLMConfig)
def update_llm_config(
    config_id: int,
    config_update: LLMConfigUpdate,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    updated = update_llm_config_service(db, config_id, current_user["id"], config_update)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenAI 配置未找到")
    return updated


@router.delete("/llm_config/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_config(
    config_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not delete_llm_config_service(db, config_id, current_user["id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenAI 配置未找到")
