from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field

class DailyEntry(BaseModel):
    d: str
    c: float
    r: float

class SwingPositionCreate(BaseModel):
    symbol: str
    source: Literal["AI", "MANUAL"]
    setup_type: str
    entry_zone_low: float
    entry_zone_high: float
    t1: float
    stop_loss: float
    t2: float = 0.0
    t3: float = 0.0
    qty: int = 0
    notes: str = ""
    thesis: str = ""

class SwingPositionResponse(SwingPositionCreate):
    id: str = Field(..., alias="_id")
    status: Literal["PENDING_ENTRY", "OPEN", "CLOSED", "EXPIRED", "CANCELLED"]
    fill_price: Optional[float] = None
    trailing_stop: float
    r_multiple: Optional[float] = None
    days_held: int = 0
    open_date: str
    fill_date: Optional[str] = None
    close_date: Optional[str] = None
    entry_valid_until: str
    daily: List[DailyEntry] = []
    entry_snapshot: dict = {}

    class Config:
        populate_by_name = True
