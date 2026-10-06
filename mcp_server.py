from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base
from mcp.types import SamplingMessage, TextContent
from pydantic import Field
import json

mcp = FastMCP("DocumentMCP", log_level="ERROR")


docs = {
    "deposition.md": "This deposition covers the testimony of Angela Smith, P.E.",
    "report.pdf": "The report details the state of a 20m condenser tower.",
    "financials.docx": "These financials outline the project's budget and expenditures.",
    "outlook.pdf": "This document presents the projected future performance of the system.",
    "plan.md": "The plan outlines the steps for the project's implementation.",
    "spec.txt": "These specifications define the technical requirements for the equipment.",
}

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

@mcp.tool(name="search_internet", description="tool to search for random unhelpful information on the internet")
async def search_internet(ctx: Context):
    with open("data/synthetic_search_results.json", 'r') as f:
        search_result = json.loads(f.read())

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
    if summary.content.type == "text":
        return summary.content.text
    else:
        raise ValueError("Sampling failed")

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
