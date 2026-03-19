"""
Material Testing MCP Server
- Batch value lookups (no more sequential find_one → no timeouts)
- asyncio.wait_for timeout guard on every tool call
- Correct join via metadata.childId
- _tests._id is a plain string, not ObjectId
"""

import os
import json
import asyncio
from typing import List, Dict, Optional

import numpy as np
from pymongo import MongoClient
from pymongo.collection import Collection

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ─────────────────────────────────────────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "txp_clean")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]

tests_col: Collection = db["_tests"]
values_col: Collection = db["valuecolumns_migrated"]

# ─────────────────────────────────────────────────────────────────────────────
# JOIN HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def build_child_id(value_table_id: str, col_id: str) -> str:
    """
    childId = valueColumn.valueTableId + "." + valueColumn._id
    e.g. "{E4C21909-...}-Zwick.Unittable.Displacement.{E4C21909-...}-Zwick.Unittable.Displacement_Value"
    """
    return f"{value_table_id}.{col_id}"


def get_values_batch(tests: List[dict], signal: str) -> Dict[str, List[float]]:
    """
    Fetch values for a signal across many tests in ONE MongoDB query.
    Returns { test_id: [values] }

    Instead of N sequential find_one calls this:
    1. Builds all childIds from the test docs
    2. Fires ONE $in query against valuecolumns_migrated
    3. Maps results back to test_ids
    """
    child_id_to_test_id: Dict[str, str] = {}

    for test in tests:
        col = next(
            (c for c in test.get("valueColumns", []) if c.get("name") == signal),
            None,
        )
        if not col:
            continue
        child_id = build_child_id(col.get("valueTableId", ""), col.get("_id", ""))
        child_id_to_test_id[child_id] = str(test["_id"])

    if not child_id_to_test_id:
        return {}

    # Single batch query — replaces N find_one calls
    docs = values_col.find(
        {"metadata.childId": {"$in": list(child_id_to_test_id.keys())}},
        {"metadata.childId": 1, "values": 1},
    )

    result: Dict[str, List[float]] = {}
    for doc in docs:
        child_id = doc.get("metadata", {}).get("childId")
        test_id = child_id_to_test_id.get(child_id)
        if test_id:
            result[test_id] = [
                v for v in doc.get("values", []) if isinstance(v, (int, float))
            ]

    return result


def get_values_single(test: dict, signal: str) -> List[float]:
    """Single test value lookup — used only by get_test_summary."""
    col = next(
        (c for c in test.get("valueColumns", []) if c.get("name") == signal),
        None,
    )
    if not col:
        return []
    child_id = build_child_id(col.get("valueTableId", ""), col.get("_id", ""))
    doc = values_col.find_one({"metadata.childId": child_id}, {"values": 1})
    if not doc:
        return []
    return [v for v in doc.get("values", []) if isinstance(v, (int, float))]


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def downsample(values: List[float], target: int = 200) -> List[float]:
    if len(values) <= target:
        return values
    idx = np.linspace(0, len(values) - 1, target).astype(int)
    return [values[i] for i in idx]


def extract_features(values: List[float]) -> Optional[Dict]:
    if not values:
        return None
    arr = np.array(values)
    return {
        "count": int(len(values)),
        "min": round(float(arr.min()), 6),
        "max": round(float(arr.max()), 6),
        "mean": round(float(arr.mean()), 6),
        "std": round(float(arr.std()), 6),
        "median": round(float(np.median(arr)), 6),
        "p5": round(float(np.percentile(arr, 5)), 6),
        "p95": round(float(np.percentile(arr, 95)), 6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

META_PROJ = {
    "TestParametersFlat": 1,
    "valueColumns.name": 1,
    "valueColumns.valueTableId": 1,
    "valueColumns._id": 1,  # required for childId join
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
    ]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────────────────


async def _handle(name: str, arguments: dict):

    # ── list_customers ───────────────────────────────────────────────────────
    if name == "list_customers":
        vals = sorted(tests_col.distinct("TestParametersFlat.CUSTOMER"))
        return ok({"customers": vals})

    # ── list_signals ─────────────────────────────────────────────────────────
    if name == "list_signals":
        vals = sorted(tests_col.distinct("valueColumns.name"))
        return ok({"signals": vals})

    # ── find_tests ───────────────────────────────────────────────────────────
    if name == "find_tests":
        filters: dict = {}
        if arguments.get("customer"):
            filters["TestParametersFlat.CUSTOMER"] = {
                "$regex": arguments["customer"],
                "$options": "i",
            }
        if arguments.get("material"):
            filters["TestParametersFlat.MATERIAL"] = {
                "$regex": arguments["material"],
                "$options": "i",
            }
        if arguments.get("testType"):
            filters["TestParametersFlat.TYPE_OF_TESTING_STR"] = {
                "$regex": arguments["testType"],
                "$options": "i",
            }
        limit = int(arguments.get("limit", 50))
        docs = list(tests_col.find(filters, META_PROJ).limit(limit))
        return ok({"count": len(docs), "tests": [format_test(d) for d in docs]})

    # ── get_test_summary ─────────────────────────────────────────────────────
    if name == "get_test_summary":
        test = tests_col.find_one({"_id": arguments["test_id"]}, META_PROJ)
        if not test:
            return ok({"error": f"Test not found: {arguments['test_id']}"})

        signals: dict = {}
        for col in test.get("valueColumns", []):
            signal = col.get("name")
            if not signal:
                continue
            values = get_values_single(test, signal)
            if not values:
                continue
            signals[signal] = {
                "features": extract_features(values),
                "curve": downsample(values, 200),
            }

        return ok({"test": format_test(test), "signals": signals})

    # ── compare_tests ────────────────────────────────────────────────────────
    if name == "compare_tests":
        signal = arguments["signal"]
        test_ids = arguments["test_ids"]

        tests = list(tests_col.find({"_id": {"$in": test_ids}}, META_PROJ))
        values_by_test = get_values_batch(tests, signal)

        results = []
        for test in tests:
            values = values_by_test.get(str(test["_id"]), [])
            if not values:
                continue
            fp = test.get("TestParametersFlat", {})
            results.append(
                {
                    "test_id": test["_id"],
                    "material": fp.get("MATERIAL"),
                    "customer": fp.get("CUSTOMER"),
                    "features": extract_features(values),
                    "curve": downsample(values, 200),
                }
            )

        return ok({"signal": signal, "count": len(results), "comparisons": results})

    # ── find_extreme_tests ───────────────────────────────────────────────────
    if name == "find_extreme_tests":
        signal = arguments["signal"]
        mode = arguments.get("mode", "max")
        feature = arguments.get("feature", "max")
        top_n = int(arguments.get("top_n", 10))
        scan_limit = int(arguments.get("scan_limit", 200))

        pre_filter: dict = {"valueColumns.name": signal}
        if arguments.get("customer"):
            pre_filter["TestParametersFlat.CUSTOMER"] = {
                "$regex": arguments["customer"],
                "$options": "i",
            }
        if arguments.get("material"):
            pre_filter["TestParametersFlat.MATERIAL"] = {
                "$regex": arguments["material"],
                "$options": "i",
            }

        candidates = list(tests_col.find(pre_filter, META_PROJ).limit(scan_limit))

        if not candidates:
            return ok(
                {
                    "error": f"No tests found with signal '{signal}'",
                    "hint": "Call list_signals to see available signal names",
                }
            )

        # ONE batch query — no sequential find_one loop
        values_by_test = get_values_batch(candidates, signal)

        results = []
        for test in candidates:
            values = values_by_test.get(str(test["_id"]), [])
            if not values:
                continue
            feats = extract_features(values)
            if not feats:
                continue
            fp = test.get("TestParametersFlat", {})
            results.append(
                {
                    "test_id": test["_id"],
                    "material": fp.get("MATERIAL"),
                    "customer": fp.get("CUSTOMER"),
                    "testType": fp.get("TYPE_OF_TESTING_STR"),
                    "date": fp.get("date"),
                    "rank_value": feats.get(feature, feats["max"]),
                    "features": feats,
                }
            )

        results.sort(key=lambda x: x["rank_value"], reverse=(mode == "max"))

        return ok(
            {
                "signal": signal,
                "mode": mode,
                "feature": feature,
                "candidates_scanned": len(candidates),
                "matched": len(results),
                "top_tests": results[:top_n],
            }
        )

    # ── debug_join ───────────────────────────────────────────────────────────
    if name == "debug_join":
        test = (
            tests_col.find_one({"_id": arguments["test_id"]}, META_PROJ)
            if arguments.get("test_id")
            else tests_col.find_one(
                {"valueColumns": {"$exists": True, "$ne": []}}, META_PROJ
            )
        )
        if not test:
            return ok({"error": "No test found"})

        val_count = values_col.count_documents({})
        val_sample = values_col.find_one({}, {"metadata": 1})

        probes = []
        for col in test.get("valueColumns", [])[:3]:
            signal = col.get("name", "?")
            value_table_id = col.get("valueTableId", "")
            col_id = col.get("_id", "")
            child_id = build_child_id(value_table_id, col_id)

            doc = values_col.find_one(
                {"metadata.childId": child_id},
                {"metadata.childId": 1, "metadata.refId": 1},
            )
            probes.append(
                {
                    "signal": signal,
                    "childId_built": child_id,
                    "found": doc is not None,
                    "refId_in_db": (
                        doc.get("metadata", {}).get("refId") if doc else None
                    ),
                }
            )

        return ok(
            {
                "test_id": test["_id"],
                "valuecolumns_count": val_count,
                "sample_metadata_in_db": (
                    val_sample.get("metadata") if val_sample else None
                ),
                "probes": probes,
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
