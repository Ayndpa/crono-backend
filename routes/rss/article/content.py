from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import services.playwright as pw_service
from services.auth import get_current_user
from services.database import get_db

router = APIRouter(prefix="/rss/article")


class ArticleContentRequest(BaseModel):
    url: str
    bypass_cache: bool = False


@router.post("/content")
async def get_article_content(
    body: ArticleContentRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """
    抓取文章正文 HTML。
    - 优先返回缓存
    - 触发验证码时返回 captcha=True，前端降级为 iframe
    """
    browser = request.app.state.browser
    try:
        result = await pw_service.scrape_article(browser, body.url, bypass_cache=body.bypass_cache)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取失败: {e}")

    return JSONResponse({
        "html": result["html"],
        "title": result["title"],
        "from_cache": result["from_cache"],
        "captcha": result["captcha"],
    })
