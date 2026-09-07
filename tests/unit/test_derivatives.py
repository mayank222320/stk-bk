import pandas as pd
import math
from domain.calc.derivatives import (
    calculate_iv_rank, calculate_iv_percentile, calculate_futures_basis, 
    calculate_rollover_pct, interpret_oi_buildup
)

def test_calculate_iv_rank():
    assert calculate_iv_rank(20, 10, 30) == 50.0
    assert calculate_iv_rank(10, 10, 10) == 0.0

def test_calculate_iv_percentile():
    hist = pd.Series([10, 15, 25, 30])
    assert calculate_iv_percentile(20, hist) == 50.0
    assert math.isnan(calculate_iv_percentile(20, pd.Series([])))

def test_calculate_futures_basis():
    assert calculate_futures_basis(105, 100) == 5.0

def test_calculate_rollover_pct():
    assert calculate_rollover_pct(80, 100) == 80.0

def test_interpret_oi_buildup():
    assert interpret_oi_buildup(1.0, 1.0) == "LONG_BUILDUP"
    assert interpret_oi_buildup(1.0, -1.0) == "SHORT_COVERING"
    assert interpret_oi_buildup(-1.0, 1.0) == "SHORT_BUILDUP"
    assert interpret_oi_buildup(-1.0, -1.0) == "LONG_UNWINDING"
    assert interpret_oi_buildup(0.0, 0.0) == "NEUTRAL"
