from fastapi import APIRouter
from features.news_scanner.service import run_news_scanner, get_news_alerts

router = APIRouter(prefix="/news-scanner", tags=["News Scanner"])


@router.post("/trigger")
async def trigger_scan():
    """Manually trigger the news scanner (for testing)."""
    await run_news_scanner()
    return {"status": "scan complete"}


@router.get("/alerts")
async def list_alerts(limit: int = 20):
    """Return recent breaking news alerts for the dashboard."""
    return await get_news_alerts(limit=limit)

import asyncio
from core.timeutils import fmt_ist
from core.database import mongo

_MEM_CACHE = {}

def _source_status(rss, filings, gnews):
    return {
        "rss": "ok" if not isinstance(rss, Exception) else "error",
        "filings": "ok" if not isinstance(filings, Exception) else "error",
        "gnews": "ok" if not isinstance(gnews, Exception) else "error",
    }

def _age_min(ts):
    import time
    return int((time.time() - ts) / 60)

async def _was_alerted(url: str) -> bool:
    if mongo.db is None: return False
    return await mongo.db.news_alerts.count_documents({"url": url}) > 0

def _merge_dedupe(rss, filings, gnews):
    merged = []
    seen = set()
    for source_list in (rss, filings, gnews):
        if isinstance(source_list, list):
            for it in source_list:
                # normalize object/dict
                item = it if isinstance(it, dict) else {
                    "title": getattr(it, "title", ""),
                    "url": getattr(it, "url", ""),
                    "source": getattr(it, "source", "unknown"),
                    "published_ts": getattr(it, "published_ts", 0),
                    "symbol": getattr(it, "symbol", None)
                }
                key = item.get("title", "").lower()
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
    return merged

@router.get("/latest")
async def latest_news(symbol: str | None = None, limit: int = 30, force: bool = True):
    import time
    cache_key = f"latest_{symbol}"
    if cache_key in _MEM_CACHE:
        cached_time, data = _MEM_CACHE[cache_key]
        if time.time() - cached_time < 60:
            return {**data, "cached": True}

    from features.news_scanner.fast_lane import watched_symbols, fetch_filings
    from adapters.news.gnews import fetch_google_news
    from features.market_data.news_fetcher import fetch_all_news

    watched = [symbol.upper()] if symbol else await watched_symbols()

    rss, filings, gnews = await asyncio.gather(
        fetch_all_news(limit=60),
        fetch_filings(watched),
        fetch_google_news(watched, window="1h"),
        return_exceptions=True,
    )

    items = _merge_dedupe(rss, filings, gnews)
    for it in items:
        it["age_minutes"] = _age_min(it["published_ts"])
        it["watched"] = it.get("symbol") in watched
        it["already_alerted"] = await _was_alerted(it["url"])
        
    items.sort(key=lambda i: (not i["watched"], -i.get("published_ts", 0)))

    payload = {
        "as_of": fmt_ist(), 
        "session": "unknown",
        "count": len(items), 
        "items": items[:limit],
        "sources": _source_status(rss, filings, gnews),
        "cached": False
    }
    _MEM_CACHE[cache_key] = (time.time(), payload)
    return payload
