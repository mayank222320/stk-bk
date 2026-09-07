import math


def calculate_position_size(
    entry: float,
    stop: float,
    capital: float,
    risk_pct: float,
    size_multiplier: float = 1.0,
    max_single_pct: float = 15.0
) -> dict:
    """
    Pure function to calculate position size.
    """
    if entry <= stop:
        raise ValueError("entry must be greater than stop for longs")

    risk_per_share = entry - stop
    risk_amount = capital * (risk_pct / 100.0) * size_multiplier

    qty = math.floor(risk_amount / risk_per_share)
    position_value = qty * entry

    # Cap by max single position percentage
    max_value = capital * (max_single_pct / 100.0)
    if position_value > max_value:
        qty = math.floor(max_value / entry)
        position_value = qty * entry

    actual_risk = qty * risk_per_share

    return {
        "qty": qty,
        "position_value": position_value,
        "risk_amount": actual_risk,
        "risk_per_share": risk_per_share,
    }
