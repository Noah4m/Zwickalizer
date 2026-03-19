"""
Improved MCP Server — Material Testing Lab (Analytics-first)

Key improvements:
- Downsampling (no raw 44k arrays exposed)
- Feature extraction
- Test summaries
- Test comparison
- LLM-friendly responses

Run:
    python mcp_server.py
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict

import numpy as np
from pymongo import MongoClient
from pymongo.collection import Collection
from bson import ObjectId

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ─────────────────────────────────────────────────────────────────────────────
# DB CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "txp_clean")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]

tests_col: Collection = db["_tests"]
values_col: Collection = db["valuecolumns_migrated"]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def build_filename(test_id: str, value_table_id: str) -> str:
    return f"{test_id}_{value_table_id}"


def resolve_column(test_id: str, value_column: dict) -> List[float]:
    filename = build_filename(test_id, str(value_column["valueTableId"]))
    doc = values_col.find_one({"filename": filename})
    if doc and "values" in doc:
        return [v for v in doc["values"] if isinstance(v, (int, float))]
    return []


# ─── Downsampling ────────────────────────────────────────────────────────────


def downsample(values: List[float], target_points: int = 200) -> List[float]:
    if len(values) <= target_points:
        return values
    idx = np.linspace(0, len(values) - 1, target_points).astype(int)
    return [values[i] for i in idx]


# ─── Feature extraction ──────────────────────────────────────────────────────


def extract_features(values: List[float]) -> Optional[Dict]:
    if not values:
        return None

    arr = np.array(values)

    return {
        "count": len(values),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "median": float(np.median(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
        "trend": float((arr[-1] - arr[0]) / len(arr)),  # simple slope
    }


# ─── Metadata formatting ─────────────────────────────────────────────────────

META_PROJ = {
    "TestParametersFlat": 1,
    "valueColumns.name": 1,
    "valueColumns.valueTableId": 1,
}


def format_test(d: dict) -> dict:
    fp = d.get("TestParametersFlat", {})

    return {
        "testId": str(d["_id"]),
        "date": fp.get("date").isoformat() if fp.get("date") else None,
        "material": fp.get("MATERIAL"),
        "testType": fp.get("TYPE_OF_TESTING_STR"),
        "customer": fp.get("CUSTOMER"),
        "tester": fp.get("TESTER"),
        "availableColumns": [c["name"] for c in d.get("valueColumns", [])],
    }


def ok(data: dict):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER
# ─────────────────────────────────────────────────────────────────────────────

server = Server("material-testing-analytics-mcp")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────


@server.list_tools()
async def list_tools():
    return [
        # Discovery
        types.Tool(
            name="list_customers",
            description="List all customers",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="find_tests",
            description="Find tests using filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer": {"type": "string"},
                    "material": {"type": "string"},
                    "testType": {"type": "string"},
                },
            },
        ),
        # Core Analytics
        types.Tool(
            name="get_test_summary",
            description="Get summarized analytics for a test",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {"type": "string"},
                },
                "required": ["test_id"],
            },
        ),
        types.Tool(
            name="compare_tests",
            description="Compare multiple tests for a column",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "column": {"type": "string"},
                },
                "required": ["test_ids", "column"],
            },
        ),
        types.Tool(
            name="find_extreme_tests",
            description="Find tests with extreme values",
            inputSchema={
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "mode": {"type": "string"},  # max / min
                },
                "required": ["column"],
            },
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL HANDLER
# ─────────────────────────────────────────────────────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict):

    # ─── list_customers ──────────────────────────────────────────────────────
    if name == "list_customers":
        vals = sorted(tests_col.distinct("TestParametersFlat.CUSTOMER"))
        return ok({"customers": vals})

    # ─── find_tests ──────────────────────────────────────────────────────────
    if name == "find_tests":
        filters = {}

        if "customer" in arguments:
            filters["TestParametersFlat.CUSTOMER"] = arguments["customer"]
        if "material" in arguments:
            filters["TestParametersFlat.MATERIAL"] = arguments["material"]
        if "testType" in arguments:
            filters["TestParametersFlat.TYPE_OF_TESTING_STR"] = arguments["testType"]

        cursor = tests_col.find(filters, META_PROJ).limit(50)

        return ok({"tests": [format_test(d) for d in cursor]})

    # ─── get_test_summary ────────────────────────────────────────────────────
    if name == "get_test_summary":
        test_id = arguments["test_id"]

        test = tests_col.find_one({"_id": ObjectId(test_id)}, META_PROJ)
        if not test:
            return ok({"error": "Test not found"})

        result = {}

        for col in test.get("valueColumns", []):
            values = resolve_column(str(test["_id"]), col)

            if not values:
                continue

            result[col["name"]] = {
                "features": extract_features(values),
                "curve": downsample(values, 200),
            }

        return ok(
            {
                "test": format_test(test),
                "columns": result,
            }
        )

    # ─── compare_tests ───────────────────────────────────────────────────────
    if name == "compare_tests":
        test_ids = arguments["test_ids"]
        column_name = arguments["column"]

        comparisons = []

        for tid in test_ids:
            test = tests_col.find_one({"_id": ObjectId(tid)}, META_PROJ)
            if not test:
                continue

            col = next(
                (c for c in test.get("valueColumns", []) if c["name"] == column_name),
                None,
            )

            if not col:
                continue

            values = resolve_column(str(test["_id"]), col)

            if not values:
                continue

            comparisons.append(
                {
                    "test_id": tid,
                    "features": extract_features(values),
                    "curve": downsample(values, 200),
                }
            )

        return ok(
            {
                "column": column_name,
                "comparisons": comparisons,
            }
        )

    # ─── find_extreme_tests ──────────────────────────────────────────────────
    if name == "find_extreme_tests":
        column = arguments["column"]
        mode = arguments.get("mode", "max")

        results = []

        for test in tests_col.find({}, META_PROJ).limit(200):

            col = next(
                (c for c in test.get("valueColumns", []) if c["name"] == column),
                None,
            )

            if not col:
                continue

            values = resolve_column(str(test["_id"]), col)

            if not values:
                continue

            features = extract_features(values)

            if not features:
                continue

            value = features["max"] if mode == "max" else features["min"]

            results.append(
                {
                    "test_id": str(test["_id"]),
                    "value": value,
                }
            )

        results.sort(key=lambda x: x["value"], reverse=(mode == "max"))

        return ok(
            {
                "top_tests": results[:10],
            }
        )

    return ok({"error": f"Unknown tool: {name}"})


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
