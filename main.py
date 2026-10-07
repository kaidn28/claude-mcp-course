import asyncio
import sys
import os
from dotenv import load_dotenv
from contextlib import AsyncExitStack

from core.claude import Claude
from core.cli_chat import CliChat
from core.cli import CliApp
from mcp_client import MCPClient, MCPClientHub, StdioConfig, HttpConfig

load_dotenv()

# Anthropic Config
claude_model = os.getenv("CLAUDE_MODEL", "")
anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL", None)
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")


assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, (
    "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"
)


async def main():
    claude_service = Claude(model=claude_model, base_url=anthropic_base_url)

    clients = {}

    doc_client_config = StdioConfig("python", ["mcp_server.py"])
    http_client_config = HttpConfig("http://127.0.0.1:8000/mcp", {})

    client_configs = {
        "doc-client": doc_client_config,
        "http-client": http_client_config
    }

    for client_id, cfg in client_configs.items():
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                MCPClient(
                    transport_config=cfg,
                    sampling_callback=claude_service.sampling_callback,
                    roots=['./data/'])
            )
            clients[client_id] = client
    client_hub = MCPClientHub(clients)
    await client_hub.start()

    chat = CliChat(
        client_hub=client_hub,
        claude_service=claude_service,
    )

    cli = CliApp(chat)
    await cli.initialize()
    await cli.run()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
