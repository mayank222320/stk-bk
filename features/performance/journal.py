def calculate_mae_mfe(fill: float, stop: float, daily_closes: list[float]) -> dict:
    if not daily_closes or fill == stop:
        return {"mae_r": 0.0, "mfe_r": 0.0}
    
    risk = fill - stop
    if risk == 0:
        return {"mae_r": 0.0, "mfe_r": 0.0}
        
    mae_r = min((c - fill) / risk for c in daily_closes)
    mfe_r = max((c - fill) / risk for c in daily_closes)
    
    return {"mae_r": round(mae_r, 3), "mfe_r": round(mfe_r, 3)}

def calculate_expectancy(trades: list[dict]) -> dict:
    if not trades:
        return {"win_rate": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0, "expectancy_r": 0.0}
        
    wins = [t for t in trades if t.get("r_multiple", 0) > 0]
    losses = [t for t in trades if t.get("r_multiple", 0) <= 0]
    
    wr = len(wins) / len(trades)
    aw = sum(t["r_multiple"] for t in wins) / len(wins) if wins else 0.0
    al = abs(sum(t["r_multiple"] for t in losses)) / len(losses) if losses else 0.0
    
    expectancy = wr * aw - (1 - wr) * al
    
    return {
        "win_rate": round(wr * 100, 1),
        "avg_win_r": round(aw, 2),
        "avg_loss_r": round(al, 2),
        "expectancy_r": round(expectancy, 3)
    }
