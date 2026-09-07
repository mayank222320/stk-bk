import pandas as pd
from domain.calc.vsa import vsa_classify

def test_vsa_classify():
    df = pd.DataFrame({
        "High": list(range(10, 31)),
        "Low": list(range(5, 26)),
        "Close": list(range(8, 29)),
        "Volume": [100] * 21
    })
    res = vsa_classify(df)
    assert isinstance(res, str)
    assert res in ["NEUTRAL", "ABSORPTION_STOPPING_VOLUME", "DISTRIBUTION_SUPPLY", "CLIMACTIC_BUYING", "SELLING_CLIMAX", "NO_DEMAND", "NO_SUPPLY", "PROFESSIONAL_BUYING"]

def test_vsa_classify_unavailable():
    df = pd.DataFrame({"High": [10], "Low": [5], "Close": [8], "Volume": [100]})
    res = vsa_classify(df)
    assert res == "UNAVAILABLE"
