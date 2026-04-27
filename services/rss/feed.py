import sqlite3
from typing import List, Optional

from fastapi import HTTPException
from pydantic import HttpUrl

from models.rss.feed import Feed


def get_all_feeds(db: sqlite3.Connection, user_id: Optional[int] = None) -> List[Feed]:
    try:
        cursor = db.cursor()
        if user_id is not None:
            cursor.execute(
                "SELECT id, name, url, is_active FROM rss_feeds WHERE user_id = ?",
                (user_id,),
            )
        else:
            cursor.execute("SELECT id, name, url, is_active FROM rss_feeds")
        return [Feed(**feed) for feed in cursor.fetchall()]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"获取所有 Feed 失败: {e}")


def get_feed_by_id(db: sqlite3.Connection, feed_id: int, user_id: int) -> Optional[Feed]:
    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, url, is_active FROM rss_feeds WHERE id = ? AND user_id = ?",
            (feed_id, user_id),
        )
        feed = cursor.fetchone()
        return Feed(**feed) if feed else None
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"根据 ID 获取 Feed 失败: {e}")


def create_feed(db: sqlite3.Connection, user_id: int, name: str, url: HttpUrl) -> Optional[Feed]:
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO rss_feeds (user_id, name, url, is_active) VALUES (?, ?, ?, ?)",
            (user_id, name, str(url), True),
        )
        db.commit()
        return get_feed_by_id(db, cursor.lastrowid, user_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="该 URL 的 Feed 已存在。")
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建 Feed 失败: {e}")


def update_feed(
    db: sqlite3.Connection, feed_id: int, user_id: int, name: str, url: HttpUrl, is_active: bool = True
) -> Optional[Feed]:
    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE rss_feeds SET name = ?, url = ?, is_active = ? WHERE id = ? AND user_id = ?",
            (name, str(url), is_active, feed_id, user_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            return None
        return get_feed_by_id(db, feed_id, user_id)
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新 Feed 失败: {e}")


def delete_feed(db: sqlite3.Connection, feed_id: int, user_id: int) -> bool:
    try:
        cursor = db.cursor()
        cursor.execute(
            "DELETE FROM rss_feeds WHERE id = ? AND user_id = ?",
            (feed_id, user_id),
        )
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除 Feed 失败: {e}")
