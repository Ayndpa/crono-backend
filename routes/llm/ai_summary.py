import base64
import json

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from collections import defaultdict
from typing import Dict, Any, Optional
import asyncio
import hashlib

from services.llm.chat import OpenAIStreamClient
import services.playwright as pw_service
from services.rss.article.state import (
    save_ai_summary,
    get_ai_summary,
    save_ai_translation,
    get_ai_translation,
)
from services.database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/llm")


class AISummaryRequest(BaseModel):
    url: str
    article_id: Optional[int] = None  # RSS 文章有 id；浏览器模式可不传


class AISummaryCacheRequest(BaseModel):
    article_id: Optional[int] = None


class TranslationRequest(BaseModel):
    url: str
    article_id: Optional[int] = None


class TranslationCacheRequest(BaseModel):
    article_id: Optional[int] = None


# sessions key: article_id（int）或 url hash（str）
sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "content_buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})

podcast_sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "content_buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})

translation_sessions: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "content_buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock(),
})


def _session_key(article_id: Optional[int], url: str) -> Any:
    """article_id 存在时用 int，否则用 URL 的 sha256 前 16 位作为 key。"""
    if article_id is not None:
        return article_id
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _article_prompt_text(article: dict) -> str:
    """从抓取结果中提取可发送给 LLM 的字符串正文。"""
    if article.get("captcha"):
        raise HTTPException(status_code=422, detail="无法抓取文章内容（验证码拦截）")

    title = article.get("title") or ""
    html = article.get("html") or ""
    if not html.strip():
        raise HTTPException(status_code=422, detail="无法抓取文章正文")

    if title.strip():
        return f"标题：{title}\n\n正文：\n{html}"
    return html


def _encode_stream_event(event: dict[str, str]) -> bytes:
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
    encoded = base64.b64encode(payload).decode("utf-8")
    return f"data: {encoded}\n\n".encode("utf-8")


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
    persist_kind: str = "summary",
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
                    if chunk.get("type") == "content":
                        session["content_buffer"].append(chunk["text"])
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
                    full_text = "".join(session["content_buffer"])
                    if persist_kind == "translation":
                        save_ai_translation(db, persist_article_id, full_text)
                    else:
                        save_ai_summary(db, persist_article_id, full_text)

            except Exception as e:
                error_text = f"\n生成失败：{e}"
                session["buffer"].append(error_text)
                for q in list(session["subscribers"]):
                    try:
                        q.put_nowait(error_text)
                        q.put_nowait(None)
                    except Exception:
                        pass
                session["producer_task"] = None
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
                yield _encode_stream_event(chunk)
            while True:
                item = await q.get()
                if item is None:
                    break
                yield _encode_stream_event(item)
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
            return StreamingResponse(iter([_encode_stream_event({"type": "content", "text": existing})]), media_type="text/event-stream")

    session = sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = _article_prompt_text(
            await pw_service.scrape_article(browser, payload.url)
        )
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
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/ai_summary/cache")
async def ai_summary_cache(
    payload: AISummaryCacheRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """只检查已生成的文章摘要，不触发生成。"""
    if payload.article_id is None:
        return {"summary": None}

    return {"summary": get_ai_summary(db, payload.article_id)}


@router.post("/translation/stream")
async def translation_stream(
    payload: TranslationRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上下文感知翻译，结果持久化到 DB。"""
    key = _session_key(payload.article_id, payload.url)

    if payload.article_id is not None:
        existing = get_ai_translation(db, payload.article_id)
        if existing:
            return StreamingResponse(iter([_encode_stream_event({"type": "content", "text": existing})]), media_type="text/event-stream")

    session = translation_sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = _article_prompt_text(
            await pw_service.scrape_article(browser, payload.url)
        )
        messages = [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": article_content},
        ]
        await _make_stream_session(
            translation_sessions, key, messages, db, current_user["id"],
            persist_article_id=payload.article_id,
            persist_kind="translation",
        )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/translation/cache")
async def translation_cache(
    payload: TranslationCacheRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """只检查已生成的全文翻译，不触发生成。"""
    if payload.article_id is None:
        return {"translation": None}

    return {"translation": get_ai_translation(db, payload.article_id)}


class ArticleQARequest(BaseModel):
    url: str
    article_id: Optional[int] = None
    question: str


class SelectionAssistRequest(BaseModel):
    action: str
    text: str
    article_title: Optional[str] = None
    article_context: Optional[str] = None


ARTICLE_QA_SYSTEM_PROMPT = (
    "你是一个专业的文章问答助手。用户会提供一篇文章的内容，并向你提问。\n"
    "要求：\n"
    "1. 严格基于文章内容回答，不要编造文章中没有的信息；\n"
    "2. 如果文章中没有相关信息，请明确告知用户；\n"
    "3. 回答简洁准确，适当使用 Markdown 格式提升可读性；\n"
    "4. 用中文回答，无论原文是何种语言。"
)

SELECTION_ASSIST_SYSTEM_PROMPTS = {
    "explain": (
        "你是一个深度阅读助手。请结合文章语境，用中文解释用户选中的文本。"
        "回答要简洁、准确，控制在 150 字以内，不要添加前言。"
    ),
    "summary": (
        "你是一个阅读总结助手。请用中文总结用户选中的文本。"
        "抓住核心含义，控制在 120 字以内，不要添加前言。"
    ),
    "translate": (
        "你是一个专业翻译助手。请将用户选中的文本翻译为自然流畅的中文。"
        "如果文本已经是中文，请改写为更清晰的中文表达。不要添加前言。"
    ),
}

# qa sessions 不缓存（每次问题不同）
qa_sessions: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "content_buffer": [],
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
    article_content = _article_prompt_text(
        await pw_service.scrape_article(browser, payload.url)
    )
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


@router.post("/selection/stream")
async def selection_assist_stream(
    payload: SelectionAssistRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """对用户划选文本进行解释、总结或翻译。"""
    system_prompt = SELECTION_ASSIST_SYSTEM_PROMPTS.get(payload.action)
    if not system_prompt:
        raise HTTPException(status_code=400, detail="不支持的划词操作")

    selected_text = payload.text.strip()
    if not selected_text:
        raise HTTPException(status_code=400, detail="划词内容不能为空")

    user_message = (
        f"文章标题：{payload.article_title or '未知'}\n\n"
        f"文章上下文：\n{payload.article_context or selected_text}\n\n"
        f"用户选中文本：\n{selected_text}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    client = OpenAIStreamClient(current_user["id"])

    async def generate():
        async for chunk in client.stream_chat_completion(messages):
            yield _encode_stream_event(chunk)

    return StreamingResponse(generate(), media_type="text/event-stream")


class PodcastRequest(BaseModel):
    url: str
    article_id: Optional[int] = None
    style: Optional[str] = None


def _podcast_system_prompt(style: Optional[str]) -> str:
    style_text = (style or "").strip()
    if not style_text:
        return PODCAST_SYSTEM_PROMPT

    return (
        f"{PODCAST_SYSTEM_PROMPT}\n"
        "用户自定义风格要求：\n"
        f"{style_text}\n"
        "在不违背上述内容准确性要求的前提下，优先遵循用户自定义风格。"
    )


@router.post("/podcast/stream")
async def podcast_stream(
    payload: PodcastRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """将文章改写为播客口语稿，流式返回纯文本。"""
    style_hash = hashlib.sha256((payload.style or "").strip().encode()).hexdigest()[:8]
    key = "podcast_" + str(_session_key(payload.article_id, payload.url)) + "_" + style_hash
    session = podcast_sessions[key]

    if not session["producer_task"]:
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = _article_prompt_text(
            await pw_service.scrape_article(browser, payload.url)
        )
        messages = [
            {"role": "system", "content": _podcast_system_prompt(payload.style)},
            {"role": "user", "content": article_content},
        ]
        await _make_stream_session(
            podcast_sessions, key, messages, db, current_user["id"],
            persist_article_id=None,
        )

    q, event_generator = _make_event_generator(session)
    session["subscribers"].add(q)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
