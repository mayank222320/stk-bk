from datetime import date

from scipy.optimize import brentq


def xirr(flows: list[tuple[date, float]]) -> float:
    """
    Calculate the Internal Rate of Return (IRR) for an irregular schedule of cash flows.
    flows: list of tuples (date, amount)
    amount < 0 is an investment/outflow, amount > 0 is a return/inflow
    Returns the annualized percentage as a float (e.g. 0.12 for 12%).
    """
    if not flows:
        return 0.0

    flows = sorted(flows, key=lambda x: x[0])
    t0 = flows[0][0]

    def npv(r: float) -> float:
        total = 0.0
        for d, amt in flows:
            years = (d - t0).days / 365.0
            total += amt / ((1.0 + r) ** years)
        return total

    try:
        # Search for root between -0.99 and 100.0 (i.e. -99% to 10000%)
        return brentq(npv, -0.99, 100.0)
    except (ValueError, RuntimeError):
        return 0.0
