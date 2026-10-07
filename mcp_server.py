from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base
from mcp.types import SamplingMessage, TextContent
from pydantic import Field
import json
import os
from pathlib import Path

from core.utils import file_url_to_path

mcp = FastMCP("DocumentMCP", log_level="ERROR")


docs = {
    "deposition.md": "This deposition covers the testimony of Angela Smith, P.E.",
    "report.pdf": "The report details the state of a 20m condenser tower.",
    "financials.docx": "These financials outline the project's budget and expenditures.",
    "outlook.pdf": "This document presents the projected future performance of the system.",
    "plan.md": "The plan outlines the steps for the project's implementation.",
    "spec.txt": "These specifications define the technical requirements for the equipment.",
}


async def is_path_allowed(requested_path: Path, ctx: Context) -> bool:
    roots_result = await ctx.session.list_roots()
    client_roots = roots_result.roots

    if not requested_path.exists():
        return False

    if requested_path.is_file():
        requested_path = requested_path.parent

    for root in client_roots:
        root_path = file_url_to_path(root.uri)
        try:
            requested_path.relative_to(root_path)
            return True
        except ValueError:
            continue

    return False


@mcp.tool(name="read_doc", description="tool to read document")
def read_doc(doc_id: str = Field(description="id of the document")):
    if doc_id not in docs.keys():
        raise ValueError("file not found")

    return docs.get(doc_id)


@mcp.tool(name="edit_doc", description="tool to update document")
def update_doc(
        doc_id: str = Field(description="id of the document"),
        old_string: str = Field(description="old string to be replaced"),
        new_string: str = Field(description="new string to replace")):
    if doc_id not in docs.keys():
        raise ValueError("file not found")

    docs[doc_id] = docs.get(doc_id).replace(old_string, new_string)
    return docs[doc_id]


@mcp.tool(name="process_pic", description="a tool which helps you process a pic in the local file system, you don't need to know about which is done in the process, just call this when you are requested to process a picture")
async def process_pic(pic_path: str = Field(description="The absolute path to the picture"), *, ctx: Context):
    await ctx.info(f"Processing {pic_path}")
    pic_path = Path(pic_path).resolve()
    if not await is_path_allowed(pic_path, ctx):
        raise ValueError(f"Access to path is not allowed: {pic_path}")
    return f"Picture {os.path.basename(pic_path)} processed successfully"


@mcp.tool(name="read_dir", description="tool to read files, folders in a specified directory")
@mcp.tool()
async def read_dir(
    path: str = Field(description="Path to a directory to read"),
    *,
    ctx: Context,
):
    """Read directory contents. Path must be within one of the client's roots."""

    await ctx.info(f"Reading directory: {path}")
    requested_path = Path(path).resolve()

    if not await is_path_allowed(requested_path, ctx):
        raise ValueError("Error: can only read directories within a root")

    return [entry.name for entry in requested_path.iterdir()]


@mcp.tool(name="list_roots", description="return a list of roots: files/folders that user has permission to read")
async def list_roots(ctx: Context):
    await ctx.info("Reading allowed folders")
    roots_result = await ctx.session.list_roots()
    return [file_url_to_path(root.uri) for root in roots_result.roots]


@mcp.resource(uri="docs://documents", mime_type="application/json")
def get_doc_list():
    return list(docs.keys())


@mcp.resource(uri="docs://documents/{doc_id}", mime_type="text/plain")
def fetch_doc(doc_id):
    if doc_id not in docs.keys():
        return ValueError(f"doc_id {doc_id} not found")

    return docs.get(doc_id)


@mcp.prompt(name="format", description="rewrite a doc in md format")
def format_document(doc_id: str = Field(description="document id")) -> list[base.Message]:
    PROMPT = f"""
    Your goal is to reformat a document to be written with markdown syntax.
    The id of the document you need to reformat is:
    <document_id>
    {doc_id}
    </document_id>

    Add in headers, bullet points, tables, etc as necessary. Feel free to add in structure.
    Use the 'edit_document' tool to edit the document. After the document has been reformatted...
    """

    return [base.UserMessage(PROMPT)]


@mcp.prompt(name="summarize", description="summarize a doc")
def summarize_document(doc_id: str = Field(description="document id")) -> list[base.Message]:
    PROMPT = f"""
    Summarize this doc:
    <document_id>
    {doc_id}
    </document_id>
    """

    return [base.UserMessage(PROMPT)]


if __name__ == "__main__":
    mcp.run(transport="stdio")
