from dataclasses import dataclass
from datetime import datetime

from core.timeutils import IST, is_market_hours, now_ist

# seconds allowed during a live session; outside session everything is LAST_CLOSE
BUDGET = {"quote": 900, "option_chain": 1800, "fii_dii": 129600,     # 15m / 30m / T-1
          "indicators": None, "fundamentals": 7776000, "news": 432000}  # close / 1q / 5d

@dataclass
class Stamped:
    value: object
    source: str
    captured_at: datetime
    kind: str
    @property
    def age_seconds(self) -> int:
        return int((now_ist() - self.captured_at.astimezone(IST)).total_seconds())
    @property
    def state(self) -> str:
        if self.value is None:
            return "UNAVAILABLE"
        if self.kind == "indicators":
            return "LAST_CLOSE"
        b = BUDGET.get(self.kind)
        if b is None:
            return "LAST_CLOSE"
        if not is_market_hours():
            return "LAST_CLOSE"
        return "LIVE" if self.age_seconds <= b/3 else ("DELAYED" if self.age_seconds <= b else "STALE")

    def to_prompt(self) -> str:
        return f"{self.value}  [{self.state}, {self.source}, {self.age_seconds}s old]"

def session_state() -> str:
    """PRE_OPEN | OPEN | POST | CLOSED | HOLIDAY | WEEKEND"""
    d = now_ist()
    if d.weekday() >= 5:
        return "WEEKEND"
    hm = d.hour*60 + d.minute
    if hm < 540:
        return "CLOSED"          # before 09:00
    if hm < 555:
        return "PRE_OPEN"        # 09:00-09:15
    if hm <= 930:
        return "OPEN"            # 09:15-15:30
    if hm <= 960:
        return "POST"            # 15:30-16:00
    return "CLOSED"

def apply_freshness_gate(inputs: dict[str, Stamped], reco: dict) -> dict:
    stale = [k for k, s in inputs.items() if s.state in ("STALE", "UNAVAILABLE")]
    binding = {"quote", "indicators"}
    if binding & set(stale):
        reco["recommendation"] = "WAIT"
        reco["data_conflicts"] = reco.get("data_conflicts", []) + \
            [f"binding input stale/unavailable: {sorted(binding & set(stale))}"]
    reco["data_confidence"] = max(1, reco.get("data_confidence", 5) - 2*len(stale))
    return reco
