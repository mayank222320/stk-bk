def apply_veto_ladder(context: dict) -> tuple[bool, str]:
    """
    Apply the 12 Level 1 Hard Vetoes from the Veto Ladder.
    Returns a tuple (passed, reason).
    If passed is True, reason is "PASS".
    If passed is False, reason is the veto reason.
    """
    # 1. Binding input STALE/UNAVAILABLE
    binding_status = context.get('binding_inputs_status', 'OK')
    if binding_status in ('STALE', 'UNAVAILABLE'):
        return False, f"Binding input {binding_status}"

    # 2. Two deterministic price sources diverge > 2%
    price_divergence_pct = context.get('price_divergence_pct')
    if price_divergence_pct is not None and price_divergence_pct > 2.0:
        return False, "Price sources diverge > 2%"

    # 3. Regime = RISK_OFF
    if context.get('regime') == 'RISK_OFF':
        return False, "Regime is RISK_OFF"

    # 4. Results within 5 trading days
    days_to_results = context.get('days_to_results')
    if days_to_results is not None and days_to_results <= 5:
        return False, "Results within 5 days"

    # 5. ADX < 20 for a breakout/momentum setup
    setup_type = context.get('setup_type')
    adx = context.get('adx')
    if setup_type in ('breakout', 'momentum') and adx is not None and adx < 20:
        return False, "ADX < 20 for breakout/momentum"

    # 6. Weekly trend against the trade
    trade_direction = context.get('trade_direction', 'LONG')
    weekly_trend = context.get('weekly_trend')
    if weekly_trend is not None:
        if trade_direction == 'LONG' and weekly_trend == 'DOWN':
            return False, "Weekly trend against trade"
        if trade_direction == 'SHORT' and weekly_trend == 'UP':
            return False, "Weekly trend against trade"

    # 7. Structure = LH_LL
    if context.get('structure') == 'LH_LL':
        return False, "Structure is LH_LL"

    # 8. RS Rating < 50
    rs_rating = context.get('rs_rating')
    if rs_rating is not None and rs_rating < 50:
        return False, "RS Rating < 50"

    # 9. Turnover < ₹15 Cr
    turnover_cr = context.get('turnover_cr')
    if turnover_cr is not None and turnover_cr < 15:
        return False, "Turnover < 15 Cr"

    # 10. Piotroski <= 3 or Altman Z < 1.8
    piotroski_score = context.get('piotroski_score')
    if piotroski_score is not None and piotroski_score <= 3:
        return False, "Piotroski <= 3"

    altman_z = context.get('altman_z')
    if altman_z is not None and altman_z < 1.8:
        return False, "Altman Z < 1.8"

    # 11. R:R to T1 < 1:2 after the ATR stop is placed
    rr_to_t1 = context.get('rr_to_t1')
    if rr_to_t1 is not None and rr_to_t1 < 0.5:
        return False, "R:R to T1 < 1:2"

    # 12. Any QMAF entry gate = FAIL; portfolio heat cap breached
    if context.get('qmaf_gate_failed'):
        return False, "QMAF gate failed"
    if context.get('heat_cap_breached'):
        return False, "Portfolio heat cap breached"

    return True, "PASS"
