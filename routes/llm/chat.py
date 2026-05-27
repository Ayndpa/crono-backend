import os
import base64
import json
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from models.llm.request import ChatRequest
from services.llm.chat import OpenAIStreamClient
from services.llm.config import get_llm_config_service
from services.database import get_db
from services.auth import get_current_user


def _encode_stream_event(event: dict[str, str]) -> bytes:
  payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
  encoded = base64.b64encode(payload).decode("utf-8")
  return f"data: {encoded}\n\n".encode("utf-8")

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
      yield _encode_stream_event(chunk)

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