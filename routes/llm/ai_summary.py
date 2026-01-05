from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from collections import defaultdict
import asyncio
from services.llm.chat import OpenAIStreamClient
import services.playwright as pw_service
from services.rss.article.state import save_ai_summary, get_ai_summary
from services.database import get_db
from typing import Dict, Any, Set

router = APIRouter(prefix="/llm")

class AISummaryRequest(BaseModel):
    article_id: int
    url: str

# sessions 保存每个 article_id 的流状态
# sessions[article_id] = {
#   "buffer": [chunk,...],            # 已生成的所有 chunk（按顺序）
#   "subscribers": set(Queue,...),    # 当前连接的消费者队列
#   "producer_task": Task | None,     # 用于生成的后台任务
#   "lock": asyncio.Lock(),           # 启动 producer 的互斥锁
# }
sessions: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
    "buffer": [],
    "subscribers": set(),
    "producer_task": None,
    "lock": asyncio.Lock()
})

async def start_producer_if_needed(article_id: int, messages, db):
    """
    确保对该 article_id 只有一个 producer 在跑。
    producer 会对 OpenAIStreamClient 发起流式请求，把 chunk 追加到 buffer 并广播给所有 subscribers。
    生成结束后保存到 DB，并把结束信号发送给 subscribers，然后清理 session（因为结果已保存到 DB）。
    """
    session = sessions[article_id]
    async with session["lock"]:
        if session["producer_task"] and not session["producer_task"].done():
            # 已有 producer 在跑
            return

        async def producer():
            client = OpenAIStreamClient()
            try:
                async for chunk in client.stream_chat_completion(messages):
                    # 保存历史 chunk
                    session["buffer"].append(chunk)
                    # 广播到所有当前 subscribers（非阻塞）
                    to_remove = []
                    for q in session["subscribers"]:
                        try:
                            q.put_nowait(chunk)
                        except asyncio.QueueFull:
                            # 订阅者太慢，忽略或考虑记录（这里直接忽略）
                            pass
                        except Exception:
                            to_remove.append(q)
                    # 移除已失效的 subscriber
                    for q in to_remove:
                        session["subscribers"].discard(q)

                # 生成完成 -> 把整段摘要拼起来并保存到 DB
                full_text = "".join(session["buffer"])
                try:
                    save_ai_summary(db, article_id, full_text)
                except Exception as db_err:
                    # 如果保存失败，保留 buffer 并把错误记录/广播（这里抛出，让外层捕获）
                    raise

            except Exception as e:
                # 若发生异常，向所有订阅者发送 None（作为结束/失败信号），并清理
                for q in list(session["subscribers"]):
                    try:
                        q.put_nowait(None)
                    except Exception:
                        pass
                # 不删除 buffer（方便调试/重试），但移除 producer_task
                session["producer_task"] = None
                # 记录/抛出异常
                raise
            else:
                # 正常结束：通知订阅者结束（None），然后清理 session（因为结果已持久化到 DB）
                for q in list(session["subscribers"]):
                    try:
                        q.put_nowait(None)
                    except Exception:
                        pass
                # 清理：删除 session（释放内存），让后续请求从 DB 读取
                sessions.pop(article_id, None)

        # 启动 producer 后台任务（独立运行）
        session["producer_task"] = asyncio.create_task(producer())

@router.post("/ai_summary/stream")
async def ai_summary_stream(payload: AISummaryRequest, request: Request, db=Depends(get_db)):
    article_id = payload.article_id
    # 先检查 DB 是否已有最终结果（已生成并保存）
    existing = get_ai_summary(db, article_id)
    if existing:
        # 如果已有直接返回完整文本（结束）
        return StreamingResponse(iter([existing]), media_type="text/plain")

    # 确保 sessions 有 entry
    session = sessions[article_id]

    # 如果还没有 producer_task（即没人开始生成），我们需要抓取文章并开始 producer
    if not session["producer_task"]:
        # 抓取文章（可能耗时）
        browser = getattr(request.app.state, "browser", None)
        if not browser:
            raise HTTPException(status_code=503, detail="Browser not available")
        article_content = await pw_service.scrape_article(browser, payload.url)
        messages = [
            {"role": "system", "content": "你是一个专业的文章摘要专家。请对文章进行深度提炼，用中文输出一段紧凑的摘要。要求：1. 直接输出摘要内容，严禁包含任何开场白、分析过程或引导性文字（如“用户想让我...”、“让我分析...”等）；2. 摘要必须极其精炼，篇幅严格控制在一段话内；3. 准确捕捉核心观点与关键事实；4. 适当使用 Markdown 加粗关键词以提升视觉阅读效率。"},
            {"role": "user", "content": article_content}
        ]
        # 启动 producer，它会把生成的 chunk 放到 session["buffer"] 并广播
        await start_producer_if_needed(article_id, messages, db)
    else:
        # producer 已在跑，messages 不再需要重新发送，因为 producer 已经在 model 端
        pass

    # 建立一个 subscriber queue，把它加入 subscribers 集合
    q: asyncio.Queue = asyncio.Queue()
    session["subscribers"].add(q)

    async def event_generator():
        try:
            # 1) 先把已有历史 buffer（已生成的 chunk）重放给新连接
            for chunk in session["buffer"]:
                yield chunk

            # 2) 然后等待 producer 的后续 chunk（producer 会把新 chunk put 到此 queue）
            while True:
                item = await q.get()
                if item is None:
                    # 生产端通知结束
                    break
                yield item
        except asyncio.CancelledError:
            # 客户端断开连接：把该 subscriber 从集合里移除并结束
            session["subscribers"].discard(q)
            raise
        finally:
            # 清理 subscriber（防止泄露）
            session["subscribers"].discard(q)

    return StreamingResponse(event_generator(), media_type="text/plain")
