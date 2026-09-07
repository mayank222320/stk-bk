from typing import Any
from core.database import mongo
from core.retention import get_policy, SACRED

M0_LIMIT = 512 * 1024 * 1024

async def storage_stats() -> dict[str, Any]:
    if mongo.db is None:
        return {"error": "No DB connection"}
        
    db_stats = await mongo.db.command("dbStats")
    data_size = db_stats.get("dataSize", 0)
    
    collection_stats = {}
    collections = await mongo.db.list_collection_names()
    policy = await get_policy()
    
    for coll in collections:
        coll_stat = await mongo.db.command("collStats", coll)
        collection_stats[coll] = {
            "size": coll_stat.get("size", 0),
            "count": coll_stat.get("count", 0),
            "retention_days": policy.get(coll, "SACRED" if coll in SACRED else "unmanaged"),
            "is_sacred": coll in SACRED
        }
        
    return {
        "db_size": data_size,
        "m0_limit": M0_LIMIT,
        "usage_percent": (data_size / M0_LIMIT) * 100 if M0_LIMIT > 0 else 0,
        "collections": collection_stats
    }
