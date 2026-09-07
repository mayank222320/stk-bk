"""
yfinance market data adapter.
Runs all blocking yfinance I/O inside a dedicated ThreadPoolExecutor with strict timeouts.
Never blocks the asyncio event loop.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import pandas as pd
import yfinance as yf

from core.errors import DataUnavailable
from core.freshness import Stamped
from core.logging import log
from core.timeutils import now_ist

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yf_market")
_TIMEOUT_SECONDS = 12.0


def _sync_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Synchronous yfinance history call with fallback for NSE/BSE symbols."""
    clean_sym = symbol.strip().upper()
    candidates = (
        [clean_sym]
        if clean_sym.endswith(".NS") or clean_sym.endswith(".BO")
        else [f"{clean_sym}.NS", f"{clean_sym}.BO"]
    )
    for s in candidates:
        try:
            ticker = yf.Ticker(s)
            df = ticker.history(period=period, interval=interval)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            log.debug(f"[yfinance] Failed fetching {s}: {e}")
    return pd.DataFrame()


def _sync_quote(symbol: str) -> dict[str, Any]:
    """Synchronous yfinance quote call using latest 1m bar or fast_info."""
    clean_sym = symbol.strip().upper()
    candidates = (
        [clean_sym]
        if clean_sym.endswith(".NS") or clean_sym.endswith(".BO")
        else [f"{clean_sym}.NS", f"{clean_sym}.BO"]
    )
    for s in candidates:
        try:
            ticker = yf.Ticker(s)
            # Try 1m bar for live intraday close
            hist = ticker.history(period="1d", interval="1m")
            if hist is not None and not hist.empty:
                last_row = hist.iloc[-1]
                close_price = float(last_row["Close"])
                return {
                    "symbol": clean_sym,
                    "ticker": s,
                    "price": close_price,
                    "open": float(hist["Open"].iloc[0]),
                    "high": float(hist["High"].max()),
                    "low": float(hist["Low"].min()),
                    "volume": int(hist["Volume"].sum()),
                }
            # Fallback to fast_info
            price = getattr(ticker.fast_info, "last_price", None)
            if price is not None:
                return {
                    "symbol": clean_sym,
                    "ticker": s,
                    "price": float(price),
                }
        except Exception as e:
            log.debug(f"[yfinance] Quote error for {s}: {e}")
    return {}


class YFinanceAdapter:
    """Thread-pooled async adapter for yfinance."""

    async def _run(self, fn, *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        call = partial(fn, *args, **kwargs)
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_POOL, call),
                timeout=_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise DataUnavailable("yfinance", f"Timeout after {_TIMEOUT_SECONDS}s") from exc
        except Exception as exc:
            raise DataUnavailable("yfinance", str(exc)) from exc

    async def get_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch OHLCV dataframe asynchronously."""
        return await self._run(_sync_history, symbol, period, interval)

    async def get_quote(self, symbol: str) -> Stamped:
        """Fetch quote information asynchronously."""
        data = await self._run(_sync_quote, symbol)
        return Stamped(
            value=data if data else None,
            source="yfinance",
            captured_at=now_ist(),
            kind="quote"
        )


yfinance_adapter = YFinanceAdapter()
