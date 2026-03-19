"""
Minimal chat agent using Google Gemini.

Receives a user message plus chat history from the backend,
sends the conversation to Gemini, and returns the model's reply.
"""
import os
from typing import List

from fastapi import FastAPI
from google import genai
from google.genai import types
from pydantic import BaseModel


app = FastAPI(title="MatAI Agent", version="0.1.0")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = "gemini-2.5-flash-lite"

gemini = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """You are MatAI, a concise and practical assistant.
Give direct answers, keep them clear, and avoid unnecessary filler.
"""


class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


@app.post("/chat")
async def chat(req: ChatRequest):
    contents: list[types.Content] = []

    for item in req.history:
        role = "model" if item["role"] == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=item["content"])],
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=req.message)],
        )
    )

    response = gemini.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
        ),
    )

    answer_parts = response.candidates[0].content.parts
    answer = " ".join(part.text for part in answer_parts if part.text).strip()

    return {"answer": answer}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
