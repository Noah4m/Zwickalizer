"""
MCP Server — exposes the txp-database MongoDB as tools the agent can call.

Connects to the external txp-mongo container via host.docker.internal:27017.
Each endpoint = one tool. The agent sends structured args, gets structured JSON back.

Expected MongoDB structure (adapt COLLECTION / field names to match txp-mongo):
  db: txp
  collection: test_results
  document shape:
    {
      material_name: str,
      machine_id:    str,
      site:          str,
      operator:      str,
      property_name: str,   e.g. "tensile_strength"
      value:         float,
      unit:          str,
      tested_at:     ISODate
    }
"""
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import statistics

app = FastAPI(title="MatAI MCP Server (MongoDB)", version="0.1.0")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://host.docker.internal:27017")
MONGO_DB  = os.environ.get("MONGO_DB", "txp")
COLLECTION = "test_results"   # ← change to match your actual collection name

_client: AsyncIOMotorClient = None
_db = None


@app.on_event("startup")
async def startup():
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    _db = _client[MONGO_DB]
    # Ensure useful indexes exist (no-op if already present)
    col = _db[COLLECTION]
    await col.create_index([("material_name", 1), ("property_name", 1)])
    await col.create_index([("tested_at", 1)])


@app.on_event("shutdown")
async def shutdown():
    _client.close()


def _serialize(doc: dict) -> dict:
    """Make a Mongo document JSON-safe (convert ObjectId, datetime)."""
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ── Tool: list available materials ───────────────────────────────────────────

@app.get("/tools/list_materials")
async def list_materials():
    """Return all distinct material names in the DB."""
    names = await _db[COLLECTION].distinct("material_name")
    return {"materials": sorted(names)}


# ── Tool: list available collections / fields (discovery helper) ─────────────

@app.get("/tools/describe_db")
async def describe_db():
    """Return collection names and a sample document so the agent can explore."""
    collections = await _db.list_collection_names()
    result = {}
    for col in collections:
        sample = await _db[col].find_one({}, {"_id": 0})
        result[col] = {
            "fields": list(sample.keys()) if sample else [],
            "sample": _serialize(sample) if sample else {},
        }
    return result


# ── Tool: query test results ──────────────────────────────────────────────────

class QueryTestsRequest(BaseModel):
    material_name: Optional[str] = None
    machine_id:    Optional[str] = None
    site:          Optional[str] = None
    property_name: Optional[str] = None
    date_from:     Optional[str] = None   # ISO date string e.g. "2024-01-01"
    date_to:       Optional[str] = None
    limit:         int = 500


@app.post("/tools/query_tests")
async def query_tests(req: QueryTestsRequest):
    """
    Flexible query. Returns documents matching the filters.
    The agent decides which filters to apply based on the user question.
    """
    filt: dict = {}

    if req.material_name:
        filt["material_name"] = req.material_name
    if req.machine_id:
        filt["machine_id"] = req.machine_id
    if req.site:
        filt["site"] = req.site
    if req.property_name:
        filt["property_name"] = req.property_name

    date_filt: dict = {}
    if req.date_from:
        date_filt["$gte"] = datetime.fromisoformat(req.date_from)
    if req.date_to:
        date_filt["$lte"] = datetime.fromisoformat(req.date_to)
    if date_filt:
        filt["tested_at"] = date_filt

    cursor = (
        _db[COLLECTION]
        .find(filt, {"_id": 0})
        .sort("tested_at", -1)
        .limit(req.limit)
    )
    rows = [_serialize(doc) async for doc in cursor]
    return {"rows": rows, "count": len(rows)}


# ── Tool: summary stats (computed in Python from Mongo cursor) ────────────────

class SummaryRequest(BaseModel):
    material_name: str
    property_name: str
    group_by: Optional[str] = None   # "machine_id" | "site" | None


@app.post("/tools/summary_stats")
async def summary_stats(req: SummaryRequest):
    """
    Returns count, mean, std, min, max, p5, p95 for a property.
    Optional group_by splits results per machine or site.
    Uses MongoDB aggregation pipeline.
    """
    match = {
        "material_name": req.material_name,
        "property_name": req.property_name,
    }

    if req.group_by:
        group_id = f"${req.group_by}"
    else:
        group_id = "all"

    pipeline = [
        {"$match": match},
        {"$sort": {"value": 1}},
        {"$group": {
            "_id":   group_id,
            "n":     {"$sum": 1},
            "mean":  {"$avg": "$value"},
            "min":   {"$min": "$value"},
            "max":   {"$max": "$value"},
            "std":   {"$stdDevSamp": "$value"},
            "values": {"$push": "$value"},   # for percentile calc
        }},
        {"$sort": {"_id": 1}},
    ]

    results = []
    async for doc in _db[COLLECTION].aggregate(pipeline):
        vals = sorted(doc.pop("values", []))
        n = len(vals)

        def percentile(data, p):
            if not data: return None
            idx = (p / 100) * (len(data) - 1)
            lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
            return round(data[lo] + (data[hi] - data[lo]) * (idx - lo), 4)

        results.append({
            "group": doc["_id"],
            "n":     doc["n"],
            "mean":  round(doc["mean"], 4) if doc["mean"] is not None else None,
            "std":   round(doc["std"],  4) if doc["std"]  is not None else None,
            "min":   round(doc["min"],  4) if doc["min"]  is not None else None,
            "max":   round(doc["max"],  4) if doc["max"]  is not None else None,
            "p5":    percentile(vals, 5),
            "p95":   percentile(vals, 95),
        })

    return {"stats": results}


# ── Tool: fetch ordered time series ──────────────────────────────────────────

class SeriesRequest(BaseModel):
    material_name: str
    property_name: str
    machine_id:    Optional[str] = None
    date_from:     Optional[str] = None
    date_to:       Optional[str] = None


@app.post("/tools/get_series")
async def get_series(req: SeriesRequest):
    """Returns ordered (date, value) pairs — fed directly into the stats tool."""
    filt: dict = {
        "material_name": req.material_name,
        "property_name": req.property_name,
    }
    if req.machine_id:
        filt["machine_id"] = req.machine_id

    date_filt: dict = {}
    if req.date_from:
        date_filt["$gte"] = datetime.fromisoformat(req.date_from)
    if req.date_to:
        date_filt["$lte"] = datetime.fromisoformat(req.date_to)
    if date_filt:
        filt["tested_at"] = date_filt

    cursor = (
        _db[COLLECTION]
        .find(filt, {"_id": 0, "tested_at": 1, "value": 1})
        .sort("tested_at", 1)
    )

    dates, values = [], []
    async for doc in cursor:
        ts = doc.get("tested_at")
        dates.append(ts.isoformat() if isinstance(ts, datetime) else str(ts))
        values.append(float(doc["value"]))

    return {"dates": dates, "values": values}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        await _client.admin.command("ping")
        return {"status": "ok", "mongo": "reachable"}
    except Exception as e:
        return {"status": "degraded", "mongo": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("MCP_PORT", 8001)))
