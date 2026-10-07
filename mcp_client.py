import sys
import asyncio
import json
import httpx

from typing import Optional, Any
from pydantic import AnyUrl, FileUrl
from contextlib import AsyncExitStack
from pathlib import Path
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.types import LoggingMessageNotificationParams, Root, ListRootsResult, ErrorData, Tool, CallToolResult, Prompt, TextResourceContents
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import SamplingFnT
from mcp.shared.context import RequestContext

from core.utils import safe_name


@dataclass
class StdioConfig:
    command: str
    args: list[str]
    env: dict | None = None


@dataclass
class HttpConfig:
    url: str
    headers: dict = field(default_factory=dict)


class MCPClient:
    def __init__(
        self,
        transport_config: StdioConfig | HttpConfig,
        roots: Optional[list[str]] = None,
        sampling_callback: Optional[SamplingFnT] = None
    ):
        self._transport_config = transport_config
        self._session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._sampling_callback = sampling_callback
        self._roots = self.create_roots(roots) if roots else []

    async def connect(self):
        match self._transport_config:
            case StdioConfig(command, args, env):
                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env,
                )
                transport = await self._exit_stack.enter_async_context(
                    stdio_client(server_params)
                )

            case HttpConfig(url, headers):
                http = await self._exit_stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=headers, timeout=httpx.Timeout(30, read=300))
                )
                transport = await self._exit_stack.enter_async_context(
                    streamable_http_client(url, http_client=http)
                )
        _stdio, _write, *_ = transport
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
    async def logging_callback(params: LoggingMessageNotificationParams):
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
    def create_roots(root_paths: list[str]) -> list[Root]:
        """Convert path strings to Root objects."""
        roots = []
        for path in root_paths:
            p = Path(path).resolve()
            file_url = FileUrl(f"file://{p}")
            roots.append(Root(uri=file_url, name=p.name or "Root"))
        return roots

    async def handle_list_roots(
        self, ctx: RequestContext["ClientSession", None]
    ) -> ListRootsResult | ErrorData:
        """Callback for when server requests roots."""
        return ListRootsResult(roots=self._roots)

    async def list_tools(self) -> list[Tool]:
        _list_tools = await self.session().list_tools()
        return _list_tools.tools

    async def call_tool(
        self, tool_name: str, tool_input: dict
    ) -> CallToolResult | None:
        return await self.session().call_tool(tool_name, tool_input, progress_callback=self.print_progress_callback)

    async def list_prompts(self) -> list[Prompt]:
        _list_prompts = await self.session().list_prompts()
        return _list_prompts.prompts

    async def get_prompt(self, prompt_name, args: dict[str, str]):
        prompt = await self.session().get_prompt(prompt_name, args)
        return prompt.messages

    async def read_resource(self, uri: str) -> Any:
        results = await self.session().read_resource(AnyUrl(uri))
        resource = results.contents[0]
        if isinstance(resource, TextResourceContents):
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


class MCPClientHub:
    def __init__(self, clients: dict[str, MCPClient]):
        self._clients = clients
        self.tool_owners: dict[str, MCPClient] = {}

    async def start(self):
        for client in self._clients.values():
            await client.connect()

    async def close(self):
        for client in reversed(self._clients.values()):
            await client.cleanup()

    async def read_resource(self, uri, client_id: Optional[MCPClient] = None):
        if not client_id:
            # TODO: Solve the case when the client_id is not specified
            raise NotImplementedError(
                f"Please specify client id in this list: {self._clients.keys()}")

        return self._clients.get(client_id).read_resource(uri)

    async def list_prompts(self):
        prompts = []
        for server, client in self._clients.items():
            server_prompts = await client.list_prompts()
            prompts.extend(server_prompts)
        return prompts

    async def list_tools(self):
        tools = {}
        for server, client in self._clients.items():
            server_tools = await client.list_tools()
            for t in server_tools:
                tools[safe_name(server, t.name)] = (client, t)
        return tools

    def _resolve(self, name: str) -> tuple[MCPClient, str]:
        server, original = name.split("__", 1)
        if server not in self._clients.keys():
            raise KeyError(f"Unknown server: {server}")
        return self._clients[server], original

    async def call_tool(self, name: str, args: dict):
        client, tool = self._resolve(name)
        return await client.call_tool(tool, args)

    async def get_prompt(self, name: str, args: dict | None = None):
        client, prompt = self._resolve(name)
        return await client.get_prompt(prompt, args or {})

    async def check_tool_available(self, name: str) -> bool:
        server, sep, tool = name.partition("__")
        if not sep or server not in self._clients:
            return False                              # malformed name or unknown server

        client = self._clients[server]
        try:
            tools = (await client.session().list_tools()).tools
        except Exception:
            return False                              # server down / session not connected
        return any(t.name == tool for t in tools)


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
