import asyncio
from openai import AsyncOpenAI

from services.database import get_db
from services.llm.config import get_llm_config_service
from services.config import get_config

class OpenAIStreamClient:
    """
    封装OpenAI异步流式客户端。
    """
    def __init__(self):
        """
        初始化AsyncOpenAI客户端。
        从数据库中读取配置并初始化。
        """
        try:
            with next(get_db()) as db:
                config_entry = get_config(db, "llm_config_id")
                llm_config_id = config_entry.value if config_entry else None

                if not llm_config_id:
                    raise ValueError("LLM configuration ID not set. Please set LLM_CONFIG_ID environment variable.")

                config = get_llm_config_service(db, int(llm_config_id))
                if not config:
                    raise ValueError(f"LLM configuration with ID {llm_config_id} not found in the database.")

                self.model = config.model  # 从配置中读取模型名称
                self.client = AsyncOpenAI(
                    base_url=str(config.base_url),
                    api_key=config.api_key
                )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")

    async def stream_chat_completion(self, messages: list[dict], model: str = None):
        """
        发起流式聊天补全请求并逐块返回响应内容。
        此方法将直接返回模型生成的文本内容。

        Args:
            messages (list[dict]): 聊天消息列表。
            model (str, optional): 覆盖默认的模型名称。
        """
        try:
            stream = await self.client.chat.completions.create(
                model=model or self.model,  # 使用传入的模型名称或默认配置
                messages=messages,
                stream=True,
                extra_body={"reasoning_split": True}
            )

            async for chunk in stream:
                # 检查 choices 是否为空（有些 chunk 可能只包含 usage 或其他信息）
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                
                # 处理思考内容
                # SiliconFlow/DeepSeek 使用 reasoning_content (str)
                # MiniMax 使用 reasoning_details (list[dict])
                reasoning = None
                if hasattr(delta, 'reasoning_details') and delta.reasoning_details:
                    # 尝试解析 MiniMax 的列表格式
                    parts = []
                    for part in delta.reasoning_details:
                        if isinstance(part, dict) and "text" in part:
                            parts.append(part["text"])
                        elif hasattr(part, "text"):
                            parts.append(part.text)
                    reasoning = "".join(parts)
                else:
                    reasoning = getattr(delta, 'reasoning_content', None)

                if reasoning:
                    yield str(reasoning)
                
                # 检查是否存在内容块
                if delta.content:
                    # 直接返回内容字符串
                    yield delta.content
                
        except Exception as e:
            # 打印错误信息，并重新抛出异常，以便上层处理
            print(f"\n流式输出过程中发生错误: {e}")
            raise

    async def chat_completion(self, messages: list[dict]) -> str:
        """
        发起非流式聊天补全请求并返回完整响应内容。

        Args:
            messages (list[dict]): 聊天消息列表。

        Returns:
            str: 模型生成的完整文本内容。
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,  # 使用从配置中读取的模型名称
                messages=messages,
                stream=False,
                extra_body={"reasoning_split": True}
            )
            # 提取并返回完整的响应内容
            # 如果存在思考内容，有些 API 可能会把它们放在不同的字段，这里暂时只返回 content
            return response.choices[0].message.content
        except Exception as e:
            # 打印错误信息，并重新抛出异常，以便上层处理
            print(f"\n非流式输出过程中发生错误: {e}")
            raise