"""
Backend — thin API layer.
Receives chat requests from the frontend, forwards to agent, returns response.
This is where you'd add auth, rate-limiting, session management later.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import httpx

app = FastAPI(title="MatAI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENT_URL = os.environ["AGENT_URL"]   # http://agent:8003


class Message(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    role: str | None = None
    history: List[Message] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    payload = {
        "message": req.message,
        "role": req.role,
        "history": [m.model_dump() for m in req.history],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{AGENT_URL}/chat", json=payload)
        r.raise_for_status()
        return r.json()


@app.get("/api/health")
async def health():
    async with httpx.AsyncClient(timeout=5) as client:
        services = {}
        for name, url in [("agent", AGENT_URL)]:
            try:
                r = await client.get(f"{url}/health")
                services[name] = "ok" if r.status_code == 200 else "degraded"
            except Exception:
                services[name] = "unreachable"
    return {"status": "ok", "services": services}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", 8000)))
