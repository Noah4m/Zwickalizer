"""
MCP Server — Material Testing Lab (Python)
Covers Tier 1 (data retrieval) and Tier 2/3 (comparison + analytics)

Dependencies:
    pip install mcp pymongo scipy numpy python-dotenv

Run:
    python mcp_server_sketch.py

The server communicates over stdio — connect it from your MCP client config:
    {
      "mcpServers": {
        "material-testing": {
          "command": "python",
          "args": ["mcp_server_sketch.py"],
          "env": { "MONGO_URI": "mongodb://localhost:27017", "MONGO_DB": "material_testing" }
        }
      }
    }
"""

import os
import json
import math
import asyncio
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy import stats as scipy_stats
from pymongo import MongoClient
from pymongo.collection import Collection
from bson import ObjectId

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ─── DB connection ────────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "txp_clean")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]

tests_col: Collection = db["_tests"]
values_col: Collection = db["valuecolumns_migrated"]

# ─── Helpers ──────────────────────────────────────────────────────────────────


def build_filename(test_id: str, value_table_id: str) -> str:
    """
    Reconstruct the filename key used in valuecolumns_migrated.
    Adjust the format to match your actual naming convention.
    """
    return f"{test_id}_{value_table_id}"


def resolve_column(test_id: str, value_column: dict) -> list[float]:
    """Look up the actual values array from valuecolumns_migrated."""
    filename = build_filename(str(test_id), str(value_column["valueTableId"]))
    doc = values_col.find_one({"filename": filename})
    if doc and "values" in doc:
        return [v for v in doc["values"] if isinstance(v, (int, float))]
    return []


def fetch_column_values(
    test_id: str, column_name: str, page: int = 0, page_size: int = 500
) -> dict:
    """Paginated raw value fetch for a single test + column."""
    test = tests_col.find_one({"_id": ObjectId(test_id)}, {"valueColumns": 1})
    if not test:
        return {"values": [], "total": 0, "page": page, "page_size": page_size}

    col = next(
        (c for c in test.get("valueColumns", []) if c.get("name") == column_name), None
    )
    if not col:
        return {"values": [], "total": 0, "page": page, "page_size": page_size}

    all_values = resolve_column(str(test["_id"]), col)
    start = page * page_size
    return {
        "values": all_values[start : start + page_size],
        "total": len(all_values),
        "page": page,
        "page_size": page_size,
    }


def collect_property_values(test_ids: list[str], column_name: str) -> list[dict]:
    """
    For a list of test IDs, resolve the join and return
    [{ test_id, date, values: [...] }, ...].
    Never loads all arrays simultaneously — iterates one test at a time.
    """
    results = []
    for tid in test_ids:
        test = tests_col.find_one(
            {"_id": ObjectId(tid)}, {"valueColumns": 1, "TestParametersFlat.date": 1}
        )
        if not test:
            continue
        col = next(
            (c for c in test.get("valueColumns", []) if c.get("name") == column_name),
            None,
        )
        if not col:
            continue
        values = resolve_column(str(test["_id"]), col)
        if values:
            results.append(
                {
                    "test_id": tid,
                    "date": test.get("TestParametersFlat", {}).get("date"),
                    "values": values,
                }
            )
    return results


def flat_values(collected: list[dict]) -> list[float]:
    return [v for entry in collected for v in entry["values"]]


def describe_values(values: list[float]) -> Optional[dict]:
    if not values:
        return None
    arr = np.array(values)
    return {
        "n": len(values),
        "mean": round(float(arr.mean()), 6),
        "std": round(float(arr.std(ddof=1)), 6),
        "min": round(float(arr.min()), 6),
        "max": round(float(arr.max()), 6),
        "median": round(float(np.median(arr)), 6),
        "p5": round(float(np.percentile(arr, 5)), 6),
        "p95": round(float(np.percentile(arr, 95)), 6),
    }


def parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def date_filter(date_from: Optional[str], date_to: Optional[str]) -> dict:
    f: dict = {}
    if date_from:
        f["$gte"] = parse_date(date_from)
    if date_to:
        f["$lte"] = parse_date(date_to)
    elif date_from:
        f["$lte"] = datetime.now(timezone.utc)
    return f


# Minimal projection — always exclude raw value arrays unless requested
META_PROJ = {
    "TestParametersFlat": 1,
    "valueColumns._id": 1,
    "valueColumns.valueTableId": 1,
    "valueColumns.name": 1,
}


def format_test(d: dict) -> dict:
    fp = d.get("TestParametersFlat", {})
    return {
        "testId": str(d["_id"]),
        "date": fp.get("date").isoformat() if fp.get("date") else None,
        "material": fp.get("MATERIAL"),
        "testType": fp.get("TYPE_OF_TESTING_STR"),
        "machine": fp.get("MACHINE"),
        "tester": fp.get("TESTER"),
        "customer": fp.get("CUSTOMER"),
        "standard": fp.get("standard"),
        "specimenWidth": fp.get("SPECIMEN_WIDTH"),
        "diameter": fp.get("DIAMETER"),
        "availableColumns": [
            c["name"] for c in d.get("valueColumns", []) if "name" in c
        ],
    }


def ok(data: dict) -> list[types.TextContent]:
    return [
        types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))
    ]


# ─── MCP Server ───────────────────────────────────────────────────────────────

server = Server("material-testing-mcp")


# ═════════════════════════════════════════════════════════════════════════════
# TIER 1 — Data selection & retrieval
# ═════════════════════════════════════════════════════════════════════════════


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Discovery ─────────────────────────────────────────────────────────
        types.Tool(
            name="list_customers",
            description="List all distinct customer names in the database.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="find_tests",
            description="Find tests for given filters (test type, date, customer, material)",
            inputSchema={
                "type": "object",
                "properties": {
                    "testType": {"type": "string"},
                    "customer": {"type": "string"},
                    "material": {"type": "string"},
                },
            },
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Tool call handler
# ═════════════════════════════════════════════════════════════════════════════


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    # ── Discovery ─────────────────────────────────────────────────────────────

    if name == "list_customers":
        vals = sorted(tests_col.distinct("TestParametersFlat.CUSTOMER"))
        return ok({"customers": vals})

    if name == "find_tests":
        filters = {}
        if "testType" in arguments:
            filters["TestParametersFlat.TYPE_OF_TESTING_STR"] = arguments["testType"]
        if "customer" in arguments:
            filters["TestParametersFlat.CUSTOMER"] = arguments["customer"]
        if "material" in arguments:
            filters["TestParametersFlat.MATERIAL"] = arguments["material"]

        cursor = (
            tests_col.find(filters, META_PROJ)
            .sort("TestParametersFlat.date", -1)
            .limit(100)
        )
        results = [format_test(d) for d in cursor]
        return ok({"tests": results})

    return ok({"error": f"Unknown tool: {name}"})


# ─── Entry point ──────────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
