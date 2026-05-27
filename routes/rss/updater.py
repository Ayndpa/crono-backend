from fastapi import APIRouter, Depends, HTTPException, Request
from services.auth import get_current_user
from services.database import get_db
from services.rss.feed import get_feed_by_id

router = APIRouter(
    prefix="/rss/updater",
    tags=["RSS Updater"]
)

@router.post("/refresh/all")
def refresh_all_feeds(request: Request):
    updater = request.app.state.rss_updater
    updater.refresh_now()
    return {"message": "已立即刷新所有 RSS 源。"}

@router.post("/refresh/{feed_id}")
def refresh_feed(
    feed_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    updater = request.app.state.rss_updater
    db_generator = get_db()
    try:
        conn = next(db_generator)
        feed = get_feed_by_id(conn, feed_id, current_user["id"])
        if not feed:
            raise HTTPException(status_code=404, detail=f"未找到 ID 为 {feed_id} 的 RSS 源。")
        updater.process_feed(conn, feed)
        return {"message": f"已立即刷新 RSS 源 (id: {feed_id})。"}
    except StopIteration:
        raise HTTPException(status_code=500, detail="数据库连接失败。")
    finally:
        updater.safely_close_generator(db_generator)