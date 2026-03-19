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
    "valueColumns.unitTableId": 1,
}


def format_test(d: dict) -> dict:
    fp = d.get("TestParametersFlat", {})
    return {
        "testId": str(d["_id"]),
        "date": fp.get("date").isoformat() if fp.get("date") else None,
        "material": fp.get("material"),
        "testType": fp.get("testType"),
        "machine": fp.get("machine"),
        "tester": fp.get("tester"),
        "customer": fp.get("customer"),
        "standard": fp.get("standard"),
        "specimenWidth": fp.get("specimenWidth"),
        "diameter": fp.get("diameter"),
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
        # ── Tier 1 ────────────────────────────────────────────────────────────
        types.Tool(
            name="get_results_for_test_date_material",
            description=(
                "Find tests by date range and material name. "
                "Returns metadata only — no raw measurement values. "
                "Call this first to discover relevant test IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "material": {
                        "type": "string",
                        "description": "Material name, e.g. 'FancyPlast 42'",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "ISO date, e.g. '2024-05-01'",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "ISO date. Defaults to today.",
                    },
                    "test_type": {
                        "type": "string",
                        "description": "e.g. 'compression', 'tensile', 'charpy'",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["material", "date_from"],
            },
        ),
        types.Tool(
            name="get_results_for_date",
            description="List all tests on a date or date range regardless of material.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "customer": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["date_from"],
            },
        ),
        types.Tool(
            name="list_tests_by_tester",
            description=(
                "List all tests performed by a specific tester, "
                "optionally filtered by test type (e.g. 'charpy')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tester": {"type": "string"},
                    "test_type": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["tester"],
            },
        ),
        types.Tool(
            name="get_material_properties",
            description=(
                "Aggregated statistics (mean, std, min, max, p5/p95) for a material's measured columns. "
                "Never returns raw value arrays. Use for 'summarize material properties' queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "material": {"type": "string"},
                    "property_column": {
                        "type": "string",
                        "description": "Specific column. Omit for all.",
                    },
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["material"],
            },
        ),
        types.Tool(
            name="get_test_values_paginated",
            description=(
                "Fetch raw measurement values for a specific test and column. "
                "Use only when actual data points are needed, not summaries. "
                "Prefer get_material_properties for aggregates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "MongoDB _id of the test",
                    },
                    "column_name": {"type": "string"},
                    "page": {"type": "integer", "default": 0, "minimum": 0},
                    "page_size": {
                        "type": "integer",
                        "default": 500,
                        "minimum": 10,
                        "maximum": 1000,
                    },
                },
                "required": ["test_id", "column_name"],
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
        types.Tool(
            name="get_quality_outcome_on_site",
            description="Compare aggregated quality metrics across sites (e.g. Ulm vs Kennesaw).",
            inputSchema={
                "type": "object",
                "properties": {
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "property_column": {"type": "string"},
                    "material": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["sites", "property_column"],
            },
        ),
        # ── Tier 2 ────────────────────────────────────────────────────────────
        types.Tool(
            name="compare_materials",
            description=(
                "Statistically compare a measured property between two materials. "
                "Returns means, std, and Welch t-test (p-value, significance)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "material_a": {"type": "string"},
                    "material_b": {"type": "string"},
                    "property_column": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["material_a", "material_b", "property_column"],
            },
        ),
        types.Tool(
            name="compare_machines",
            description=(
                "Compare measurement results between two machines for the same property. "
                "Returns Welch t-test result and per-machine stats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "machine_a": {"type": "string"},
                    "machine_b": {"type": "string"},
                    "property_column": {"type": "string"},
                    "material": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["machine_a", "machine_b", "property_column"],
            },
        ),
        # ── Tier 3 ────────────────────────────────────────────────────────────
        types.Tool(
            name="get_trend",
            description=(
                "Detect trends in a measured property over time. "
                "Returns linear regression (slope, R²) and Mann-Kendall monotonic trend test. "
                "Data is bucketed by week or month before regression to avoid test-level noise."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "property_column": {"type": "string"},
                    "material": {"type": "string"},
                    "site": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "bucket": {
                        "type": "string",
                        "enum": ["week", "month"],
                        "default": "month",
                    },
                },
                "required": ["property_column", "date_from"],
            },
        ),
        types.Tool(
            name="check_limit_violation",
            description=(
                "Check current violation rate against a spec limit, "
                "and project the trend to estimate when/if the limit will be crossed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "property_column": {"type": "string"},
                    "limit_value": {"type": "number"},
                    "limit_direction": {
                        "type": "string",
                        "enum": ["above", "below"],
                        "description": "'above' = must stay above limit, 'below' = must stay below",
                    },
                    "material": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["property_column", "limit_value", "limit_direction"],
            },
        ),
        # ── Discovery ─────────────────────────────────────────────────────────
        types.Tool(
            name="list_customers",
            description="List all distinct customer names in the database.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_materials",
            description="List all distinct material names, optionally filtered by customer.",
            inputSchema={
                "type": "object",
                "properties": {"customer": {"type": "string"}},
            },
        ),
        types.Tool(
            name="list_test_types",
            description="List all distinct test types (e.g. tensile, charpy, compression).",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_machines",
            description="List all distinct machine identifiers.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_column_names_for_material",
            description=(
                "List value column names available for a material. "
                "Call before get_test_values_paginated or get_material_properties."
            ),
            inputSchema={
                "type": "object",
                "properties": {"material": {"type": "string"}},
                "required": ["material"],
            },
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Tool call handler
# ═════════════════════════════════════════════════════════════════════════════


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    # ── Tier 1 ────────────────────────────────────────────────────────────────

    if name == "get_results_for_test_date_material":
        material = arguments["material"]
        date_from = arguments["date_from"]
        date_to = arguments.get("date_to")
        test_type = arguments.get("test_type")
        limit = arguments.get("limit", 50)

        filt: dict = {
            "TestParametersFlat.material": {"$regex": material, "$options": "i"},
            "TestParametersFlat.date": date_filter(date_from, date_to),
        }
        if test_type:
            filt["TestParametersFlat.testType"] = {"$regex": test_type, "$options": "i"}

        docs = list(tests_col.find(filt, META_PROJ).limit(limit))
        return ok({"count": len(docs), "tests": [format_test(d) for d in docs]})

    # ─────────────────────────────────────────────────────────────────────────

    if name == "get_results_for_date":
        date_from = arguments["date_from"]
        date_to = arguments.get("date_to") or (date_from[:10] + "T23:59:59")
        customer = arguments.get("customer")
        limit = arguments.get("limit", 50)

        filt: dict = {"TestParametersFlat.date": date_filter(date_from, date_to)}
        if customer:
            filt["TestParametersFlat.customer"] = {"$regex": customer, "$options": "i"}

        docs = list(tests_col.find(filt, META_PROJ).limit(limit))
        return ok({"count": len(docs), "tests": [format_test(d) for d in docs]})

    # ─────────────────────────────────────────────────────────────────────────

    if name == "list_tests_by_tester":
        tester = arguments["tester"]
        test_type = arguments.get("test_type")
        limit = arguments.get("limit", 50)

        filt: dict = {"TestParametersFlat.tester": {"$regex": tester, "$options": "i"}}
        if test_type:
            filt["TestParametersFlat.testType"] = {"$regex": test_type, "$options": "i"}

        docs = list(
            tests_col.find(filt, META_PROJ)
            .sort("TestParametersFlat.date", -1)
            .limit(limit)
        )
        return ok({"count": len(docs), "tests": [format_test(d) for d in docs]})

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

    # ─────────────────────────────────────────────────────────────────────────

    if name == "get_material_properties":
        material = arguments["material"]
        prop_col = arguments.get("property_column")
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")

        filt: dict = {
            "TestParametersFlat.material": {"$regex": material, "$options": "i"}
        }
        df = date_filter(date_from, date_to)
        if df:
            filt["TestParametersFlat.date"] = df

        docs = list(tests_col.find(filt, {"_id": 1, "valueColumns": 1}))

        all_col_names = list(
            {c["name"] for d in docs for c in d.get("valueColumns", []) if "name" in c}
        )
        target_cols = (
            [n for n in all_col_names if prop_col.lower() in n.lower()]
            if prop_col
            else all_col_names
        )

        properties: dict = {}
        test_ids = [str(d["_id"]) for d in docs]
        for col_name in target_cols:
            collected = collect_property_values(test_ids, col_name)
            flat = flat_values(collected)
            if flat:
                properties[col_name] = describe_values(flat)

        return ok(
            {
                "material": material,
                "test_count": len(docs),
                "date_range": {"from": date_from, "to": date_to},
                "properties": properties,
            }
        )

    # ── Discovery ─────────────────────────────────────────────────────────────

    if name == "list_customers":
        vals = sorted(tests_col.distinct("TestParametersFlat.CUSTOMER"))
        return ok({"customers": vals})

    if name == "list_materials":
        filt = {}
        if arguments.get("customer"):
            filt["TestParametersFlat.customer"] = {
                "$regex": arguments["customer"],
                "$options": "i",
            }
        vals = sorted(tests_col.distinct("TestParametersFlat.material", filt))
        return ok({"materials": vals})

    if name == "list_test_types":
        vals = sorted(tests_col.distinct("TestParametersFlat.testType"))
        return ok({"test_types": vals})

    if name == "list_machines":
        vals = sorted(tests_col.distinct("TestParametersFlat.machine"))
        return ok({"machines": vals})

    if name == "list_column_names_for_material":
        doc = tests_col.find_one(
            {
                "TestParametersFlat.material": {
                    "$regex": arguments["material"],
                    "$options": "i",
                }
            },
            {"valueColumns.name": 1},
        )
        cols = [c["name"] for c in (doc or {}).get("valueColumns", []) if "name" in c]
        return ok({"columns": cols})

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
