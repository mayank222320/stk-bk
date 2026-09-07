"""
NSE direct / nsepython market data adapter.
Executes blocking requests inside a threadpool executor with timeouts.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import pandas as pd
import requests

from core.errors import DataUnavailable
from core.freshness import Stamped
from core.logging import log
from core.timeutils import now_ist

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="nse_market")
_TIMEOUT_SECONDS = 10.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


def _sync_nse_quote(symbol: str) -> dict[str, Any]:
    """Fetch live quote from NSE quote API using session cookie warm-up."""
    clean_sym = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=_HEADERS, timeout=5)
        url = f"https://www.nseindia.com/api/quote-equity?symbol={clean_sym}"
        resp = session.get(url, headers=_HEADERS, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            price_info = data.get("priceInfo", {})
            last_price = price_info.get("lastPrice")
            if last_price:
                return {
                    "symbol": clean_sym,
                    "price": float(last_price),
                    "open": float(price_info.get("open", 0)),
                    "high": float(price_info.get("intraDayHighLow", {}).get("max", 0)),
                    "low": float(price_info.get("intraDayHighLow", {}).get("min", 0)),
                    "close": float(price_info.get("close", 0)),
                }
    except Exception as e:
        log.debug(f"[NSE] Failed fetching quote for {clean_sym}: {e}")
    return {}


class NSEAdapter:
    """Thread-pooled async adapter for NSE direct API."""

    async def _run(self, fn, *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        call = partial(fn, *args, **kwargs)
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_POOL, call),
                timeout=_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise DataUnavailable("NSE", f"Timeout after {_TIMEOUT_SECONDS}s") from exc
        except Exception as exc:
            raise DataUnavailable("NSE", str(exc)) from exc

    async def get_quote(self, symbol: str) -> Stamped:
        """Fetch quote information asynchronously."""
        data = await self._run(_sync_nse_quote, symbol)
        return Stamped(
            value=data if data else None,
            source="nse",
            captured_at=now_ist(),
            kind="quote"
        )

    async def get_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """NSE direct does not provide simple OHLCV bulk history without scraping; returns empty."""
        return pd.DataFrame()


nse_adapter = NSEAdapter()
