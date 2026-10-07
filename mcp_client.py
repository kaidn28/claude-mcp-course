import sys
import asyncio
import json
from typing import Optional, Any
from pydantic import AnyUrl
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.session import SamplingFnT
from mcp.shared.context import RequestContext
from pathlib import Path
from pydantic import FileUrl


class MCPClient:
    def __init__(
        self,
        command: str,
        args: list[str],
        env: Optional[dict] = None,
        roots: Optional[list[str]] = None,
        sampling_callback: Optional[SamplingFnT] = None
    ):
        self._command = command
        self._args = args
        self._env = env
        self._session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._sampling_callback = sampling_callback
        self._roots = self.create_roots(roots) if roots else []

    async def connect(self):
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        _stdio, _write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(_stdio, _write, sampling_callback=self._sampling_callback,
                          logging_callback=self.logging_callback, list_roots_callback=self.handle_list_roots)
        )
        await self._session.initialize()

    def session(self) -> ClientSession:
        if self._session is None:
            raise ConnectionError(
                "Client session not initialized or cache not populated. Call connect_to_server first."
            )
        return self._session

    @staticmethod
    async def logging_callback(params: types.LoggingMessageNotificationParams):
        print(params.data)

    @staticmethod
    async def print_progress_callback(
        progress: float, total: float | None, message: str | None
    ):
        if total is not None:
            percentage = (progress / total) * 100
            print(f"Progress: {progress}/{total} ({percentage:.1f}%)")
        else:
            print(f"Progress: {progress}")

    @staticmethod
    def create_roots(root_paths: list[str]) -> list[types.Root]:
        """Convert path strings to Root objects."""
        roots = []
        for path in root_paths:
            p = Path(path).resolve()
            file_url = FileUrl(f"file://{p}")
            roots.append(types.Root(uri=file_url, name=p.name or "Root"))
        return roots

    async def handle_list_roots(
        self, ctx: RequestContext["ClientSession", None]
    ) -> types.ListRootsResult | types.ErrorData:
        """Callback for when server requests roots."""
        return types.ListRootsResult(roots=self._roots)

    async def list_tools(self) -> list[types.Tool]:
        _list_tools = await self.session().list_tools()
        return _list_tools.tools

    async def call_tool(
        self, tool_name: str, tool_input: dict
    ) -> types.CallToolResult | None:
        return await self.session().call_tool(tool_name, tool_input, progress_callback=self.print_progress_callback)

    async def list_prompts(self) -> list[types.Prompt]:
        _list_prompts = await self.session().list_prompts()
        return _list_prompts.prompts

    async def get_prompt(self, prompt_name, args: dict[str, str]):
        prompt = await self.session().get_prompt(prompt_name, args)
        return prompt.messages

    async def read_resource(self, uri: str) -> Any:
        results = await self.session().read_resource(AnyUrl(uri))
        resource = results.contents[0]
        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                return json.loads(resource.text)
            elif resource.mimeType == "text/plain":
                return resource.text
        return ValueError(f"{uri} is not a text file")

    async def cleanup(self):
        await self._exit_stack.aclose()
        self._session = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# For testing
async def main():
    async with MCPClient(
        # If using Python without UV, update command to 'python' and remove "run" from args.
        command="uv",
        args=["run", "mcp_server.py"],
    ) as _client:
        print(await _client.list_tools())


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
