import pandas as pd
import numpy as np
from domain.calc.adx import adx
from domain.calc.relative_strength import rs_raw, pct_from_52w_high, risk_adj_mom
from domain.calc.pivots import swing_points, get_swing_structure
from domain.calc.pead import pead_52w

def test_adx():
    h = pd.Series([10, 12, 11, 13, 15, 14, 16])
    l = pd.Series([8, 9, 10, 11, 12, 13, 14])
    c = pd.Series([9, 11, 10, 12, 14, 13, 15])
    adx_series, pdi, mdi = adx(h, l, c, n=2)
    assert not adx_series.empty
    assert not pdi.empty
    assert not mdi.empty

def test_relative_strength():
    c = pd.Series(np.linspace(100, 200, 300))
    rs = rs_raw(c)
    assert not np.isnan(rs)
    
    pct_high = pct_from_52w_high(c)
    assert pct_high == 0.0  # since last element is max
    
    risk_mom = risk_adj_mom(c)
    assert not np.isnan(risk_mom)

def test_pivots():
    h = pd.Series([10, 12, 15, 12, 10, 13, 18, 13, 10])
    l = pd.Series([8, 10, 12, 10, 8, 11, 15, 11, 8])
    ph, pl = swing_points(h, l, k=1)
    
    struct = get_swing_structure(h, l, k=1)
    assert struct in ["HH_HL", "LH_LL", "RANGE", "UNKNOWN"]

def test_pead():
    c = pd.Series(np.linspace(100, 200, 300))
    res = pead_52w(c)
    assert res == "MOMENTUM_NEAR_HIGH"
