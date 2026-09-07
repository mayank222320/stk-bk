"""
Market data adapter protocol.
Defines the standard asynchronous interface for market data providers (yfinance, NSE, broker).
"""
from typing import Protocol, runtime_checkable

import pandas as pd

from core.freshness import Stamped


@runtime_checkable
class MarketData(Protocol):
    """Asynchronous protocol for fetching quotes and OHLCV history."""

    async def get_quote(self, symbol: str) -> Stamped:
        """Fetch current quote / live price info for a symbol."""
        ...

    async def get_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch OHLCV historical dataframe for a symbol."""
        ...
