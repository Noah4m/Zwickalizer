import os
from typing import List, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from llm_agent import MCPEnabledChatAgent


app = FastAPI(title="MatAI Agent", version="0.2.0")
chat_agent = MCPEnabledChatAgent(
    api_key=os.environ["GEMINI_API_KEY"],
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
    mcp_server_root=os.environ.get("MCP_SERVER_ROOT", "/mcp-server"),
)


class ChatRequest(BaseModel):
    message: str
    role: Literal["engineer", "executive"] | None = None
    history: List[dict] = []


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": chat_agent.model,
        "mcp_server_root": chat_agent.mcp_server_root,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
