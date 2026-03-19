import json
import os
import sys
from typing import Any

from bson import json_util
from pymongo import MongoClient


MONGO_URI = os.environ.get("MONGO_URI", "mongodb://host.docker.internal:27017")
MONGO_DB = os.environ.get("MONGO_DB", "test")

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
db = mongo[MONGO_DB]


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}

    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        decoded = line.decode("utf-8")
        if decoded in ("\r\n", "\n"):
            break
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    content_length = int(headers["content-length"])
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def success(message_id: int, result: dict[str, Any]) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def error(message_id: int, code: int, message: str) -> None:
    write_message(
        {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }
    )


def list_collections() -> list[str]:
    mongo.admin.command("ping")
    return db.list_collection_names()


def query_collection(collection: str, filter_json: str = "{}", limit: int = 5) -> str:
    mongo.admin.command("ping")
    parsed_filter = json.loads(filter_json or "{}")
    bounded_limit = max(1, min(limit or 5, 50))
    docs = list(db[collection].find(parsed_filter).limit(bounded_limit))
    return json_util.dumps(docs)


def search_tests(search: str, limit: int = 5) -> str:
    mongo.admin.command("ping")
    search = (search or "").strip()
    if not search:
        return json_util.dumps([])

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
    bounded_limit = max(1, min(limit or 5, 50))
    docs = list(db["Tests"].find(query).limit(bounded_limit))
    return json_util.dumps(docs)


TOOLS = {
    "list_collections": {
        "description": "List the collections available in the configured MongoDB database.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": lambda _args: json.dumps(list_collections()),
    },
    "query_collection": {
        "description": "Query any MongoDB collection with a JSON filter string and limit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string"},
                "filter_json": {"type": "string", "default": "{}"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["collection"],
        },
        "handler": lambda args: query_collection(
            collection=args["collection"],
            filter_json=args.get("filter_json", "{}"),
            limit=args.get("limit", 5),
        ),
    },
    "search_tests": {
        "description": "Search the Tests collection by free text across common fields.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["search"],
        },
        "handler": lambda args: search_tests(
            search=args["search"],
            limit=args.get("limit", 5),
        ),
    },
}


def handle_request(message: dict[str, Any]) -> None:
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})

    if method == "initialize":
        success(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "db-mcp-server", "version": "0.1.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
        return

    if method == "tools/list":
        success(
            message_id,
            {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            },
        )
        return

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        spec = TOOLS.get(name)
        if spec is None:
            error(message_id, -32601, f"Unknown tool: {name}")
            return

        try:
            result = spec["handler"](arguments)
            success(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": result,
                        }
                    ],
                    "isError": False,
                },
            )
        except Exception as exc:
            success(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Database tool error: {exc}",
                        }
                    ],
                    "isError": True,
                },
            )
        return

    if message_id is not None:
        error(message_id, -32601, f"Unsupported method: {method}")


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            break
        handle_request(message)


if __name__ == "__main__":
    main()
