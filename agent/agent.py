"""
Minimal chat agent using Google Gemini.

Receives a user message plus chat history from the backend,
sends the conversation to Gemini, and returns the model's reply.
"""
import json
import os
import csv
from typing import List, Literal
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from bson import json_util
from google import genai
from pymongo import MongoClient
from pydantic import BaseModel


app = FastAPI(title="MatAI Agent", version="0.1.0")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://host.docker.internal:27017")
MONGO_DB = os.environ.get("MONGO_DB", "test")
MODEL = "gemini-2.5-flash-lite"
LOG_FILE = Path(os.environ.get("TOOL_LOG_FILE", "log.csv"))

gemini = genai.Client(api_key=GEMINI_API_KEY)
mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
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
    role: Literal["engineer", "executive"] | None = None
    history: List[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


def audience_instruction(role: str | None) -> str:
    if role == "executive":
        return (
            "Answer for an executive audience. Focus on the takeaway, risk, and next action. "
            "Keep technical detail to a minimum."
        )
    return (
        "Answer for an engineering audience. Be concrete about findings, relevant fields, and "
        "technical implications."
    )


def format_history(history: List[dict]) -> str:
    lines: list[str] = []
    for item in history:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        speaker = "Assistant" if role == "assistant" else "User"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) if lines else "No prior conversation."



def debug_db_overview():
    try:
        return {
            "db_name": MONGO_DB,
            "collections": db.list_collection_names(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_db_error() -> str | None:
    try:
        mongo.admin.command("ping")
        return None
    except Exception as exc:
        return str(exc)


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


def unavailable_db_message(role: str | None) -> str:
    if role == "executive":
        return (
            "I cannot access the test database right now, so I cannot provide live test results. "
            "Please try again once the database connection is restored."
        )
    return (
        "The test database is not reachable right now, so I cannot query live results. "
        "Please check the MongoDB connection and try again."
    )


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

    try:
        db_error = get_db_error()
        print("DB overview:", debug_db_overview())
        print("Using DB:", MONGO_DB)

        if db_error:
            answer = unavailable_db_message(req.role)
            log_event(
                "chat_response",
                {
                    "message": req.message,
                    "role": req.role,
                    "history_length": len(req.history),
                    "db_available": False,
                },
                "success",
                answer,
            )
            return {"answer": answer}

        # 1. Get data from Mongo (controlled, deterministic)
        try:
            data = find_tests_by_text(req.message)
        except Exception as exc:
            answer = unavailable_db_message(req.role)
            log_event(
                "chat_response",
                {
                    "message": req.message,
                    "role": req.role,
                    "history_length": len(req.history),
                    "db_available": False,
                    "db_error_type": type(exc).__name__,
                },
                "success",
                answer,
            )
            return {"answer": answer}

        # 2. Convert Mongo docs to JSON string
        data_json = json_util.dumps(data)

        # 3. Build prompt
        conversation = format_history(req.history)
        prompt = f"""
System instructions:
{SYSTEM_PROMPT.strip()}

Audience instructions:
{audience_instruction(req.role)}

Conversation history:
{conversation}

Latest user question:
{req.message}

Database results:
{data_json}

Response requirements:
- Answer the latest user question directly
- Use the conversation history when it changes the interpretation
- Summarize the database results clearly
- If no results, say "No matching tests found"
- Keep it concise
""".strip()

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
                "role": req.role,
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
                "role": req.role,
                "history_length": len(req.history),
                "error_type": type(exc).__name__,
            },
            "error",
            str(exc),
        )
        raise


@app.get("/health")
async def health():
    db_error = get_db_error()
    return {
        "status": "ok" if db_error is None else "degraded",
        "database": {
            "reachable": db_error is None,
            "name": MONGO_DB,
            "error": db_error,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
