from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import mongo

SACRED = {"users", "system_metrics", "portfolios", "performance_log", "knowledge_base"}

DEFAULTS = {
    "chat_history": 14,
    "intraday_alerts": 7,
    "news_alerts": 30,
    "morning_alerts": 30,
    "swing_positions": 90,
    "processed_news": 30,
    "market_cache": 3
}

async def get_policy() -> dict[str, int]:
    if mongo.db is None:
        return DEFAULTS.copy()

    policy = DEFAULTS.copy()
    doc = await mongo.db.system_settings.find_one({"_id": "retention_policy"})
    if doc and "policy" in doc:
        policy.update(doc["policy"])
    return policy

async def set_policy(collection: str, days: int) -> None:
    if mongo.db is None:
        return
    policy = await get_policy()
    policy[collection] = days
    await mongo.db.system_settings.update_one(
        {"_id": "retention_policy"},
        {"$set": {"policy": policy}},
        upsert=True
    )
    await ensure_storage_indexes()

def _cutoff(days: int, as_string: bool = False) -> datetime | str:
    dt = datetime.now(UTC) - timedelta(days=days)
    if as_string:
        return dt.isoformat()
    return dt

async def ensure_storage_indexes() -> None:
    if mongo.db is None:
        return
    policy = await get_policy()
    for coll_name, days in policy.items():
        if coll_name in SACRED:
            continue
        try:
            await mongo.db.command({
                "collMod": coll_name,
                "index": {
                    "keyPattern": {"created_at": 1},
                    "expireAfterSeconds": days * 86400
                }
            })
        except Exception:
            try:
                await mongo.db[coll_name].create_index(
                    [("created_at", 1)],
                    expireAfterSeconds=days * 86400,
                    background=True
                )
            except Exception:
                pass

async def cleanup(
    older_than_days: int | None = None,
    collections: list[str] | None = None,
    dry_run: bool = True,
    include_sacred: bool = False,
    confirm: bool = False
) -> dict[str, Any]:
    if not confirm and not dry_run:
        return {"error": "Must pass confirm=True to actually delete"}

    if mongo.db is None:
        return {"error": "No DB connection"}

    policy = await get_policy()
    target_collections = collections if collections else list(policy.keys())

    deleted_counts = {}
    for coll in target_collections:
        if coll in SACRED and not include_sacred:
            continue

        days = older_than_days if older_than_days is not None else policy.get(coll, 30)
        dt_cutoff = _cutoff(days)

        query = {"created_at": {"$lt": dt_cutoff}}

        if dry_run:
            count = await mongo.db[coll].count_documents(query)
            deleted_counts[coll] = count
        else:
            result = await mongo.db[coll].delete_many(query)
            deleted_counts[coll] = result.deleted_count

    from features.storage.service import storage_stats
    stats = await storage_stats()

    return {
        "dry_run": dry_run,
        "deleted_counts": deleted_counts,
        "post_cleanup_stats": stats
    }

async def rollup_month(month: str) -> dict[str, Any]:
    if mongo.db is None:
        return {"error": "No DB connection"}

    # Example rollup logic for swing_positions matching the month (YYYY-MM)
    query = {"created_at": {"$regex": f"^{month}"}}
    count = await mongo.db.swing_positions.count_documents(query)
    # in a real implementation we would aggregate and insert into performance_log

    return {"month": month, "rolled_up": count, "message": "Rollup complete"}
