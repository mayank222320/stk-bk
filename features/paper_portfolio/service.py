import math
from typing import Optional, List, Dict, Any
from core.database import mongo
from core.timeutils import today_ist
from features.swing.service import (
    ensure_indexes as _swing_ensure_indexes,
    track_positions as _swing_track_positions,
    get_positions as _swing_get_positions,
    performance as _swing_performance,
    delete_position as _swing_delete_position,
    _create,
    _slim
)

PAPER_COLLECTION = "paper_positions"

async def ensure_indexes() -> None:
    await _swing_ensure_indexes(coll_name=PAPER_COLLECTION)

async def log_paper_trade(reco: dict, snapshot: dict, capital: float = 500000.0) -> str | None:
    """Create a PENDING_ENTRY paper position from a BUY/ACCUMULATE reco.
    ATR-based sizing: risk 1% of capital, qty = floor(risk_amount / (entry - stop_loss)).
    Entry zone from reco['levels']['entry_low'] and reco['levels']['entry_high'].
    Stop from reco['levels']['stop_loss'], t1/t2/t3 from reco['levels'].
    If levels are missing, fall back to entry_price=snapshot.get('cmp'), stop=entry*0.97, t1=entry*1.06.
    Returns inserted _id as str, or None if not BUY/ACCUMULATE.
    """
    if mongo.db is None:
        return None
        
    rec = reco.get("recommendation")
    if rec not in ("BUY", "ACCUMULATE"):
        return None

    levels = reco.get("levels", {})
    entry_low = levels.get("entry_low")
    entry_high = levels.get("entry_high")
    stop_loss = levels.get("stop_loss")
    t1 = levels.get("target1")
    t2 = levels.get("target2", 0)
    t3 = levels.get("target3", 0)

    cmp_price = snapshot.get("cmp", 0)

    # Fallback levels
    if not entry_low or not entry_high:
        entry_low = cmp_price * 0.99
        entry_high = cmp_price * 1.01
    if not stop_loss:
        stop_loss = cmp_price * 0.97
    if not t1:
        t1 = cmp_price * 1.06

    # ATR-based sizing: 1% risk
    risk_amount = capital * 0.01
    entry_mid = (entry_low + entry_high) / 2
    per_share_risk = entry_mid - stop_loss

    qty = 0
    if per_share_risk > 0:
        qty = math.floor(risk_amount / per_share_risk)

    doc = await _create(
        source="AI_PAPER",
        symbol=reco.get("symbol", ""),
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        t1=t1,
        t2=t2,
        t3=t3,
        stop_loss=stop_loss,
        setup_type=reco.get("setup", "UNKNOWN"),
        thesis=reco.get("thesis", ""),
        qty=qty,
        entry_snapshot=_slim(snapshot),
        coll_name=PAPER_COLLECTION
    )
    return str(doc.get("_id")) if doc else None

async def track_paper_positions() -> list[tuple]:
    """Mirror of swing service track_positions() but on paper_positions.
    Run at 15:45 IST. Returns list of events.
    """
    return await _swing_track_positions(coll_name=PAPER_COLLECTION)

async def get_paper_positions(status_filter: str | None = None) -> list[dict]:
    return await _swing_get_positions(status_filter, coll_name=PAPER_COLLECTION)

async def get_paper_performance(last_n_days: int = 90) -> dict:
    """Same expectancy stats as swing performance() but on paper trades.
    Include 'vs_real' comparison: paper expectancy vs real swing expectancy (call swing service.performance()).
    """
    paper_perf = await _swing_performance(last_n_days, coll_name=PAPER_COLLECTION)
    real_perf = await _swing_performance(last_n_days, coll_name="swing_positions")
    
    paper_perf["vs_real"] = {
        "paper_expectancy_r": paper_perf.get("expectancy_r", 0),
        "real_expectancy_r": real_perf.get("expectancy_r", 0),
        "paper_win_rate": paper_perf.get("win_rate_pct", 0),
        "real_win_rate": real_perf.get("win_rate_pct", 0),
        "paper_trades": paper_perf.get("trades", 0),
        "real_trades": real_perf.get("trades", 0),
    }
    return paper_perf

async def delete_paper_position(position_id: str) -> bool:
    return await _swing_delete_position(position_id, coll_name=PAPER_COLLECTION)

async def clear_paper_positions() -> int:
    if mongo.db is None:
        return 0
    res = await mongo.db[PAPER_COLLECTION].delete_many({})
    return res.deleted_count
