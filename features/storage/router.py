from fastapi import APIRouter, HTTPException
from typing import Any
from pydantic import BaseModel
from features.storage.service import storage_stats
from core.retention import get_policy, set_policy, cleanup, rollup_month, DEFAULTS, SACRED
from core.database import mongo

router = APIRouter(prefix="/storage", tags=["storage"])

class RetentionPolicyUpdate(BaseModel):
    collection: str
    days: int

class CleanupRequest(BaseModel):
    older_than_days: int | None = None
    collections: list[str] | None = None
    dry_run: bool = True
    include_sacred: bool = False
    confirm: bool = False

class RollupRequest(BaseModel):
    month: str

@router.get("/stats")
async def get_storage_stats() -> dict[str, Any]:
    return await storage_stats()

@router.get("/retention")
async def get_retention_policy() -> dict[str, Any]:
    return await get_policy()

@router.put("/retention")
async def update_retention_policy(req: RetentionPolicyUpdate) -> dict[str, Any]:
    await set_policy(req.collection, req.days)
    return {"message": f"Updated retention for {req.collection} to {req.days} days"}

@router.post("/cleanup")
async def run_cleanup(req: CleanupRequest) -> dict[str, Any]:
    return await cleanup(
        older_than_days=req.older_than_days,
        collections=req.collections,
        dry_run=req.dry_run,
        include_sacred=req.include_sacred,
        confirm=req.confirm
    )

@router.post("/rollup")
async def run_rollup(req: RollupRequest) -> dict[str, Any]:
    return await rollup_month(req.month)

@router.delete("/collection/{name}")
async def drop_collection(name: str) -> dict[str, Any]:
    if name not in DEFAULTS or name in SACRED:
        raise HTTPException(status_code=400, detail="Cannot drop this collection. Must be rolling and not sacred.")
    if mongo.db is not None:
        await mongo.db[name].drop()
    return {"message": f"Collection {name} dropped"}
