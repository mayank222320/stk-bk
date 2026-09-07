from typing import TypedDict

import pandas as pd

from domain.calc.indicators import rsi


class DipStatus(TypedDict):
    tier: str
    deploy_pct: int
    deploy_amount: float
    reason: str

def calculate_dip_status(df: pd.DataFrame, budget: float, is_month_end: bool = False) -> DipStatus:
    if df.empty or len(df) < 50:
        return {"tier": "NONE", "deploy_pct": 0, "deploy_amount": 0.0, "reason": "Not enough data"}

    if is_month_end and budget > 0:
        return {"tier": "MONTH_END", "deploy_pct": 100, "deploy_amount": budget, "reason": "Deploy remaining budget at month end"}

    close = df['Close']
    cmp = close.iloc[-1]

    high_20 = close.tail(20).max()
    drawdown = (cmp - high_20) / high_20

    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1]

    rsi_series = rsi(close)
    rsi_val = rsi_series.iloc[-1]

    if drawdown <= -0.07 and cmp <= sma_50 * 1.02 and rsi_val < 35:
        return {"tier": "STRONG", "deploy_pct": 100, "deploy_amount": budget, "reason": f"-7% dip near 50DMA, RSI {rsi_val:.1f}"}
    elif drawdown <= -0.04 and cmp <= sma_20 * 1.01 and rsi_val < 45:
        return {"tier": "GOOD", "deploy_pct": 50, "deploy_amount": budget * 0.50, "reason": f"-4% dip at/below 20DMA, RSI {rsi_val:.1f}"}
    elif drawdown <= -0.02 and rsi_val < 55:
        return {"tier": "MILD", "deploy_pct": 33, "deploy_amount": budget * 0.33, "reason": f"-2% dip from 20d high, RSI {rsi_val:.1f}"}

    return {"tier": "NONE", "deploy_pct": 0, "deploy_amount": 0.0, "reason": "No dip condition met"}

def mon100_breakdown(etf_df: pd.DataFrame, ndx_df: pd.DataFrame, fx_df: pd.DataFrame, days: int = 5) -> dict:
    if len(etf_df) < days+1 or len(ndx_df) < days+1 or len(fx_df) < days+1:
        return {}

    etf_ret = (etf_df['Close'].iloc[-1] / etf_df['Close'].iloc[-days-1]) - 1.0
    ndx_ret = (ndx_df['Close'].iloc[-1] / ndx_df['Close'].iloc[-days-1]) - 1.0
    fx_ret = (fx_df['Close'].iloc[-1] / fx_df['Close'].iloc[-days-1]) - 1.0

    theoretical_nav_ret = (1.0 + ndx_ret) * (1.0 + fx_ret) - 1.0

    if (1.0 + theoretical_nav_ret) != 0:
        premium_change = (1.0 + etf_ret) / (1.0 + theoretical_nav_ret) - 1.0
    else:
        premium_change = 0.0

    return {
        "etf_return": round(etf_ret * 100, 2),
        "ndx_return": round(ndx_ret * 100, 2),
        "inr_return": round(fx_ret * 100, 2),
        "premium_change": round(premium_change * 100, 2)
    }
