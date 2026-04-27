from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from collections import defaultdict
from typing import Dict, Any, Optional
import asyncio
import hashlib

from services.llm.chat import OpenAIStreamClient
import services.playwright as pw_service
from services.rss.article.state import save_ai_summary, get_ai_summary
from services.database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/llm")


class AISummaryRequest(BaseModel):
    url: str
    article_id: Optional[int] = None  # RSS 文章有 id；浏览器模式可不传


class TranslationRequest(BaseModel):
    url: str
    article_id: Optional[int] = None


# sessions key: article_id（int）或 url hash（str）
sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})

podcast_sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})

translation_sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})


def _session_key(article_id: Optional[int], url: str) -> Any:
    """article_id 存在时用 int，否则用 URL 的 sha256 前 16 位作为 key。"""
    if article_id is not None:
        return article_id
    return hashlib.sha256(url.encode()).hexdigest()[:16]


SUMMARY_SYSTEM_PROMPT = (
    "你是一个专业的文章摘要专家。请对文章进行深度提炼，用中文输出一段紧凑的摘要。"
    "要求：\n"
    "1. 直接输出摘要内容，严禁包含任何开场白、分析过程或引导性文字；\n"
    "2. 摘要必须极其精炼，篇幅严格控制在一段话内；\n"
    "3. 准确捕捉核心观点与关键事实；\n"
    "4. 适当使用 Markdown 加粗关键词以提升视觉阅读效率；\n"
    "5. 无论原文是何种语言（英文、日文等），均直接输出中文摘要，无需保留原文。"
)

PODCAST_SYSTEM_PROMPT = (
    "你是一位播客主播，擅长将文章改写为自然流畅的中文口语播客稿。\n"
    "要求：\n"
    "1. 以第一人称口吻娓娓道来，像在和听众聊天，语气亲切自然；\n"
    "2. 去掉所有 Markdown 符号（#、*、`、- 等），输出纯文本；\n"
    "3. 保留文章的核心观点和关键信息，适当补充过渡语让内容连贯；\n"
    "4. 篇幅控制在 300～500 字，适合 2～3 分钟朗读；\n"
    "5. 直接输出播客正文，不要有标题、开场白说明或任何元信息。"
)

TRANSLATION_SYSTEM_PROMPT = (
    "你是一位专业的技术文章翻译专家，擅长将外文技术内容翻译为地道的中文。\n"
    "翻译要求：\n"
    "1. 进行全篇语义意译，而非逐句直译，确保中文表达自然流畅；\n"
    "2. 准确传达原文的技术含义和语气，不遗漏任何关键信息；\n"
    "3. 对专业技术名词（如框架名、协议名、算法名等）保留英文原名，并在首次出现时用括号附上中文解释，例如：RAG（检索增强生成）；\n"
    "4. 保留原文的 Markdown 格式结构（标题、列表、代码块等）；\n"
    "5. 直接输出译文，不要添加任何说明性前言或注释。"
)


async def _make_stream_session(
    sessions_dict: Dict,
    key: Any,
    messages: list,
    db,
    user_id: int,
    persist_article_id: Optional[int] = None,
):
    """
    通用流式 producer 启动逻辑。
    persist_article_id 不为 None 时，生成完毕后写入 DB。
    """
    session = sessions_dict[key]
    async with session["lock"]:
        if session["producer_task"] and not session["producer_task"].done():
            return

        async def producer():
            client = OpenAIStreamClient(user_id)
            try:
                async for chunk in client.stream_chat_completion(messages):
                    session["buffer"].append(chunk)
                    to_remove = []
                    for q in session["subscribers"]:
                        try:
                            q.put_nowait(chunk)
                        except asyncio.QueueFull:
                            pass
                        except Exception:
                            to_remove.append(q)
                    for q in to_remove:
                        session["subscribers"].discard(q)

                if persist_article_id is not None:
                    full_text = "".join(session["buffer"])
                    save_ai_summary(db, persist_article_id, full_text)

            except Exception:
                for q in list(session["subscribers"]):
                    try:
                        q.put_nowait(None)
                    except Exception:
                        pass
                session["producer_task"] = None
                raise
            else:
                for q in list(session["subscribers"]):
                    try:
                        q.put_nowait(None)
                    except Exception:
                        pass
                sessions_dict.pop(key, None)

        session["producer_task"] = asyncio.create_task(producer())


def _make_event_generator(session: dict):
    """通用 SSE 事件生成器，返回 (queue, async_generator)。"""
    q: asyncio.Queue = asyncio.Queue()
    session["subscribers"].add(q)

    async def event_generator():
        try:
            for chunk in session["buffer"]:
                yield chunk
            while True:
                item = await q.get()
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            session["subscribers"].discard(q)
            raise
        finally:
            session["subscribers"].discard(q)

    return q, event_generator


@router.post("/ai_summary/stream")
async def ai_summary_stream(
    payload: AISummaryRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    key = _session_key(payload.article_id, payload.url)

    # 有 article_id 时才查 DB 缓存
    if payload.article_id is not None:
        existing = get_ai_summary(db, payload.article_id)
        if existing:
            return StreamingResponse(iter([existing]), media_type="text/plain")

    session = sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = await pw_service.scrape_article(browser, payload.url)
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": article_content},
        ]
        await _make_stream_session(
            sessions, key, messages, db, current_user["id"],
            persist_article_id=payload.article_id,
        )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/plain")


@router.post("/translation/stream")
async def translation_stream(
    payload: TranslationRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上下文感知翻译，结果不持久化到 DB。"""
    key = _session_key(payload.article_id, payload.url)
    session = translation_sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = await pw_service.scrape_article(browser, payload.url)
        messages = [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": article_content},
        ]
        await _make_stream_session(
            translation_sessions, key, messages, db, current_user["id"],
            persist_article_id=None,
        )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/plain")


class ArticleQARequest(BaseModel):
    url: str
    article_id: Optional[int] = None
    question: str


ARTICLE_QA_SYSTEM_PROMPT = (
    "你是一个专业的文章问答助手。用户会提供一篇文章的内容，并向你提问。\n"
    "要求：\n"
    "1. 严格基于文章内容回答，不要编造文章中没有的信息；\n"
    "2. 如果文章中没有相关信息，请明确告知用户；\n"
    "3. 回答简洁准确，适当使用 Markdown 格式提升可读性；\n"
    "4. 用中文回答，无论原文是何种语言。"
)

# qa sessions 不缓存（每次问题不同）
qa_sessions: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})


@router.post("/article_qa/stream")
async def article_qa_stream(
    payload: ArticleQARequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """针对单篇文章的流式问答接口。"""
    import uuid
    key = str(uuid.uuid4())  # 每次问答独立 session，不复用
    session = qa_sessions[key]

    browser = getattr(request.app.state, "browser", None)
    if not browser:
        raise HTTPException(status_code=503, detail="Browser not available")
    article_content = await pw_service.scrape_article(browser, payload.url)
    messages = [
        {"role": "system", "content": ARTICLE_QA_SYSTEM_PROMPT},
        {"role": "user", "content": f"以下是文章内容：\n\n{article_content}\n\n请回答：{payload.question}"},
    ]
    await _make_stream_session(
        qa_sessions, key, messages, db, current_user["id"],
        persist_article_id=None,
    )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/plain")


class PodcastRequest(BaseModel):
    url: str
    article_id: Optional[int] = None


@router.post("/podcast/stream")
async def podcast_stream(
    payload: PodcastRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """将文章改写为播客口语稿，流式返回纯文本。"""
    key = "podcast_" + str(_session_key(payload.article_id, payload.url))
    session = podcast_sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = await pw_service.scrape_article(browser, payload.url)
        messages = [
            {"role": "system", "content": PODCAST_SYSTEM_PROMPT},
            {"role": "user", "content": article_content},
        ]
        await _make_stream_session(
            podcast_sessions, key, messages, db, current_user["id"],
            persist_article_id=None,
        )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/plain")
