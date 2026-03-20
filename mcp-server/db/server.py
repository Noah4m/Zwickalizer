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
from pathlib import Path
import asyncio
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from pymongo.collection import Collection
from bson import ObjectId
import logging

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

# ─── Helpers ──────────────────────────────────────────────────────────────────


def parse_iso_date(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_date_only(value: str | None) -> bool:
    return isinstance(value, str) and "T" not in value and " " not in value


def build_test_date_filter(
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    if date_value:
        start = parse_iso_date(date_value)
        if start is None:
            return {}
        if _is_date_only(date_value):
            return {"$gte": start, "$lt": start + timedelta(days=1)}
        return {"$gte": start, "$lte": start}

    filt: dict = {}
    start = parse_iso_date(date_from)
    end = parse_iso_date(date_to)

    if start is not None:
        filt["$gte"] = start
    if end is not None:
        if _is_date_only(date_to):
            filt["$lt"] = end + timedelta(days=1)
        else:
            filt["$lte"] = end
    return filt


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
    "_id": 1,
    "name": 1,
    "TestParametersFlat": 1,
    "valueColumns._id": 1,
    "valueColumns.valueTableId": 1,
    "valueColumns.name": 1,
    "valueColumns.unitTableId": 1,
}


# Fixed fields to always show first
_FIXED_KEYS = ["testId", "name", "date"]

# Keys to always exclude from output
_EXCLUDED_KEYS = {"date", "Date", "Date/Clock time", "Clock time"}


def format_test(d: dict) -> dict:
    fp = d.get("TestParametersFlat", {})

    result: dict = {
        "testId": str(d["_id"]).strip("{}"),
        "name": d.get("name"),
        "date": fp.get("Date") or fp.get("date"),
    }
    if result["date"] and hasattr(result["date"], "isoformat"):
        result["date"] = result["date"].isoformat()

    # Add all remaining TestParametersFlat fields dynamically
    for key, value in fp.items():
        if key not in _EXCLUDED_KEYS and value is not None:
            result[key] = value

    result["availableColumns"] = [
        c["name"] for c in d.get("valueColumns", []) if "name" in c
    ]

    return result


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
            description=(
                "Search for material tests in the database using one or more filters. "
                "All filters are optional and combined with AND logic. "
                "Returns the 10 most recent matching tests sorted by date descending. "
                "Use list_customers to discover valid customer names before filtering. "
                "Supports exact date matching or open/closed date ranges. "
                "Use id to look up a single specific test directly. "
                "Use name to filter tests that contain a specific value column such as 'force' or 'displacement'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "_id": {
                        "type": "string",
                        "description": 'Exact match on the test _id, e.g. "{641a7c8f9f1b2c3d4e5f6789}". Id\'s should have curly brackets. Use this to look up a single known test directly.',
                    },
                    "testType": {
                        "type": "string",
                        "description": "Filter by test type, e.g. 'Tensile test'. Exact match on TYPE_OF_TESTING_STR.",
                    },
                    "customer": {
                        "type": "string",
                        "description": "Filter by customer name. Use list_customers to find valid values. Exact match on CUSTOMER.",
                    },
                    "material": {
                        "type": "string",
                        "description": "Filter by material designation, e.g. '7075-T6'. Exact match on MATERIAL.",
                    },
                    "tester": {
                        "type": "string",
                        "description": "Filter by the name of the person who ran the test. Exact match on TESTER.",
                    },
                    "machine_nr": {
                        "type": "string",
                        "description": "Filter by machine identifier, e.g. 'Zwick1'. Exact match on MACHINE.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Filter by the test name. Exact match on the top-level name field of the test document.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Exact date in ISO format, e.g. '2026-03-19'. Matches all tests within that UTC day. Cannot be combined with date_from or date_to.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Inclusive start of a date range in ISO format, e.g. '2026-03-01'.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Inclusive end of a date range in ISO format, e.g. '2026-03-31'.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Defaults to 10, maximum 50.",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
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
                "Set strict=false to return every valuecolumns_migrated document for the test refId, "
                "or pass value_column_index to return only the migrated entry mapped from one "
                "specific test.valueColumns array position."
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
                    "value_column_index": {
                        "type": "integer",
                        "description": "Optional zero-based index into test.valueColumns. Example: 0 returns only the migrated entry mapped from test.valueColumns[0].",
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
                "Use strict=true for validated _Value matches only, or strict=false for all documents with matching metadata.refId. "
                "Pass value_column_index to return only the array mapped from one specific test.valueColumns entry."
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
                    "value_column_index": {
                        "type": "integer",
                        "description": "Optional zero-based index into test.valueColumns. Example: 0 returns only the migrated array mapped from test.valueColumns[0].",
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

    if name == "find_tests":
        filters = {}

        if "_id" in arguments:
            raw_id = arguments["_id"].strip()
            # Ensure it has the curly brace wrapper that matches the stored format
            if not raw_id.startswith("{"):
                raw_id = f"{{{raw_id}}}"
            filters["_id"] = raw_id

        if "testType" in arguments:
            filters["TestParametersFlat.TYPE_OF_TESTING_STR"] = arguments["testType"]
        if "customer" in arguments:
            filters["TestParametersFlat.CUSTOMER"] = arguments["customer"]
        if "material" in arguments:
            filters["TestParametersFlat.MATERIAL"] = arguments["material"]
        if "tester" in arguments:
            filters["TestParametersFlat.TESTER"] = arguments["tester"]
        if "machine_nr" in arguments:
            filters["TestParametersFlat.MACHINE_DATA"] = arguments["machine_nr"]
        if "name" in arguments:
            filters["name"] = arguments["name"]

        date_filter = build_test_date_filter(
            arguments.get("date"),
            arguments.get("date_from"),
            arguments.get("date_to"),
        )
        if date_filter:
            filters["TestParametersFlat.date"] = date_filter

        limit = min(int(arguments.get("limit", 10)), 50)

        cursor = (
            tests_col.find(filters, META_PROJ)
            .sort("TestParametersFlat.date", -1)
            .limit(limit)
        )
        results = [format_test(d) for d in cursor]
        return ok(
            {
                "tests": results,
                "count": len(results),
                "filters_applied": list(filters.keys()),
            }
        )

    if name == "get_test_value_columns":
        test_id = arguments["test_id"]
        strict = bool(arguments.get("strict", True))
        include_values = bool(arguments.get("include_values", False))
        values_limit = arguments.get("values_limit")
        value_column_index = arguments.get("value_column_index")
        resolved = resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            strict=strict,
            include_values=include_values,
            values_limit=values_limit if isinstance(values_limit, int) else None,
            value_column_index=(
                value_column_index if isinstance(value_column_index, int) else None
            ),
        )
        if resolved is None:
            return ok(
                {"error": f"Test not found for id: {test_id}", "valueColumns": []}
            )
        return ok(
            {
                "testId": test_id,
                "count": len(resolved),
                "strict": strict,
                "includeValues": include_values,
                "valuesLimit": values_limit if isinstance(values_limit, int) else None,
                "valueColumnIndex": (
                    value_column_index if isinstance(value_column_index, int) else None
                ),
                "valueColumns": resolved,
            }
        )

    if name == "get_test_value_arrays":
        test_id = arguments["test_id"]
        strict = bool(arguments.get("strict", True))
        values_limit = arguments.get("values_limit")
        value_column_index = arguments.get("value_column_index")
        resolved = resolve_test_value_columns(
            tests_col,
            values_col,
            test_id,
            strict=strict,
            include_values=True,
            values_limit=values_limit if isinstance(values_limit, int) else None,
            value_column_index=(
                value_column_index if isinstance(value_column_index, int) else None
            ),
        )
        if resolved is None:
            return ok({"error": f"Test not found for id: {test_id}", "valueArrays": []})
        return ok(
            {
                "testId": test_id,
                "strict": strict,
                "count": len(resolved),
                "valuesLimit": values_limit if isinstance(values_limit, int) else None,
                "valueColumnIndex": (
                    value_column_index if isinstance(value_column_index, int) else None
                ),
                "valueArrays": extract_value_arrays(resolved),
            }
        )

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
