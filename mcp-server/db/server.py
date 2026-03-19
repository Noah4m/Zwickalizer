"""
MCP Server — Material Testing Lab (Python)
Covers Tier 1 (data retrieval) and Tier 2/3 (comparison + analytics)

Dependencies:
    pip install mcp pymongo python-dotenv

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
import asyncio

from pymongo import MongoClient
from pymongo.collection import Collection

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from value_lookup import (
    extract_value_arrays,
    find_test_by_id,
    find_value_column_by_name,
    numeric_values,
    resolve_test_value_columns,
    resolve_value_column_documents,
)

# ─── DB connection ────────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "txp_clean")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]

tests_col: Collection = db["_tests"]
values_col: Collection = db["valuecolumns_migrated"]

# ─────────────────────────────────────────────────────────────────────────────
# JOIN HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def resolve_column(test_id: str, value_column: dict) -> list[float]:
    """Look up the actual numeric values array from valuecolumns_migrated."""
    docs = resolve_value_column_documents(values_col, test_id, value_column)
    if docs:
        return numeric_values(docs[0].get("values", []))
    return []


def fetch_column_values(
    test_id: str, column_name: str, page: int = 0, page_size: int = 500
) -> dict:
    """Paginated raw value fetch for a single test + column."""
    test = find_test_by_id(tests_col, test_id, {"valueColumns": 1})
    if not test:
        return {"values": [], "total": 0, "page": page, "page_size": page_size}

    col = find_value_column_by_name(test, column_name)
    if not col:
        return {"values": [], "total": 0, "page": page, "page_size": page_size}

    all_values = resolve_column(test["_id"], col)
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
        test = find_test_by_id(
            tests_col,
            tid,
            {"valueColumns": 1, "TestParametersFlat.date": 1},
        )
        if not test:
            continue
        col = find_value_column_by_name(test, column_name)
        if not col:
            continue
        values = resolve_column(test["_id"], col)
        if values:
            results.append(
                {
                    "test_id": tid,
                    "date": test.get("TestParametersFlat", {}).get("date"),
                    "values": values,
                }
            )
    return results

# Minimal projection — always exclude raw value arrays unless requested
META_PROJ = {
    "TestParametersFlat": 1,
    "valueColumns.name": 1,
    "valueColumns.valueTableId": 1,
    "valueColumns.name": 1,
    "valueColumns.unitTableId": 1,
}


def format_test(d: dict) -> dict:
    fp = d.get("TestParametersFlat", {})
    return {
        "testId": d["_id"],  # plain string, not ObjectId
        "date": fp.get("date"),
        "material": fp.get("MATERIAL"),
        "testType": fp.get("TYPE_OF_TESTING_STR"),
        "customer": fp.get("CUSTOMER"),
        "tester": fp.get("TESTER"),
        "availableSignals": [
            c["name"] for c in d.get("valueColumns", []) if "name" in c
        ],
    }


def ok(data: dict):
    return [
        types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))
    ]


# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER
# ─────────────────────────────────────────────────────────────────────────────

server = Server("material-testing-analytics")


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="list_customers",
            description="List all distinct customers in the database.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_signals",
            description=(
                "List all distinct signal names (value column names) available. "
                "Always call this before find_extreme_tests to get valid signal names."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="find_tests",
            description=(
                "Find tests by optional filters. "
                "All parameters are optional — omit any to return all."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer": {"type": "string", "description": "Partial match"},
                    "material": {"type": "string", "description": "Partial match"},
                    "testType": {"type": "string", "description": "Partial match"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="get_test_summary",
            description=(
                "Get full analytics for a single test: "
                "features (min/max/mean/std/p5/p95) and downsampled curve for every signal. "
                "Get testId from find_tests first."
            ),
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
            description=(
                "Compare multiple tests on a single signal. "
                "Returns features and downsampled curve per test. "
                "Get testIds from find_tests first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "test_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of testId strings from find_tests",
                    },
                    "signal": {
                        "type": "string",
                        "description": "Signal name from list_signals, e.g. 'Strain / Deformation'",
                    },
                },
                "required": ["test_ids", "signal"],
            },
        ),
        types.Tool(
            name="find_extreme_tests",
            description=(
                "Find tests with the highest or lowest value for a signal. "
                "Returns a ranked list with statistical features. "
                "Call list_signals first to get valid signal names."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "signal": {
                        "type": "string",
                        "description": "Signal name from list_signals",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["max", "min"],
                        "description": "Find highest or lowest values. Default: max",
                    },
                    "feature": {
                        "type": "string",
                        "enum": ["max", "min", "mean", "p95", "p5"],
                        "description": "Statistic to rank by. Default: max",
                    },
                    "customer": {"type": "string", "description": "Optional filter"},
                    "material": {"type": "string", "description": "Optional filter"},
                    "top_n": {
                        "type": "integer",
                        "description": "Results to return. Default: 10",
                    },
                    "scan_limit": {
                        "type": "integer",
                        "description": "Max candidates to scan. Default: 200.",
                    },
                },
                "required": ["signal"],
            },
        ),
        types.Tool(
            name="debug_join",
            description=(
                "Verify the join between _tests and valuecolumns_migrated. "
                "Use if signals are returning empty values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "Optional specific test ID",
                    },
                },
            },
        ),
        types.Tool(
            name="get_test_value_columns",
            description=(
                "Resolve all stored valuecolumns_migrated entries for a single test id "
                "by joining metadata.refId and metadata.childId. Returns only _Value columns. "
                "By default this returns metadata and counts only; raw values are opt-in. "
                "Set strict=false to return every valuecolumns_migrated document for the test refId."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "The _tests._id value for the test to resolve.",
                    },
                    "strict": {
                        "type": "boolean",
                        "description": "When true, only return validated _Value matches from test.valueColumns. When false, return all documents with metadata.refId matching the test id.",
                        "default": True,
                    },
                    "include_values": {
                        "type": "boolean",
                        "description": "Set true to include raw values arrays in the response.",
                        "default": False,
                    },
                    "values_limit": {
                        "type": "integer",
                        "description": "Maximum number of values to return per matched column when include_values=true.",
                        "minimum": 0,
                    },
                },
                "required": ["test_id"],
            },
        ),
        types.Tool(
            name="get_test_value_arrays",
            description=(
                "Return the values arrays for a single test id as an array of arrays. "
                "Use strict=true for validated _Value matches only, or strict=false for all documents with matching metadata.refId."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "The _tests._id value for the test to resolve.",
                    },
                    "strict": {
                        "type": "boolean",
                        "description": "When true, only return validated _Value matches from test.valueColumns. When false, return all documents with metadata.refId matching the test id.",
                        "default": True,
                    },
                    "values_limit": {
                        "type": "integer",
                        "description": "Maximum number of values to return per matched document.",
                        "minimum": 0,
                    },
                },
                "required": ["test_id"],
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

    # ── list_signals ─────────────────────────────────────────────────────────
    if name == "list_signals":
        vals = sorted(tests_col.distinct("valueColumns.name"))
        return ok({"signals": vals})

    # ── find_tests ───────────────────────────────────────────────────────────
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
            .limit(5)
        )
        results = [format_test(d) for d in cursor]
        return ok({"tests": results})

    if name == "get_test_value_columns":
        test_id = arguments["test_id"]
        strict = bool(arguments.get("strict", True))
        include_values = bool(arguments.get("include_values", False))
        values_limit = arguments.get("values_limit")
        resolved = resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            strict=strict,
            include_values=include_values,
            values_limit=values_limit if isinstance(values_limit, int) else None,
        )
        if resolved is None:
            return ok({"error": f"Test not found for id: {test_id}", "valueColumns": []})
        return ok(
            {
                "testId": test_id,
                "count": len(resolved),
                "strict": strict,
                "includeValues": include_values,
                "valuesLimit": values_limit if isinstance(values_limit, int) else None,
                "valueColumns": resolved,
            }
        )

    if name == "get_test_value_arrays":
        test_id = arguments["test_id"]
        strict = bool(arguments.get("strict", True))
        values_limit = arguments.get("values_limit")
        resolved = resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            strict=strict,
            include_values=True,
            values_limit=values_limit if isinstance(values_limit, int) else None,
        )
        if resolved is None:
            return ok({"error": f"Test not found for id: {test_id}", "valueArrays": []})
        return ok(
            {
                "testId": test_id,
                "strict": strict,
                "count": len(resolved),
                "valuesLimit": values_limit if isinstance(values_limit, int) else None,
                "valueArrays": extract_value_arrays(resolved),
            }
        )

    return ok({"error": f"Unknown tool: {name}"})


# ─────────────────────────────────────────────────────────────────────────────
# CALL TOOL — wraps every call with a 60s timeout
# ─────────────────────────────────────────────────────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        return await asyncio.wait_for(_handle(name, arguments), timeout=60.0)
    except asyncio.TimeoutError:
        return ok(
            {
                "error": "Tool timed out after 60s",
                "hint": (
                    "Reduce scope: add customer/material filters, "
                    "lower scan_limit, or call list_signals first"
                ),
            }
        )


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
