from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from features.investments.service import (
    add_sip_transaction,
    delete_sip_transaction,
    get_etf_dip_status,
    get_sip_xirr,
    list_sip_transactions,
)

router = APIRouter(prefix="/investments", tags=["Investments"])


# ─── Pydantic Models ─────────────────────────────────────────────────────────

class CashflowItem(BaseModel):
    date: date
    amount: float


class XirrRequest(BaseModel):
    code: int
    flows: list[CashflowItem]


class SIPTransactionIn(BaseModel):
    code: int = Field(..., gt=0, description="MFAPI fund scheme code")
    date: str = Field(..., description="Purchase date in YYYY-MM-DD format")
    amount: float = Field(..., gt=0, description="Amount invested (positive rupees)")
    note: str | None = Field(None, description="Optional free-text note")


class DipRequest(BaseModel):
    symbol: str
    budget: float
    is_month_end: bool = False


# ─── MF SIP Endpoints ────────────────────────────────────────────────────────

@router.get("/mf/xirr")
async def get_mf_xirr_status() -> dict:
    """Return XIRR snapshot for the full SIP portfolio stored in MongoDB."""
    return await get_sip_xirr()


@router.post("/mf/xirr")
async def calculate_xirr(req: XirrRequest) -> dict:
    """Ad-hoc XIRR calculation for a manually supplied fund code and cashflows."""
    flows = [(item.date, item.amount) for item in req.flows]
    return await get_sip_xirr(req.code, flows)


@router.get("/mf/portfolio")
async def get_portfolio() -> list[dict]:
    """Return all SIP transactions from MongoDB sorted by date descending."""
    return await list_sip_transactions()


@router.post("/mf/portfolio", status_code=201)
async def add_transaction(txn: SIPTransactionIn) -> dict:
    """Insert a new SIP transaction record."""
    result = await add_sip_transaction(txn.code, txn.date, txn.amount, txn.note)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.delete("/mf/portfolio/{transaction_id}")
async def remove_transaction(transaction_id: str) -> dict:
    """Delete a SIP transaction by its MongoDB ObjectId."""
    result = await delete_sip_transaction(transaction_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return result


# ─── ETF Dip Endpoints (unchanged) ───────────────────────────────────────────

@router.post("/etf/dip")
async def get_dip(req: DipRequest) -> dict:
    return await get_etf_dip_status(req.symbol, req.budget, req.is_month_end)


@router.get("/etf/dips")
async def get_etf_dips_status() -> dict:
    """Return the current ETF dip status for GOLDBEES and MON100."""
    return await get_etf_dip_status()
