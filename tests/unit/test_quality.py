import pandas as pd
import numpy as np
from domain.calc.quality import piotroski_f_score, altman_z_score

def test_piotroski_f_score():
    income = pd.DataFrame({
        "2023": [100, 50, 20],
        "2022": [80, 40, 10]
    }, index=["Total Revenue", "Gross Profit", "Net Income"])
    
    balance = pd.DataFrame({
        "2023": [1000, 200, 150, 300, 100],
        "2022": [900, 150, 100, 350, 100]
    }, index=["Total Assets", "Current Assets", "Current Liabilities", "Long Term Debt", "Ordinary Shares Number"])
    
    cashflow = pd.DataFrame({
        "2023": [30],
        "2022": [15]
    }, index=["Operating Cash Flow"])
    
    score = piotroski_f_score(income, balance, cashflow)
    assert isinstance(score, int)
    assert -1 <= score <= 9

def test_altman_z_score():
    income = pd.DataFrame({
        "2023": [100, 20],
    }, index=["Total Revenue", "EBIT"])
    
    balance = pd.DataFrame({
        "2023": [1000, 200, 150, 50, 400],
    }, index=["Total Assets", "Current Assets", "Current Liabilities", "Retained Earnings", "Total Liabilities Net Minority Interest"])
    
    score = altman_z_score(income, balance, mkt_cap=500.0)
    assert isinstance(score, float)
    assert not np.isnan(score)
