import json
import hashlib
import base64
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.llm.chat import OpenAIStreamClient
import services.playwright as pw_service
from services.database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/llm")


class EntityRequest(BaseModel):
    url: str
    article_id: Optional[int] = None


class EntityExplainRequest(BaseModel):
    entity: str
    entity_type: str
    article_title: str
    article_context: str          # 实体周围的文本片段（前后各 300 字）
    history_titles: list[str]     # 用户最近已读文章标题（最多 10 条）


ENTITY_SYSTEM_PROMPT = """\
你是一个语义实体识别专家。请从以下文章中识别关键实体，包括：
- tech: 技术名词、框架、协议、算法、工具
- person: 人名
- org: 机构、公司、组织
- concept: 生僻概念、专业术语、行业黑话

输出要求：
1. 严格输出 JSON 数组，不要有任何其他文字
2. 每个元素格式：{"text": "实体原文", "type": "tech|person|org|concept"}
3. 只选取对理解文章有价值的词，不超过 25 个
4. 实体必须是文章中出现的原文片段（区分大小写）
5. 避免过于常见的词（如 "the", "API", "HTTP" 等基础词汇）

示例输出：
[{"text": "Transformer", "type": "tech"}, {"text": "Sam Altman", "type": "person"}]
"""

ENTITY_EXPLAIN_SYSTEM_PROMPT = """\
你是一个深度阅读助手，专门基于文章语境给出精准解释。
你的解释必须：
1. 结合当前文章的具体语境，而非通用字典定义
2. 说明该实体在本文中扮演的角色或意义
3. 如果用户有相关阅读历史，指出与历史文章的关联
4. 用中文回答，简洁有力，控制在 150 字以内
5. 直接输出解释内容，不要有任何前言
"""


def _encode_stream_event(event: dict[str, str]) -> bytes:
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
    encoded = base64.b64encode(payload).decode("utf-8")
    return f"data: {encoded}\n\n".encode("utf-8")


@router.post("/entities")
async def extract_entities(
    payload: EntityRequest,
    request: Request,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    提取文章中的语义实体，返回 JSON 数组。
    """
    browser = getattr(request.app.state, "browser", None)
    if not browser:
        raise HTTPException(status_code=503, detail="Browser not available")

    article_content = await pw_service.scrape_article(browser, payload.url)
    if article_content.get("captcha"):
        raise HTTPException(status_code=422, detail="无法抓取文章内容（验证码拦截）")

    # 截取前 4000 字符，避免 token 过多
    content_text = article_content.get("html", "")[:4000]

    try:
        client = OpenAIStreamClient(current_user["id"])
        result = await client.chat_completion([
            {"role": "system", "content": ENTITY_SYSTEM_PROMPT},
            {"role": "user", "content": content_text},
        ])
        # 尝试解析 JSON
        entities = json.loads(result.strip())
        if not isinstance(entities, list):
            entities = []
    except json.JSONDecodeError:
        entities = []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"实体提取失败: {e}")

    return {"entities": entities}


@router.post("/entity_explain/stream")
async def entity_explain_stream(
    payload: EntityExplainRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    基于文章语境，流式返回实体的深度解释。
    """
    history_str = ""
    if payload.history_titles:
        titles = "\n".join(f"- {t}" for t in payload.history_titles[:10])
        history_str = f"\n\n用户最近阅读的相关文章：\n{titles}"

    user_message = (
        f"当前文章：《{payload.article_title}》\n\n"
        f"实体：「{payload.entity}」（类型：{payload.entity_type}）\n\n"
        f"上下文片段：\n{payload.article_context}"
        f"{history_str}\n\n"
        f"请解释「{payload.entity}」在本文中的含义和作用。"
    )

    messages = [
        {"role": "system", "content": ENTITY_EXPLAIN_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        client = OpenAIStreamClient(current_user["id"])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    import base64

    async def generate():
        async for chunk in client.stream_chat_completion(messages):
            yield _encode_stream_event(chunk)

    return StreamingResponse(generate(), media_type="text/event-stream")
