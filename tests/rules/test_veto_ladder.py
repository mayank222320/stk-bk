import pytest
from domain.rules.veto_ladder import apply_veto_ladder

@pytest.mark.parametrize("ctx,expected_veto", [
    # 1. Binding input STALE/UNAVAILABLE
    ({"binding_inputs_status": "STALE"}, "Binding input STALE"),
    ({"binding_inputs_status": "UNAVAILABLE"}, "Binding input UNAVAILABLE"),
    # 2. Two deterministic price sources diverge > 2%
    ({"price_divergence_pct": 2.5}, "Price sources diverge > 2%"),
    # 3. Regime = RISK_OFF
    ({"regime": "RISK_OFF"}, "Regime is RISK_OFF"),
    # 4. Results within 5 trading days
    ({"days_to_results": 3}, "Results within 5 days"),
    ({"days_to_results": 5}, "Results within 5 days"),
    # 5. ADX < 20 for a breakout/momentum setup
    ({"setup_type": "breakout", "adx": 18}, "ADX < 20 for breakout/momentum"),
    ({"setup_type": "momentum", "adx": 15}, "ADX < 20 for breakout/momentum"),
    # 6. Weekly trend against the trade
    ({"trade_direction": "LONG", "weekly_trend": "DOWN"}, "Weekly trend against trade"),
    ({"trade_direction": "SHORT", "weekly_trend": "UP"}, "Weekly trend against trade"),
    # 7. Structure = LH_LL
    ({"structure": "LH_LL"}, "Structure is LH_LL"),
    # 8. RS Rating < 50
    ({"rs_rating": 45}, "RS Rating < 50"),
    # 9. Turnover < ₹15 Cr
    ({"turnover_cr": 10}, "Turnover < 15 Cr"),
    # 10. Piotroski <= 3 or Altman Z < 1.8
    ({"piotroski_score": 3}, "Piotroski <= 3"),
    ({"altman_z": 1.5}, "Altman Z < 1.8"),
    # 11. R:R to T1 < 1:2 after the ATR stop is placed
    ({"rr_to_t1": 0.4}, "R:R to T1 < 1:2"),
    # 12. Any QMAF entry gate = FAIL; portfolio heat cap breached
    ({"qmaf_gate_failed": True}, "QMAF gate failed"),
    ({"heat_cap_breached": True}, "Portfolio heat cap breached"),
])
def test_hard_vetoes(ctx, expected_veto):
    passed, reason = apply_veto_ladder(ctx)
    assert not passed
    assert reason == expected_veto

def test_clean_setup_passes():
    ctx = {
        "binding_inputs_status": "OK",
        "price_divergence_pct": 1.5,
        "regime": "RISK_ON",
        "days_to_results": 10,
        "setup_type": "breakout",
        "adx": 25,
        "trade_direction": "LONG",
        "weekly_trend": "UP",
        "structure": "HH_HL",
        "rs_rating": 80,
        "turnover_cr": 50,
        "piotroski_score": 7,
        "altman_z": 3.0,
        "rr_to_t1": 2.5,
        "qmaf_gate_failed": False,
        "heat_cap_breached": False
    }
    passed, reason = apply_veto_ladder(ctx)
    assert passed
    assert reason == "PASS"

def test_missing_data_graceful():
    # If missing most non-binding data, it should pass unless it explicitly violates a rule
    ctx = {
        "binding_inputs_status": "OK"
    }
    passed, reason = apply_veto_ladder(ctx)
    assert passed
    assert reason == "PASS"
