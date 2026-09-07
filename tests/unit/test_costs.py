import pytest
from domain.calc.costs import calculate_costs
from features.performance.journal import calculate_mae_mfe, calculate_expectancy

def test_calculate_costs_delivery():
    # Buy 100 shares at 100, sell at 110. delivery=True
    # buy_val = 10000, sell_val = 11000
    # t = 21000
    # stt = 0.001 * 21000 = 21
    # exch = 21000 * 0.0000322 = 0.6762
    # sebi = 21000 * 0.000001 = 0.021
    # stamp = 10000 * 0.00015 = 1.5
    # brok = 0.0
    # gst = 0.18 * (0.0 + 0.6762 + 0.021) = 0.125496
    # total = 21 + 0.6762 + 0.021 + 1.5 + 0.0 + 0.125496 = 23.322696 -> 23.32
    cost = calculate_costs(10000, 11000, delivery=True)
    assert cost == 23.32

def test_calculate_costs_intraday():
    # Buy 10000, sell 11000, delivery=False
    # t = 21000
    # stt = 0.00025 * 11000 = 2.75
    # exch = 21000 * 0.0000322 = 0.6762
    # sebi = 21000 * 0.000001 = 0.021
    # stamp = 10000 * 0.00015 = 1.5
    # brok = min(20.0, 0.0003 * 21000) = min(20.0, 6.3) = 6.3
    # gst = 0.18 * (6.3 + 0.6762 + 0.021) = 0.18 * 6.9972 = 1.259496
    # total = 2.75 + 0.6762 + 0.021 + 1.5 + 6.3 + 1.259496 = 12.506696 -> 12.51
    cost = calculate_costs(10000, 11000, delivery=False)
    assert cost == 12.51

def test_calculate_mae_mfe():
    fill = 100
    stop = 90
    closes = [98, 105, 110, 95]
    # risk = 10
    # closes vs fill: -2, +5, +10, -5
    # R multiples: -0.2, 0.5, 1.0, -0.5
    # MAE = -0.5
    # MFE = 1.0
    res = calculate_mae_mfe(fill, stop, closes)
    assert res["mae_r"] == -0.5
    assert res["mfe_r"] == 1.0

def test_calculate_mae_mfe_empty():
    res = calculate_mae_mfe(100, 90, [])
    assert res["mae_r"] == 0.0
    assert res["mfe_r"] == 0.0

def test_calculate_expectancy():
    trades = [
        {"r_multiple": 2.0},
        {"r_multiple": 3.0},
        {"r_multiple": -1.0},
        {"r_multiple": -1.0},
        {"r_multiple": 0.0} # counted as loss/scratch
    ]
    # wins: 2.0, 3.0 -> sum 5.0, avg 2.5
    # losses: -1.0, -1.0, 0.0 -> sum -2.0, avg (abs) 2.0/3 = 0.666...
    # WR = 2/5 = 0.4
    # expectancy = 0.4 * 2.5 - 0.6 * 0.666... = 1.0 - 0.4 = 0.6
    res = calculate_expectancy(trades)
    assert res["win_rate"] == 40.0
    assert res["avg_win_r"] == 2.5
    assert res["avg_loss_r"] == 0.67
    assert res["expectancy_r"] == 0.6

def test_calculate_expectancy_empty():
    res = calculate_expectancy([])
    assert res["expectancy_r"] == 0.0
