from typing import List, Tuple, Any
from pydantic import AnyUrl
from mcp.types import Prompt, PromptMessage, Tool
from anthropic.types import MessageParam

from core.claude import Claude
from core.tools import ToolManager
from mcp_client import MCPClientHub


class CliChat:
    def __init__(
        self,
        client_hub: MCPClientHub,
        claude_service: Claude,
    ):
        self._client_hub = client_hub
        self._claude_service = claude_service
        self.messages: list[MessageParam] = []

    async def run(
        self,
        query: str,
    ) -> str:
        final_text_response = ""

        await self._process_query(query)

        while True:
            response = self._claude_service.chat(
                messages=self.messages,
                tools=await ToolManager.get_all_tools(self._client_hub),
            )

            self._claude_service.add_assistant_message(self.messages, response)

            if response.stop_reason == "tool_use":
                print(self._claude_service.text_from_message(response))
                tool_result_parts = await ToolManager.execute_tool_requests(
                    self._client_hub, response
                )

                self._claude_service.add_user_message(
                    self.messages, tool_result_parts
                )
            else:
                final_text_response = self._claude_service.text_from_message(
                    response
                )
                break

        return final_text_response

    async def list_documents(self):
        doc_client = self._client_hub._clients.get("doc-client")
        return await doc_client.read_resource(f"docs://documents")

    async def read_document(self, doc_id: str):
        doc_client = self._client_hub._clients.get("doc-client")
        return await doc_client.read_resource(f"docs://documents/{doc_id}")

    async def list_prompts(self) -> list[Prompt]:
        return await self._client_hub.list_prompts()

    async def get_prompt(
        self, command: str, args: dict
    ) -> list[PromptMessage]:
        return await self._client_hub.get_prompt(command, args)

    async def _extract_resources(self, query: str) -> str:
        mentions = [word[1:] for word in query.split() if word.startswith("@")]

        doc_ids = await self.list_documents()
        mentioned_docs: list[Tuple[str, str]] = []

        for doc_id in doc_ids:
            if doc_id in mentions:
                content = await self.read_document(doc_id)
                mentioned_docs.append((doc_id, content))

        return "".join(
            f'\n<document id="{doc_id}">\n{content}\n</document>\n'
            for doc_id, content in mentioned_docs
        )

    async def _process_command(self, query: str) -> bool:
        if not query.startswith("/"):
            return False

        words = query.split()
        command = words[0].replace("/", "")

        messages = await self.get_prompt(
            command, {"doc_id": words[1]}
        )

        self.messages += convert_prompt_messages_to_message_params(messages)
        return True

    async def _process_query(self, query: str):
        if await self._process_command(query):
            return

        added_resources = await self._extract_resources(query)

        prompt = f"""
        The user has a question:
        <query>
        {query}
        </query>

        The following context may be useful in answering their question:
        <context>
        {added_resources}
        </context>

        Note the user's query might contain references to documents like "@report.docx". The "@" is only
        included as a way of mentioning the doc. The actual name of the document would be "report.docx".
        If the document content is included in this prompt, you don't need to use an additional tool to read the document.
        Answer the user's question directly and concisely. Start with the exact information they need. 
        Don't refer to or mention the provided context in any way - just use it to inform your answer.
        """

        self.messages.append({"role": "user", "content": prompt})


def convert_prompt_message_to_message_param(
    prompt_message: "PromptMessage",
) -> MessageParam:
    role = "user" if prompt_message.role == "user" else "assistant"

    content = prompt_message.content

    # Check if content is a dict-like object with a "type" field
    if isinstance(content, dict) or hasattr(content, "__dict__"):
        content_type = (
            content.get("type", None)
            if isinstance(content, dict)
            else getattr(content, "type", None)
        )
        if content_type == "text":
            content_text = (
                content.get("text", "")
                if isinstance(content, dict)
                else getattr(content, "text", "")
            )
            return {"role": role, "content": content_text}

    if isinstance(content, list):
        text_blocks = []
        for item in content:
            # Check if item is a dict-like object with a "type" field
            if isinstance(item, dict) or hasattr(item, "__dict__"):
                item_type = (
                    item.get("type", None)
                    if isinstance(item, dict)
                    else getattr(item, "type", None)
                )
                if item_type == "text":
                    item_text = (
                        item.get("text", "")
                        if isinstance(item, dict)
                        else getattr(item, "text", "")
                    )
                    text_blocks.append({"type": "text", "text": item_text})

        if text_blocks:
            return {"role": role, "content": text_blocks}

    return {"role": role, "content": ""}


def convert_prompt_messages_to_message_params(
    prompt_messages: List[PromptMessage],
) -> List[MessageParam]:
    return [
        convert_prompt_message_to_message_param(msg) for msg in prompt_messages
    ]
