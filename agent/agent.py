import json
import os
import traceback
from typing import List, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from llm_agent import MCPEnabledChatAgent
from mcp_client import MCPToolbox


load_dotenv()


def _openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_API_KEY")
    if api_key:
        return api_key
    raise RuntimeError("OPENAI_API_KEY is not set.")


app = FastAPI(title="MatAI Agent", version="0.3.0")
chat_agent = MCPEnabledChatAgent(
    api_key=_openai_api_key(),
    model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
    mcp_server_root=os.environ.get("MCP_SERVER_ROOT", "/mcp-server"),
)


class ChatRequest(BaseModel):
    message: str
    role: Literal["engineer", "executive"] | None = None
    history: List[dict] = Field(default_factory=list)


def inspect_mcp() -> dict:
    with MCPToolbox(chat_agent.mcp_server_root) as toolbox:
        tool_names = sorted(toolbox.tools)
        payload: dict = {
            "status": "ok",
            "servers": sorted(toolbox.sessions),
            "tools": tool_names,
        }

        if "db_list_collections" not in toolbox.tools:
            payload["db"] = {
                "status": "skipped",
                "reason": "db_list_collections tool is not registered.",
            }
            return payload

        raw_collections = toolbox.call("db_list_collections", {})
        collections = json.loads(raw_collections)
        payload["db"] = {
            "status": "ok",
            "collections_count": len(collections) if isinstance(collections, list) else None,
            "sample_collections": collections[:5] if isinstance(collections, list) else [],
        }
        return payload


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        answer = chat_agent.answer(
            message=req.message,
            role=req.role,
            history=req.history,
        )
        return {"answer": answer}
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health(response: Response):
    payload = {
        "status": "ok",
        "model": chat_agent.model,
        "mcp_server_root": chat_agent.mcp_server_root,
    }

    try:
        payload["mcp"] = inspect_mcp()
    except Exception as exc:
        response.status_code = 503
        payload["status"] = "degraded"
        payload["mcp"] = {"status": "error", "error": str(exc)}

    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
