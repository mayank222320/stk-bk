def calculate_costs(buy_val: float, sell_val: float, delivery: bool = True) -> float:
    t = buy_val + sell_val
    stt = 0.001 * t if delivery else 0.00025 * sell_val
    exch = t * 0.0000322
    sebi = t * 0.000001
    stamp = buy_val * 0.00015
    brok = 0.0 if delivery else min(20.0, 0.0003 * t)
    gst = 0.18 * (brok + exch + sebi)
    return round(stt + exch + sebi + stamp + brok + gst, 2)
