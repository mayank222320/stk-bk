from fastapi import APIRouter
from typing import List, Dict, Any, Optional

from features.paper_portfolio.service import (
    get_paper_positions,
    get_paper_performance,
    track_paper_positions,
    delete_paper_position,
    clear_paper_positions
)
from core.database import mongo

router = APIRouter(prefix="/paper", tags=["Paper Portfolio"])

@router.get("/positions")
async def api_get_paper_positions(status: Optional[str] = None):
    return await get_paper_positions(status)

@router.get("/performance")
async def api_get_paper_performance(days: int = 90):
    return await get_paper_performance(days)

@router.post("/tracker/run")
async def api_track_paper_positions():
    events = await track_paper_positions()
    return {"status": "success", "events": events}

@router.delete("/positions/all")
async def api_clear_paper_positions():
    count = await clear_paper_positions()
    return {"status": "success", "deleted_count": count}

@router.delete("/positions/{id}")
async def api_delete_paper_position(id: str):
    success = await delete_paper_position(id)
    return {"status": "success", "deleted": success}

@router.post("/migrate-legacy")
async def api_migrate_legacy():
    if mongo.db is None:
        return {"status": "error", "message": "DB not connected"}
    
    # Simple migration of virtual_portfolio to paper_positions
    cursor = mongo.db.virtual_portfolio.find({})
    legacy_docs = await cursor.to_list(length=None)
    
    migrated = 0
    for doc in legacy_docs:
        # Check if already migrated
        if await mongo.db.paper_positions.find_one({"legacy_id": str(doc["_id"])}):
            continue
            
        pnl_pct = doc.get("pnl_pct", 0)
        # rough estimate of r_multiple based on 3% stop loss assumption if not provided
        r_multiple = pnl_pct / 3.0
        
        new_doc = {
            "symbol": doc.get("symbol", "UNKNOWN"),
            "source": "AI_LEGACY",
            "setup_type": "LEGACY",
            "status": "CLOSED",
            "entry_zone_low": doc.get("entry_price", 0),
            "entry_zone_high": doc.get("entry_price", 0),
            "fill_price": doc.get("entry_price", 0),
            "t1": doc.get("target", 0),
            "t2": 0,
            "t3": 0,
            "stop_loss": doc.get("stop_loss", 0),
            "trailing_stop": doc.get("stop_loss", 0),
            "qty": int(20000 / (doc.get("entry_price") or 1)), # Hardcoded 20k legacy size
            "r_multiple": r_multiple,
            "days_held": 0, # unknown
            "open_date": doc.get("date", ""),
            "fill_date": doc.get("date", ""),
            "close_date": doc.get("close_date", ""),
            "thesis": "Migrated from legacy virtual_portfolio",
            "daily": [],
            "legacy_id": str(doc["_id"])
        }
        await mongo.db.paper_positions.insert_one(new_doc)
        migrated += 1
        
    return {"status": "success", "migrated_count": migrated}
