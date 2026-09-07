import asyncio
import io
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pandas as pd
import requests
import yfinance as yf

from core.logging import log

# Cache file for universe
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
UNIVERSE_CACHE = os.path.join(DATA_DIR, "nifty500_universe.csv")
UNIVERSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="screener_yf")

def _fetch_universe_sync() -> list[str]:
    # Check cache first
    import time
    if os.path.exists(UNIVERSE_CACHE):
        if time.time() - os.path.getmtime(UNIVERSE_CACHE) < 7 * 86400: # 7 days
            try:
                df = pd.read_csv(UNIVERSE_CACHE)
                return df["Symbol"].tolist()
            except Exception as e:
                log.warning(f"Failed to read universe cache: {e}")

    # Fetch from NSE
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/csv",
        "Referer": "https://www.nseindia.com",
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(UNIVERSE_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        with open(UNIVERSE_CACHE, "wb") as f:
            f.write(resp.content)
        df = pd.read_csv(io.StringIO(resp.content.decode("utf-8")))
        return df["Symbol"].tolist()
    except Exception as e:
        log.error(f"Failed to fetch Nifty 500 universe: {e}")
        # Return fallback if cache exists but is stale
        if os.path.exists(UNIVERSE_CACHE):
            try:
                df = pd.read_csv(UNIVERSE_CACHE)
                return df["Symbol"].tolist()
            except Exception:
                pass
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

async def get_universe() -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_universe_sync)

def _download_chunk(symbols: list[str], days: int) -> pd.DataFrame:
    # Append .NS for yfinance
    yf_symbols = [f"{s}.NS" for s in symbols]
    period = f"{days}d"
    # Using threads=False prevents massive RAM spikes on Free Tier
    df = yf.download(yf_symbols, period=period, group_by="ticker", auto_adjust=True, threads=False, progress=False)
    return df

async def bulk_history(symbols: list[str], days: int = 300) -> dict[str, pd.DataFrame]:
    loop = asyncio.get_running_loop()
    frames = {}

    # Limit to top 200 to prevent OOM on Render Free Tier (512MB RAM)
    symbols = symbols[:200]

    chunk_size = 40
    chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]

    for chunk_idx, chunk in enumerate(chunks):
        try:
            # Run sequentially to save memory and avoid YF rate limit bursts
            df = await loop.run_in_executor(_POOL, partial(_download_chunk, chunk, days))

            if len(chunk) == 1:
                sym = chunk[0]
                if not df.empty:
                    frames[sym] = df
            else:
                for sym in chunk:
                    yf_sym = f"{sym}.NS"
                    if yf_sym in df.columns.levels[0]:
                        ticker_df = df[yf_sym].dropna(how="all")
                        if not ticker_df.empty:
                            frames[sym] = ticker_df

            # Sleep briefly to avoid YFRateLimitError
            await asyncio.sleep(1.0)
        except Exception as e:
            log.error(f"Failed to download chunk {chunk_idx}: {e}")

    return frames
