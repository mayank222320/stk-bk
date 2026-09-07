import pandas as pd
from domain.calc.volume_profile import volume_profile

def test_volume_profile():
    df = pd.DataFrame({
        "High": [10, 11, 12, 13, 14],
        "Low": [8, 9, 10, 11, 12],
        "Close": [9, 10, 11, 12, 13],
        "Volume": [100, 200, 300, 200, 100]
    })
    res = volume_profile(df, bins=3, lookback=5)
    assert "poc" in res
    assert "vah" in res
    assert "val" in res
    assert "position" in res

def test_volume_profile_unavailable():
    df = pd.DataFrame({"High": [], "Low": [], "Close": [], "Volume": []})
    res = volume_profile(df)
    assert res["poc"] == "UNAVAILABLE"
