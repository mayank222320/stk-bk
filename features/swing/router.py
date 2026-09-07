from fastapi import APIRouter, Query, HTTPException, Path, Body
from typing import List, Optional, Any
from pydantic import BaseModel

from features.swing import service
from features.swing.models import SwingPositionCreate

router = APIRouter(prefix="/swing", tags=["Swing"])

@router.get("/positions")
async def get_positions(status: Optional[str] = None):
    return await service.get_positions(status)

@router.get("/positions/{id}")
async def get_position(id: str):
    pos = await service.get_position(id)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return pos

@router.post("/positions/manual")
async def create_manual_position(pos: SwingPositionCreate):
    return await service.create_manual_position(
        symbol=pos.symbol,
        entry_low=pos.entry_zone_low,
        entry_high=pos.entry_zone_high,
        t1=pos.t1,
        stop_loss=pos.stop_loss,
        t2=pos.t2,
        t3=pos.t3,
        qty=pos.qty,
        notes=pos.notes
    )

class ClosePositionRequest(BaseModel):
    close_price: float
    reason: str = "MANUAL"

@router.post("/positions/{id}/close")
async def close_position_manually(id: str, req: ClosePositionRequest):
    result = await service.close_position_manually(id, req.close_price, req.reason)
    if not result:
        raise HTTPException(status_code=404, detail="Position not found")
    return result

@router.delete("/positions/{id}")
async def delete_position(id: str):
    success = await service.delete_position(id)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found or could not be deleted")
    return {"success": True}

@router.get("/performance")
async def performance(days: int = 90):
    return await service.performance(days)

@router.post("/tracker/run")
async def run_tracker():
    events = await service.track_positions()
    return {"events": events}
