from mcp.server.fastmcp import FastMCP
from pydantic import Field

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

# TODO: Write a resource to return all doc id's
# TODO: Write a resource to return the contents of a particular doc
# TODO: Write a prompt to rewrite a doc in markdown format
# TODO: Write a prompt to summarize a doc


if __name__ == "__main__":
    mcp.run(transport="stdio")
