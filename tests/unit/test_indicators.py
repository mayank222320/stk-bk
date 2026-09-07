"""
Unit tests for domain/calc/indicators.py.
Verifies Wilder-smoothed indicators (RSI, ATR, ADX), MACD, Bollinger Bands, and Moving Averages.
"""
import numpy as np
import pandas as pd
import pytest

from domain.calc.indicators import adx, atr, bbands, ema, macd, rsi, sma


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate 60 days of deterministic sample price bars."""
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    np.random.seed(42)
    # Drift up slowly with oscillation
    trend = np.linspace(100, 150, 60)
    noise = np.sin(np.linspace(0, 4 * np.pi, 60)) * 5
    close = trend + noise
    high = close + np.random.uniform(1, 3, 60)
    low = close - np.random.uniform(1, 3, 60)
    open_ = close + np.random.uniform(-1, 1, 60)
    volume = np.random.randint(100_000, 500_000, 60)

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


def test_rsi_bounds_and_values(sample_ohlcv):
    close = sample_ohlcv["Close"]
    r = rsi(close, n=14)

    assert isinstance(r, pd.Series)
    valid_rsi = r.dropna()
    assert len(valid_rsi) > 30
    assert (valid_rsi >= 0).all()
    assert (valid_rsi <= 100).all()

    # Monotonically increasing close should yield RSI near 100
    all_up = pd.Series([10.0 + i for i in range(30)])
    r_up = rsi(all_up, n=14).dropna()
    assert r_up.iloc[-1] > 99.0


def test_atr_positive(sample_ohlcv):
    h = sample_ohlcv["High"]
    low = sample_ohlcv["Low"]
    c = sample_ohlcv["Close"]
    a = atr(h, low, c, n=14)

    assert isinstance(a, pd.Series)
    valid_atr = a.dropna()
    assert len(valid_atr) > 40
    # True range is strictly positive
    assert (valid_atr > 0).all()


def test_macd_relationship(sample_ohlcv):
    c = sample_ohlcv["Close"]
    line, sig, hist = macd(c, fast=12, slow=26, signal=9)

    assert len(line) == len(c)
    assert len(sig) == len(c)
    assert len(hist) == len(c)

    # Histogram must equal line - signal
    np.testing.assert_allclose(hist.values, (line - sig).values, rtol=1e-5)


def test_bbands_structure(sample_ohlcv):
    c = sample_ohlcv["Close"]
    upper, mid, lower = bbands(c, n=20, k=2.0)

    valid_idx = ~upper.isna()
    # Upper >= Mid >= Lower
    assert (upper[valid_idx] >= mid[valid_idx]).all()
    assert (mid[valid_idx] >= lower[valid_idx]).all()


def test_adx_bounds(sample_ohlcv):
    h = sample_ohlcv["High"]
    low = sample_ohlcv["Low"]
    c = sample_ohlcv["Close"]
    adx_val, pdi, mdi = adx(h, low, c, n=14)

    valid_adx = adx_val.dropna()
    assert len(valid_adx) > 30
    assert (valid_adx >= 0).all()
    assert (valid_adx <= 100).all()
    assert (pdi.dropna() >= 0).all()
    assert (mdi.dropna() >= 0).all()


def test_ema_and_sma(sample_ohlcv):
    c = sample_ohlcv["Close"]
    e20 = ema(c, 20)
    s20 = sma(c, 20)

    assert len(e20) == len(c)
    assert s20.iloc[18] is not None
    assert np.isnan(s20.iloc[18])
    assert not np.isnan(s20.iloc[19])
