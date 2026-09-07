import pandas as pd
import pytest

from domain.rules.scoring import score_universe

def test_score_universe():
    # Mock data
    symbols = ["TEST1", "TEST2"]
    
    # Create valid dataframe for TEST1
    dates = pd.date_range("2025-01-01", periods=250)
    df1 = pd.DataFrame({
        "Close": [100.0] * 250,
        "High": [105.0] * 250,
        "Low": [95.0] * 250,
        "Volume": [1000000] * 250
    }, index=dates)
    
    # Create invalid dataframe for TEST2 (too short)
    df2 = pd.DataFrame({
        "Close": [100.0] * 10,
        "High": [105.0] * 10,
        "Low": [95.0] * 10,
        "Volume": [1000000] * 10
    }, index=dates[:10])
    
    frames = {"TEST1": df1, "TEST2": df2}
    
    nifty = pd.Series([20000.0] * 250, index=dates)
    regime = {"nifty": nifty}
    
    scored = score_universe(symbols, frames, regime)
    
    assert len(scored) == 1
    assert scored[0]["symbol"] == "TEST1"
    assert "score" in scored[0]
    assert "illiquid" not in scored[0]["reasons"] # because volume is high enough
