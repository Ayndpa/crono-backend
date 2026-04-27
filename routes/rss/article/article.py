from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from services.auth import get_current_user
from services.database import get_db
from services.rss.article.article import get_articles

router = APIRouter(prefix="/rss/article")


@router.get("/latest", summary="获取最新文章及其状态")
async def fetch_latest_articles(
    limit: int = 50,
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        articles = get_articles(db, user_id=current_user["id"], feed_id=None, limit=limit)
        return {"detail": "获取成功", "articles": articles}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文章失败: {e}")


@router.get("/{feed_id}", summary="获取指定feed_id的文章")
async def fetch_articles_by_feed_id(
    feed_id: int,
    limit: int = 50,
    db: Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        articles = get_articles(db, user_id=current_user["id"], feed_id=feed_id, limit=limit)
        return {"detail": "获取成功", "articles": articles}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文章失败: {e}")
