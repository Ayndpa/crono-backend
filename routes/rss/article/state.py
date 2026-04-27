from fastapi import APIRouter, Depends, HTTPException
from services.auth import get_current_user
from services.rss.article.state import (
    get_all_tags,
    get_today_update_count,
    mark_article_as_read,
)
from services.database import get_db
import sqlite3
from typing import List
from collections import Counter

router = APIRouter(prefix="/rss/article/state", tags=["article_state"])


@router.get("/today-update-count", response_model=int)
def get_today_update_count_endpoint(
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_today_update_count(db, current_user["id"])


@router.get("/tags", response_model=List[dict])
def get_tags_with_count(
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tags = get_all_tags(db, current_user["id"])
    tag_counts = Counter(tags)
    return [{"name": tag, "count": count} for tag, count in tag_counts.items()]


@router.post("/mark-as-read/{article_id}", response_model=bool)
def mark_article_as_read_endpoint(
    article_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        return mark_article_as_read(db, article_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
