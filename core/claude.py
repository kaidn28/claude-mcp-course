import asyncio
from anthropic import Anthropic
from anthropic.types import Message
from mcp.shared.context import RequestContext
from mcp.types import CreateMessageRequestParams, CreateMessageResult, TextContent


class Claude:
    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None):
        self.client = Anthropic(base_url=base_url, api_key=api_key)
        self.model = model

    def add_user_message(self, messages: list, message):
        user_message = {
            "role": "user",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(user_message)

    def add_assistant_message(self, messages: list, message):
        assistant_message = {
            "role": "assistant",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(assistant_message)

    def text_from_message(self, message: Message):
        return "\n".join(
            [block.text for block in message.content if block.type == "text"]
        )

    def chat(
        self,
        messages,
        system=None,
        temperature=1.0,
        stop_sequences=[],
        tools=None,
        thinking=False,
        thinking_budget=1024,
    ) -> Message:
        params = {
            "model": self.model,
            "max_tokens": 8000,
            "messages": messages,
            "temperature": temperature,
            "stop_sequences": stop_sequences,
        }

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        message = self.client.messages.create(**params)
        return message
        
    async def sampling_callback(
        self, ctx: RequestContext, params: CreateMessageRequestParams
    ):
        # print(params.messages)
        messages = [{"role": m.role, "content": m.content.text} for m in params.messages]
        # Call Claude using the Anthropic SDK
        
        callback_result = await asyncio.to_thread(self.chat, messages)
        
        text = "".join(b.text for b in callback_result.content if b.type == "text")
        return CreateMessageResult(
            role="assistant",
            model=self.model,
            content=TextContent(type="text", text=text),
        )