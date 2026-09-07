from fastapi import APIRouter, HTTPException

from features.screener.service import get_regime, score_and_save_universe

router = APIRouter(prefix="/screener", tags=["Screener"])

@router.get("/regime")
async def fetch_regime():
    try:
        regime = await get_regime()
        # pop the pd.Series so we can return json
        if "nifty" in regime:
            del regime["nifty"]
        return regime
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run")
async def run_screener():
    try:
        top_10 = await score_and_save_universe()
        return {"status": "success", "results": top_10}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
