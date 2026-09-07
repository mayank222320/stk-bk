import pytest
from domain.calc.sizing import calculate_position_size
from features.risk.service import size_position, portfolio_heat, get_risk_config
import features.risk.service as risk_service

def test_calculate_position_size_normal():
    # Capital: 500k, Risk Pct: 1.0 (5000)
    # Entry: 100, Stop: 90 -> risk/share: 10
    # Qty should be 5000 / 10 = 500
    res = calculate_position_size(
        entry=100.0,
        stop=90.0,
        capital=500000.0,
        risk_pct=1.0,
        size_multiplier=1.0,
        max_single_pct=15.0
    )
    assert res["qty"] == 500
    assert res["risk_amount"] == 5000.0
    assert res["position_value"] == 50000.0

def test_calculate_position_size_cap():
    # Capital: 500k, Risk Pct: 1.0 (5000), Max Single Pct: 15.0 (75000)
    # Entry: 100, Stop: 99 -> risk/share: 1
    # Without cap: qty = 5000. Position value = 500k (exceeds cap)
    # With cap: max value = 75000. Qty = 75000 / 100 = 750.
    res = calculate_position_size(
        entry=100.0,
        stop=99.0,
        capital=500000.0,
        risk_pct=1.0,
        size_multiplier=1.0,
        max_single_pct=15.0
    )
    assert res["qty"] == 750
    assert res["position_value"] == 75000.0
    assert res["risk_amount"] == 750.0

@pytest.mark.asyncio
async def test_heat_cap_blocks(monkeypatch):
    # Mock the portfolio_heat to return a high heat pct
    async def mock_portfolio_heat():
        return {
            "total_risk": 24000.0,  # 4.8% heat
            "heat_pct": 4.8,
            "open_positions": 4,
            "max_heat_pct": 5.0,
            "max_positions": 5
        }
    
    monkeypatch.setattr(risk_service, "portfolio_heat", mock_portfolio_heat)
    
    # Next trade would add 5000 (1%) risk, bringing heat to 5.8% (blocks)
    res = await size_position(100.0, 90.0)
    
    assert res["blocked"] is True
    assert "max heat breached" in res["reasons"]
    assert res["new_heat_pct"] == 5.8

@pytest.mark.asyncio
async def test_max_positions_blocks(monkeypatch):
    async def mock_portfolio_heat():
        return {
            "total_risk": 10000.0,  
            "heat_pct": 2.0,
            "open_positions": 5, # Max is 5
            "max_heat_pct": 5.0,
            "max_positions": 5
        }
    
    monkeypatch.setattr(risk_service, "portfolio_heat", mock_portfolio_heat)
    
    res = await size_position(100.0, 90.0)
    
    assert res["blocked"] is True
    assert "max positions reached" in res["reasons"]

def test_invalid_entry_stop():
    with pytest.raises(ValueError):
        calculate_position_size(
            entry=100.0,
            stop=110.0,
            capital=500000.0,
            risk_pct=1.0
        )
