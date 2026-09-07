from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from core.freshness import Stamped, apply_freshness_gate, session_state

def test_stale_binding_forces_wait():
    inputs = {
        "quote": Stamped(
            value=100.0,
            source="test",
            captured_at=datetime(2023, 1, 1, tzinfo=ZoneInfo("UTC")),
            kind="quote"
        )
    }
    reco = {"recommendation": "BUY", "data_confidence": 9}
    
    with patch("core.freshness.now_ist", return_value=datetime(2023, 1, 5, tzinfo=ZoneInfo("Asia/Kolkata"))), \
         patch("core.freshness.is_market_hours", return_value=True):
         
        # Ensure it's stale
        assert inputs["quote"].state == "STALE"
        
        result = apply_freshness_gate(inputs, reco)
        
        assert result["recommendation"] == "WAIT"
        assert "data_conflicts" in result
        assert "binding input stale" in result["data_conflicts"][0]
        assert result["data_confidence"] == 7

def test_weekend_session():
    # 2026-09-05 is a Saturday
    dt = datetime(2026, 9, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    with patch("core.freshness.now_ist", return_value=dt):
        assert session_state() == "WEEKEND"
