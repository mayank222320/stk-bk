from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from features.risk.service import size_position, portfolio_heat

router = APIRouter(prefix="/risk", tags=["Risk Engine"])

class SizeRequest(BaseModel):
    entry: float
    stop: float

@router.post("/size")
async def api_size_position(req: SizeRequest):
    try:
        return await size_position(req.entry, req.stop)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/heat")
async def api_portfolio_heat():
    return await portfolio_heat()
