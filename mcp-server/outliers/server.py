import asyncio
import json
import os

from pymongo import MongoClient
from pymongo.collection import Collection

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from outlier_lookup import find_outliers


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "txp_clean")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]

tests_col: Collection = db["_tests"]
values_col: Collection = db["valuecolumns_migrated"]

server = Server("outliers-mcp")


def ok(data: dict) -> list[types.TextContent]:
    return [
        types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_review_outliers",
            description=(
                "Find a small ranked set of likely outlier tests using sampled Mongo data. "
                "This tool is intended for the engineer outlier review queue."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                    },
                    "sample_size": {
                        "type": "integer",
                        "minimum": 10,
                        "maximum": 300,
                        "default": 80,
                    },
                    "test_type": {
                        "type": "string",
                        "default": "tensile",
                    },
                },
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "list_review_outliers":
        payload = find_outliers(
            tests_col,
            values_col,
            limit=int(arguments.get("limit", 6)),
            sample_size=int(arguments.get("sample_size", 80)),
            test_type=str(arguments.get("test_type", "tensile")),
        )
        return ok(payload)

    return ok({"error": f"Unknown tool: {name}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
