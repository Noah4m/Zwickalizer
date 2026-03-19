"""
Minimal chat agent using Google Gemini.

Receives a user message plus chat history from the backend,
sends the conversation to Gemini, and returns the model's reply.
"""
import json
import os
import csv
from typing import List
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from bson import json_util
from google import genai
from google.genai import types
from pymongo import MongoClient
from pydantic import BaseModel


app = FastAPI(title="MatAI Agent", version="0.1.0")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://host.docker.internal:27017")
MONGO_DB = os.environ.get("MONGO_DB", "test")
MODEL = "gemini-2.5-flash-lite"
LOG_FILE = Path(os.environ.get("TOOL_LOG_FILE", "log.csv"))

gemini = genai.Client(api_key=GEMINI_API_KEY)
mongo = MongoClient(MONGO_URI)
db = mongo[MONGO_DB]

SYSTEM_PROMPT = """You are MatAI, a concise and practical assistant.
Give direct answers, keep them clear, and avoid unnecessary filler.
If the user asks something that requires database data, use the MongoDB tool.
Do not invent database results.
When using the MongoDB tool, always provide all arguments.
Use "{}" when no filter is needed and 5 when no limit is requested.
"""


class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]



def debug_db_overview():
    try:
        return {
            "db_name": MONGO_DB,
            "collections": db.list_collection_names(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def log_event(event_type: str, details: dict, status: str, message: str) -> None:
    file_exists = LOG_FILE.exists()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["timestamp_utc", "event_type", "details", "status", "message"])

        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                event_type,
                json.dumps(details, ensure_ascii=True),
                status,
                message[:1000],
            ]
        )


def log_tool_call(tool_name: str, arguments: dict, result_preview: str, status: str) -> None:
    log_event(tool_name, arguments, status, result_preview)


def query_mongodb(collection: str, filter_json: str, limit: int) -> str:
    """Query MongoDB and return JSON documents."""
    arguments = {
        "collection": collection,
        "filter_json": filter_json,
        "limit": limit,
    }

    log_event("query_mongodb_call", arguments, "started", "Tool called with arguments")

    try:
        parsed_filter = json.loads(filter_json or "{}")
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON filter: {exc}"
        log_tool_call("query_mongodb", arguments, message, "error")
        return message

    limit = max(1, min(limit or 5, 20))

    try:
        docs = list(db[collection].find(parsed_filter).limit(limit))
        result = json_util.dumps(docs)
        log_tool_call("query_mongodb", arguments, result, "success")
        return result
    except Exception as exc:
        message = f"MongoDB query failed: {exc}"
        log_tool_call("query_mongodb", arguments, message, "error")
        return message


def find_tests_by_text(search: str):
    search = (search or "").strip()
    if not search:
        return []

    regex = {"$regex": search, "$options": "i"}

    query = {
        "$or": [
            {"name": regex},
            {"testProgramId": regex},
            {"state": regex},
            {"clientAppType": regex},
            {"TestParametersFlat.TYPE_OF_TESTING_STR": regex},
            {"TestParametersFlat.CUSTOMER": regex},
            {"TestParametersFlat.JOB_NO": regex},
            {"TestParametersFlat.SPECIMEN_TYPE": regex},
            {"TestParametersFlat.TESTER": regex},
            {"TestParametersFlat.NOTES": regex},
            {"TestParametersFlat.STANDARD": regex},
        ]
    }

    return list(db["Tests"].find(query).limit(5))


@app.post("/chat")
async def chat(req: ChatRequest):
    log_event(
        "chat_request",
        {
            "message": req.message,
            "history_length": len(req.history),
        },
        "started",
        "Incoming chat request",
    )

    print("DB overview:", debug_db_overview())
    print("Using DB:", MONGO_DB)
    print("Collections:", db.list_collection_names())


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

    try:
        # 1. Get data from Mongo (controlled, deterministic)
        data = find_tests_by_text(req.message)

        # 2. Convert Mongo docs to JSON string
        data_json = json_util.dumps(data)

        # 3. Build prompt
        prompt = f"""
        User question:
        {req.message}

        Database results:
        {data_json}

        Instructions:
        - Summarize the results clearly
        - If no results, say "No matching tests found"
        - Keep it concise
        """

        # 4. Call LLM ONLY for summarization
        response = gemini.models.generate_content(
            model=MODEL,
            contents=[prompt],
        )

        answer_parts = response.candidates[0].content.parts
        answer = " ".join(part.text for part in answer_parts if part.text).strip()

        answer_parts = response.candidates[0].content.parts
        answer = " ".join(part.text for part in answer_parts if part.text).strip()

        log_event(
            "chat_response",
            {
                "message": req.message,
                "history_length": len(req.history),
            },
            "success",
            answer or "Empty response from model",
        )
        return {"answer": answer}
    except Exception as exc:
        log_event(
            "chat_response",
            {
                "message": req.message,
                "history_length": len(req.history),
                "error_type": type(exc).__name__,
            },
            "error",
            str(exc),
        )
        raise


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
