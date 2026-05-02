from datetime import datetime
from typing import List
from fastapi import HTTPException
import sqlite3

def get_all_tags(db: sqlite3.Connection, user_id: int) -> List[str]:
    """
    获取当前用户所有文章状态中的唯一标签。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT s.tags FROM article_states s
            JOIN articles a ON s.article_id = a.id
            JOIN rss_feeds f ON a.feed_id = f.id
            WHERE f.user_id = ?
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        tags = set()
        for row in rows:
            if row["tags"]:
                tags.update(row["tags"].split(","))
        return list(tags)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")


def get_today_update_count(db: sqlite3.Connection, user_id: int) -> int:
    """
    获取当前用户今日更新的文章数量。
    """
    try:
        cursor = db.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM article_states s
            JOIN articles a ON s.article_id = a.id
            JOIN rss_feeds f ON a.feed_id = f.id
            WHERE f.user_id = ? AND DATE(s.updated_at) = ?
            """,
            (user_id, today),
        )
        row = cursor.fetchone()
        return row["count"] if row else 0
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")
    
def mark_article_as_read(db: sqlite3.Connection, article_id: int) -> None:
    """
    将指定文章标记为已读。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE article_states
            SET is_read = 1, updated_at = ?
            WHERE article_id = ?
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), article_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="文章未找到")
        else:
            return True
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")
    
def save_ai_summary(db: sqlite3.Connection, article_id: int, ai_summary: str) -> None:
    """
    保存AI生成的总结信息到指定文章状态。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE article_states
            SET ai_summary = ?, updated_at = ?
            WHERE article_id = ?
            """,
            (ai_summary, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), article_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="文章未找到")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")


def save_ai_translation(db: sqlite3.Connection, article_id: int, ai_translation: str) -> None:
    """
    保存 AI 全文翻译到指定文章状态。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE article_states
            SET ai_translation = ?, updated_at = ?
            WHERE article_id = ?
            """,
            (ai_translation, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), article_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="文章未找到")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")
    
def get_ai_summary(db: sqlite3.Connection, article_id: int) -> str:
    """
    获取指定文章的AI生成总结信息。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT ai_summary
            FROM article_states
            WHERE article_id = ?
            """,
            (article_id,),
        )
        row = cursor.fetchone()
        if row and row["ai_summary"]:
            return row["ai_summary"]
        else:
            return None
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")


def get_ai_translation(db: sqlite3.Connection, article_id: int) -> str:
    """
    获取指定文章的 AI 全文翻译。
    """
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT ai_translation
            FROM article_states
            WHERE article_id = ?
            """,
            (article_id,),
        )
        row = cursor.fetchone()
        if row and row["ai_translation"]:
            return row["ai_translation"]
        else:
            return None
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"数据库错误: {e}")
