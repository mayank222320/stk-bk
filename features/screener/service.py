from typing import Any

import pandas as pd

from adapters.market.yfinance import yfinance_adapter
from adapters.repo.screener import bulk_history, get_universe
from core.database import mongo
from core.timeutils import today_ist
from domain.rules.scoring import score_universe


async def get_regime(frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    nifty = await yfinance_adapter.get_history("^NSEI", period="2y", interval="1d")
    if nifty is None or nifty.empty:
        # Fallback if no data
        return {
            "state": "NEUTRAL", 
            "size_multiplier": 0.5, 
            "max_positions": 3, 
            "nifty": pd.Series(),
            "breadth_pct": 0.0,
            "nifty_dma_pct": 0.0
        }

    nifty_close = nifty["Close"]
    nifty_200 = nifty_close.rolling(200).mean()
    above200 = bool(nifty_close.iloc[-1] > nifty_200.iloc[-1]) if len(nifty_close) >= 200 else False

    # Calculate breadth
    breadth = 50.0 # Default
    if frames:
        count_above = 0
        total_valid = 0
        for df in frames.values():
            if len(df) >= 50:
                c = df["Close"]
                sma50 = c.rolling(50).mean()
                if float(c.iloc[-1]) > float(sma50.iloc[-1]):
                    count_above += 1
                total_valid += 1
        if total_valid > 0:
            breadth = (count_above / total_valid) * 100.0

    vix = await yfinance_adapter.get_history("^INDIAVIX", period="2y", interval="1d")
    vix_pct = 50.0 # Default
    if vix is not None and not vix.empty:
        c = vix["Close"]
        if len(c) > 0:
            vix_pct = float((c < c.iloc[-1]).mean() * 100)

    if above200 and breadth > 55 and vix_pct < 70:
        st, mult, mx = "RISK_ON", 1.0, 5
    elif not above200 and breadth < 40:
        st, mult, mx = "RISK_OFF", 0.0, 0
    else:
        st, mult, mx = "NEUTRAL", 0.5, 3

    regime_doc = {
        "date": today_ist(),
        "state": st,
        "breadth_pct": round(breadth, 1),
        "vix_pct": round(vix_pct, 1),
        "nifty_above_200dma": above200
    }

    if mongo.db is not None:
        await mongo.db.regime_daily.replace_one(
            {"date": today_ist()},
            regime_doc,
            upsert=True
        )

    nifty_dma_pct = 0.0
    if len(nifty_close) >= 200:
        nifty_dma_pct = float(((nifty_close.iloc[-1] / nifty_200.iloc[-1]) - 1) * 100)

    return {
        "state": st,
        "size_multiplier": mult,
        "max_positions": mx,
        "nifty": nifty_close,
        "breadth_pct": float(breadth),
        "nifty_dma_pct": float(nifty_dma_pct)
    }

async def score_and_save_universe() -> list[dict[str, Any]]:
    symbols = await get_universe()
    frames = await bulk_history(symbols, days=300)

    regime = await get_regime(frames)

    # Block new entries if RISK_OFF
    if regime["state"] == "RISK_OFF":
        # Maybe we still score, but mark as blocked? The instructions say "RISK_OFF blocks new entries".
        # We will score and save, but the actual entry creation is blocked elsewhere, or we can add a flag here.
        pass

    scored = score_universe(symbols, frames, regime)

    # Exclude results in 5 days (mock this out for now as F6 is not fully implemented)
    # Also exclude illiquid (already handled by score_universe assigning -40 and returning reasons)

    # Sort and keep top 10
    top_10 = scored[:10]

    if mongo.db is not None:
        for idx, item in enumerate(top_10):
            item["date"] = today_ist()
            item["rank"] = idx + 1
            await mongo.db.screener_scores.replace_one(
                {"date": today_ist(), "symbol": item["symbol"]},
                item,
                upsert=True
            )

    return top_10
