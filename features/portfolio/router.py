from fastapi import APIRouter
from features.portfolio.service import get_positions, delete_position, clear_all_positions, close_position

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

@router.get("/positions")
async def positions():
    return await get_positions()

from core.retention import cleanup

@router.delete("/positions/all")
async def clear_all():
    return await cleanup(dry_run=True)

@router.post("/positions/{position_id}/close")
async def close_pos(position_id: str):
    success = await close_position(position_id)
    return {"status": "success" if success else "failed"}

@router.delete("/positions/{position_id}")
async def delete_pos(position_id: str):
    success = await delete_position(position_id)
    return {"status": "success" if success else "failed"}
