"""
Database MCP server.

Exposes the txp MongoDB as HTTP tools the agent can call.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

app = FastAPI(title="MatAI MCP Server (MongoDB)", version="0.2.0")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://host.docker.internal:27017")
MONGO_DB = os.environ.get("MONGO_DB", "txp")
COLLECTION = "test_results"

_client: AsyncIOMotorClient | None = None
_db = None


@app.on_event("startup")
async def startup():
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    _db = _client[MONGO_DB]

    col = _db[COLLECTION]
    await col.create_index([("material_name", 1), ("property_name", 1)])
    await col.create_index([("tested_at", 1)])


@app.on_event("shutdown")
async def shutdown():
    if _client is not None:
        _client.close()


def _serialize(doc: dict) -> dict:
    out = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    return out


@app.get("/tools/list_materials")
async def list_materials():
    names = await _db[COLLECTION].distinct("material_name")
    return {"materials": sorted(names)}


@app.get("/tools/describe_db")
async def describe_db():
    collections = await _db.list_collection_names()
    result = {}
    for collection in collections:
        sample = await _db[collection].find_one({}, {"_id": 0})
        result[collection] = {
            "fields": list(sample.keys()) if sample else [],
            "sample": _serialize(sample) if sample else {},
        }
    return result


class QueryTestsRequest(BaseModel):
    material_name: Optional[str] = None
    machine_id: Optional[str] = None
    site: Optional[str] = None
    property_name: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 500


@app.post("/tools/query_tests")
async def query_tests(req: QueryTestsRequest):
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


class SummaryRequest(BaseModel):
    material_name: str
    property_name: str
    group_by: Optional[str] = None


@app.post("/tools/summary_stats")
async def summary_stats(req: SummaryRequest):
    match = {
        "material_name": req.material_name,
        "property_name": req.property_name,
    }

    group_id = f"${req.group_by}" if req.group_by else "all"

    pipeline = [
        {"$match": match},
        {"$sort": {"value": 1}},
        {
            "$group": {
                "_id": group_id,
                "n": {"$sum": 1},
                "mean": {"$avg": "$value"},
                "min": {"$min": "$value"},
                "max": {"$max": "$value"},
                "std": {"$stdDevSamp": "$value"},
                "values": {"$push": "$value"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    results = []
    async for doc in _db[COLLECTION].aggregate(pipeline):
        values = sorted(doc.pop("values", []))

        def percentile(data: list[float], p: int):
            if not data:
                return None
            idx = (p / 100) * (len(data) - 1)
            low = int(idx)
            high = min(low + 1, len(data) - 1)
            return round(data[low] + (data[high] - data[low]) * (idx - low), 4)

        results.append(
            {
                "group": doc["_id"],
                "n": doc["n"],
                "mean": round(doc["mean"], 4) if doc["mean"] is not None else None,
                "std": round(doc["std"], 4) if doc["std"] is not None else None,
                "min": round(doc["min"], 4) if doc["min"] is not None else None,
                "max": round(doc["max"], 4) if doc["max"] is not None else None,
                "p5": percentile(values, 5),
                "p95": percentile(values, 95),
            }
        )

    return {"stats": results}


class SeriesRequest(BaseModel):
    material_name: str
    property_name: str
    machine_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@app.post("/tools/get_series")
async def get_series(req: SeriesRequest):
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
        timestamp = doc.get("tested_at")
        dates.append(timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp))
        values.append(float(doc["value"]))

    return {"dates": dates, "values": values}


@app.get("/health")
async def health():
    try:
        await _client.admin.command("ping")
        return {"status": "ok", "mongo": "reachable"}
    except Exception as exc:
        return {"status": "degraded", "mongo": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("MCP_PORT", 8001)))
