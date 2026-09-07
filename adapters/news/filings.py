import asyncio
import random
from datetime import UTC, datetime


async def fetch_bse_announcements() -> list[dict]:
    """
    Mocked BSE announcements fetcher.
    In production, this would use `bse` library or NSE API.
    """
    await asyncio.sleep(0.5)

    # Return some mock data to simulate filings
    return [
        {
            "id": f"mock_filing_{random.randint(1000, 9999)}",
            "symbol": "RELIANCE",
            "category": "Board Meeting",
            "subject": "Board Meeting for Q2 Results",
            "link": "https://bseindia.com/mock",
            "timestamp": int(datetime.now(UTC).timestamp())
        }
    ]
