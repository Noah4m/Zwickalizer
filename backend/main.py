"""
Backend — thin API layer.
Receives chat requests from the frontend, forwards to agent, returns response.
This is where you'd add auth, rate-limiting, session management later.
"""
import os
from fastapi import FastAPI
from fastapi import HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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
    history: List[Message] = Field(default_factory=list)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    payload = {
        "message": req.message,
        "role": req.role,
        "history": [m.model_dump() for m in req.history],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{AGENT_URL}/chat", json=payload)
        if r.is_error:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()


@app.get("/api/health")
async def health(response: Response):
    async with httpx.AsyncClient(timeout=5) as client:
        overall_status = "ok"
        services = {}
        for name, url in [("agent", AGENT_URL)]:
            try:
                r = await client.get(f"{url}/health")
                details = r.json()
                service_status = details.get("status", "ok") if r.status_code == 200 else "degraded"
                services[name] = {"status": service_status, "details": details}
                if service_status != "ok":
                    overall_status = "degraded"
            except Exception as exc:
                services[name] = {"status": "unreachable", "error": str(exc)}
                overall_status = "degraded"

    if overall_status != "ok":
        response.status_code = 503

    return {"status": overall_status, "services": services}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", 8000)))
