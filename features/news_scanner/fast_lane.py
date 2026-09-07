import asyncio
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError

from core.database import mongo
from core.timeutils import now_ist, fmt_ist
from adapters.news.filings import fetch_bse_announcements
from features.notifications.service import broadcast
from features.bot.setup import bot
from core.config import USER_ID
from core.logging import log

HIGH_IMPACT = {"award of order", "financial results", "acquisition", "amalgamation",
               "credit rating", "board meeting", "dividend", "buy back",
               "resignation", "fund raising", "investor presentation", "open offer"}

async def watched_symbols() -> list[str]:
    """Fetch held positions and today's shortlist."""
    if mongo.db is None:
        return []
    
    positions = await mongo.db.swing_positions.find({"status": "OPEN"}, {"symbol": 1}).to_list(None)
    
    # Mocking today's shortlist fetch to keep it simple, or query it:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    shortlist = await mongo.db.screener_shortlist.find({"date": today_str}, {"symbol": 1}).to_list(None)
    
    symbols = {p["symbol"] for p in positions} | {s["symbol"] for s in shortlist}
    return list(symbols)

def _fmt(filing: dict) -> str:
    return f"{filing.get('subject', '')} - {filing.get('link', '')}"

async def poll_filings() -> list[dict]:
    """Every 60-90s during market hours. Only alerts on watched symbols."""
    watched = await watched_symbols()
    hits = []
    for filing in await fetch_bse_announcements():
        if filing["symbol"] not in watched:
            continue
        if not any(k in filing["category"].lower() for k in HIGH_IMPACT):
            continue
        
        try:
            if mongo.db is not None:
                await mongo.db.filings_seen.insert_one({
                    "filing_id": filing["id"], 
                    "at": now_ist()
                })
        except DuplicateKeyError:
            continue
            
        # Send alert
        msg = f"📄 {filing['symbol']} — {filing['category']}\n{_fmt(filing)}"
        if USER_ID:
            try:
                await bot.send_message(chat_id=int(USER_ID), text=msg)
            except Exception as e:
                log.error(f"Telegram send failed: {e}")
                
        await broadcast(title=f"EXCHANGE_FILING P1: {filing['symbol']}", text=msg, ntfy_priority="max")
        
        hits.append(filing)
    return hits

async def fetch_filings(symbols: list[str]) -> list[dict]:
    # Wrapper for manual route
    all_filings = await fetch_bse_announcements()
    return [f for f in all_filings if f["symbol"] in symbols]

