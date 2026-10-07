from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base
from mcp.types import SamplingMessage, TextContent
from pydantic import Field
import json
import os

mcp = FastMCP("StreamableMCP", log_level="ERROR", host="127.0.0.1", port=8000)


@mcp.tool(name="search_internet", description="tool to search for random unhelpful information on the internet")
async def search_internet(ctx: Context):
    await ctx.info("Searching internet...")
    await ctx.report_progress(0, 100)
    with open("data/synthetic_search_results.json", 'r') as f:
        search_result = json.loads(f.read())

    await ctx.info("Summarizing results...")
    await ctx.report_progress(80, 100)
    prompt = f"""
    Please summarize the following text:
    {search_result}
    """

    summary = await ctx.session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=prompt
                )
            )
        ],
        max_tokens=4000,
        system_prompt="You are a helpful research assistant",
    )

    ctx.info("Returning final result...")
    await ctx.report_progress(100, 100)
    if summary.content.type == "text":
        return summary.content.text
    else:
        raise ValueError("Sampling failed")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
