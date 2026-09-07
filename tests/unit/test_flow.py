import pandas as pd
from domain.calc.flow import flow_metrics, calculate_delivery_ratio

def test_flow_metrics():
    df = pd.DataFrame({
        "High": list(range(10, 71)),
        "Low": list(range(5, 66)),
        "Close": list(range(8, 69)),
        "Volume": [100] * 61
    })
    res = flow_metrics(df)
    assert "obv" in res
    assert "cmf" in res
    assert "ud_ratio" in res

def test_flow_metrics_unavailable():
    df = pd.DataFrame({"High": [10], "Low": [5], "Close": [8], "Volume": [100]})
    res = flow_metrics(df)
    assert res["obv"] == "UNAVAILABLE"

def test_calculate_delivery_ratio():
    assert calculate_delivery_ratio(50.0, 40.0) == 1.25
