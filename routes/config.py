from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from typing import List
from services.database import get_db
from services.auth import get_current_user
from models.config import Config

from services.config import (
    get_config,
    update_config,
    list_configs,
)

router = APIRouter(prefix="/config")


@router.get("/", response_model=List[Config])
def list_configs_route(
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return list_configs(db, current_user["id"])


@router.post("/", response_model=List[Config])
def update_configs_route(
    configs: dict,
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    updated = []
    for key, value in configs.items():
        try:
            updated.append(update_config(db, current_user["id"], key=key, value=value))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return updated


@router.get("/{key}", response_model=Config)
def get_config_route(
    key: str,
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    config = get_config(db, current_user["id"], key=key)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return config


@router.put("/{key}", response_model=Config)
def update_config_route(
    key: str,
    config: Config,
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        return update_config(db, current_user["id"], key=key, value=config.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
