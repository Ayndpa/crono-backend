import os
import base64
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from models.llm.request import ChatRequest
from services.llm.chat import OpenAIStreamClient
from services.llm.config import get_llm_config_service
from services.database import get_db
from services.auth import get_current_user

# FastAPI 路由设置
router = APIRouter(
  prefix="/llm",
  tags=["LLM Client"],
)

async def generate_stream(client: OpenAIStreamClient, request: ChatRequest) -> AsyncGenerator[bytes, None]:
  """
  异步生成器，用于从 OpenAIStreamClient 获取数据，并封装成 SSE 格式返回。
  使用 Base64 编码来处理可能包含特殊字符的 chunk，以确保 SSE 格式的完整性。
  """
  try:
    async for chunk in client.stream_chat_completion(
      request.messages,
      request.model
    ):
      # 将 chunk 编码为 bytes
      chunk_bytes = chunk.encode("utf-8")
      # 使用 Base64 编码来处理 chunk 中的所有特殊字符
      encoded_chunk = base64.b64encode(chunk_bytes).decode("utf-8")
      # 将编码后的 chunk 封装成 SSE 格式
      sse_chunk = f"data: {encoded_chunk}\n\n"
      # 编码为 bytes 并返回
      yield sse_chunk.encode("utf-8")

  except HTTPException:
    raise
  except Exception as e:
    print(f"生成流时发生未知错误: {e}")
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"服务器内部发生未知错误: {e}"
    )

@router.post("/stream_chat", response_model=None)
async def stream_chat(
  request: ChatRequest,
  current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
  """
  接受一个聊天请求，并以流式方式返回 AI 响应。
  """
  try:
    client = OpenAIStreamClient(current_user["id"])
  except RuntimeError as e:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"无法初始化 LLM: {e}"
    )
  
  return StreamingResponse(
    generate_stream(client, request),
    media_type="text/event-stream"
  )