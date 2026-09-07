import pytest
from datetime import date
from domain.calc.xirr import xirr

def test_xirr():
    flows = [
        (date(2025, 1, 1), -1000.0),
        (date(2025, 7, 2), -1000.0),
        (date(2026, 1, 1), 2200.0)
    ]
    result = xirr(flows)
    
    # 13.4% approximately
    assert round(result * 100, 2) in [13.48, 13.47, 13.49, 13.46, 13.45, 13.50, 13.44]

def test_xirr_empty():
    assert xirr([]) == 0.0
