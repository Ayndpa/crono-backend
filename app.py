from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from routes.llm import ai_summary, chat, config as llm_config, entities as llm_entities
from routes.rss import feed, updater
from routes import config
from routes import auth
from fastapi.middleware.cors import CORSMiddleware

from routes.rss.article import article, state, content as article_content
from services.rss.updater import RSSUpdater
import threading
import services.playwright as pw_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动 Playwright（只做一次）
    pw, browser = await pw_service.startup_playwright()
    app.state.playwright = pw
    app.state.browser = browser

    # 启动 RSSUpdater
    rss_updater = RSSUpdater()
    app.state.rss_updater = rss_updater

    try:
        # 在后台启动 RSS 更新程序
        updater_thread = threading.Thread(target=rss_updater.start, daemon=True)
        updater_thread.start()

        yield
    finally:
        # 关闭资源
        await pw_service.shutdown_playwright(app.state.playwright, app.state.browser)

        # 停止 RSS 更新程序
        rss_updater.stop()

def create_app() -> FastAPI:
    """
    工厂函数，用于创建和配置 FastAPI 应用实例。
    """
    app = FastAPI(lifespan=lifespan)

    # 配置 CORS 中间件
    origins = [
        "http://localhost:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,          # 允许的来源列表
        allow_credentials=True,         # 允许发送 cookies
        allow_methods=["*"],            # 允许所有 HTTP 方法 (GET, POST, PUT, DELETE, PATCH, OPTIONS等)
        allow_headers=["*"],            # 允许所有请求头
    )

    # 将路由模块添加到应用中
    # llm
    app.include_router(llm_config.router)
    app.include_router(chat.router)
    app.include_router(ai_summary.router)
    app.include_router(llm_entities.router)

    # rss    
    app.include_router(feed.router)
    app.include_router(state.router)
    app.include_router(article.router)
    app.include_router(article_content.router)
    app.include_router(updater.router)

    # config
    app.include_router(config.router)

    # auth
    app.include_router(auth.router)

    return app

# 创建 FastAPI 应用实例
app = create_app()