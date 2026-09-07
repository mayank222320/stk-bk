"""
Time and trading-day utilities for StockAI.
Dates and display strings use IST. Raw datetimes are stored in UTC.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def now_ist() -> datetime:
    """Current timestamp in IST."""
    return datetime.now(IST)


def today_ist() -> str:
    """Current date key as YYYY-MM-DD in IST."""
    return now_ist().strftime("%Y-%m-%d")


def fmt_ist(dt: datetime | None = None) -> str:
    """Format datetime as readable IST string."""
    target = dt if dt is not None else now_ist()
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return target.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def is_market_hours(dt: datetime | None = None) -> bool:
    """Check if timestamp falls within normal NSE market hours (09:15 - 15:30 IST on Mon-Fri)."""
    target = (dt or now_ist()).astimezone(IST)
    if target.weekday() >= 5:
        return False
    market_open = target.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = target.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= target <= market_close
