import asyncio
from functools import partial

import requests

from core.errors import DataUnavailable
from core.freshness import Stamped
from core.timeutils import now_ist


def _sync_fetch_nav(code: int) -> dict:
    url = f"https://api.mfapi.in/mf/{code}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

async def fetch_nav_history(code: int) -> Stamped:
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, partial(_sync_fetch_nav, code))
        return Stamped(
            value=data,
            source="mfapi",
            captured_at=now_ist(),
            kind="quote"
        )
    except Exception as e:
        raise DataUnavailable("mfapi", f"Failed to fetch NAV for {code}: {e}")
