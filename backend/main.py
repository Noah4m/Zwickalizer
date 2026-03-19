"""
Backend — thin API layer.
Receives chat requests from the frontend, forwards to agent, returns response.
This is where you'd add auth, rate-limiting, session management later.
"""
import logging
import os
from fastapi import FastAPI
from fastapi import HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
import httpx

logger = logging.getLogger("uvicorn.error")

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
    logger.info(
        "Backend received chat request role=%s message=%s",
        req.role,
        req.message[:200],
    )
    payload = {
        "message": req.message,
        "role": req.role,
        "history": [m.model_dump() for m in req.history],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(f"{AGENT_URL}/chat", json=payload)
        except Exception:
            logger.exception("Backend failed to reach agent at %s/chat", AGENT_URL)
            raise
        if r.is_error:
            logger.error("Agent returned HTTP %s: %s", r.status_code, r.text[:500])
            raise HTTPException(status_code=r.status_code, detail=r.text)
        logger.info("Backend returning chat response with HTTP %s", r.status_code)
        return r.json()


@app.get("/api/health")
async def health(response: Response):
    logger.info("Backend health check requested")
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


@app.get("/api/outliers")
async def outliers(limit: int = 6):
    logger.info("Backend received outlier review request limit=%s", limit)
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.get(f"{AGENT_URL}/outliers", params={"limit": limit})
        except Exception:
            logger.exception("Backend failed to reach agent at %s/outliers", AGENT_URL)
            raise
        if r.is_error:
            logger.error("Agent returned HTTP %s for outliers: %s", r.status_code, r.text[:500])
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", 8000)))
