import sqlite3
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from models.rss.feed import Feed
from services.auth import get_current_user
from services.database import get_db
from services.rss.feed import create_feed, delete_feed, get_all_feeds, get_feed_by_id, update_feed

router = APIRouter(prefix="/rss/feed", tags=["feeds"])


@router.get("/", response_model=List[Feed])
def read_feeds(
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_all_feeds(db, current_user["id"])


@router.get("/{feed_id}", response_model=Feed)
def read_feed_by_id(
    feed_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    feed = get_feed_by_id(db, feed_id, current_user["id"])
    if not feed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return feed


@router.post("/", response_model=Feed, status_code=status.HTTP_201_CREATED)
def create_new_feed(
    feed: Feed,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return create_feed(db, current_user["id"], name=feed.name, url=feed.url)


@router.put("/{feed_id}", response_model=Feed)
def update_existing_feed(
    feed_id: int,
    feed: Feed,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    updated = update_feed(db, feed_id, current_user["id"], name=feed.name, url=feed.url)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return updated


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_feed(
    feed_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not delete_feed(db, feed_id, current_user["id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
