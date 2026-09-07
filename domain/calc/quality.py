import pandas as pd


def piotroski_f_score(income_stmt: pd.DataFrame, balance_sheet: pd.DataFrame, cashflow: pd.DataFrame) -> int:
    """
    Piotroski F-score (0-9).
    Requires statements ordered with newest first (iloc[0] is most recent year).
    Returns -1 if UNAVAILABLE.
    """
    try:
        score = 0
        if len(income_stmt.columns) < 2 or len(balance_sheet.columns) < 2 or len(cashflow.columns) < 2:
            return -1

        c0 = income_stmt.columns[0]
        c1 = income_stmt.columns[1]

        # 1. ROA > 0
        net_income = income_stmt.loc["Net Income", c0] if "Net Income" in income_stmt.index else 0
        total_assets = balance_sheet.loc["Total Assets", c0] if "Total Assets" in balance_sheet.index else 1
        roa = net_income / total_assets
        if roa > 0:
            score += 1

        # 2. CFO > 0
        cfo = cashflow.loc["Operating Cash Flow", c0] if "Operating Cash Flow" in cashflow.index else 0
        if cfo > 0:
            score += 1

        # 3. Delta ROA > 0
        net_income_prev = income_stmt.loc["Net Income", c1] if "Net Income" in income_stmt.index else 0
        total_assets_prev = balance_sheet.loc["Total Assets", c1] if "Total Assets" in balance_sheet.index else 1
        roa_prev = net_income_prev / total_assets_prev
        if roa > roa_prev:
            score += 1

        # 4. CFO > ROA (Accrual quality)
        if (cfo / total_assets) > roa:
            score += 1

        # 5. Delta Leverage < 0
        lt_debt = balance_sheet.loc["Long Term Debt", c0] if "Long Term Debt" in balance_sheet.index else 0
        lt_debt_prev = balance_sheet.loc["Long Term Debt", c1] if "Long Term Debt" in balance_sheet.index else 0
        lev = lt_debt / total_assets
        lev_prev = lt_debt_prev / total_assets_prev
        if lev < lev_prev:
            score += 1

        # 6. Delta Current Ratio > 0
        ca = balance_sheet.loc["Current Assets", c0] if "Current Assets" in balance_sheet.index else 0
        cl = balance_sheet.loc["Current Liabilities", c0] if "Current Liabilities" in balance_sheet.index else 1
        ca_prev = balance_sheet.loc["Current Assets", c1] if "Current Assets" in balance_sheet.index else 0
        cl_prev = balance_sheet.loc["Current Liabilities", c1] if "Current Liabilities" in balance_sheet.index else 1
        cr = ca / cl
        cr_prev = ca_prev / cl_prev
        if cr > cr_prev:
            score += 1

        # 7. No new share issuance
        shares = balance_sheet.loc["Ordinary Shares Number", c0] if "Ordinary Shares Number" in balance_sheet.index else 0
        shares_prev = balance_sheet.loc["Ordinary Shares Number", c1] if "Ordinary Shares Number" in balance_sheet.index else 0
        if shares <= shares_prev:
            score += 1

        # 8. Delta Gross Margin > 0
        gm = income_stmt.loc["Gross Profit", c0] / income_stmt.loc["Total Revenue", c0] if "Gross Profit" in income_stmt.index and "Total Revenue" in income_stmt.index else 0
        gm_prev = income_stmt.loc["Gross Profit", c1] / income_stmt.loc["Total Revenue", c1] if "Gross Profit" in income_stmt.index and "Total Revenue" in income_stmt.index else 0
        if gm > gm_prev:
            score += 1

        # 9. Delta Asset Turnover > 0
        at = income_stmt.loc["Total Revenue", c0] / total_assets if "Total Revenue" in income_stmt.index else 0
        at_prev = income_stmt.loc["Total Revenue", c1] / total_assets_prev if "Total Revenue" in income_stmt.index else 0
        if at > at_prev:
            score += 1

        return score
    except Exception:
        return -1

def altman_z_score(income_stmt: pd.DataFrame, balance_sheet: pd.DataFrame, mkt_cap: float) -> float:
    """
    Altman Z-score.
    < 1.8 = distress zone.
    Returns float('nan') if UNAVAILABLE.
    """
    try:
        if len(income_stmt.columns) < 1 or len(balance_sheet.columns) < 1:
            return float('nan')

        c0 = income_stmt.columns[0]

        ca = balance_sheet.loc["Current Assets", c0] if "Current Assets" in balance_sheet.index else 0
        cl = balance_sheet.loc["Current Liabilities", c0] if "Current Liabilities" in balance_sheet.index else 0
        wc = ca - cl
        ta = balance_sheet.loc["Total Assets", c0] if "Total Assets" in balance_sheet.index else 1
        re = balance_sheet.loc["Retained Earnings", c0] if "Retained Earnings" in balance_sheet.index else 0
        ebit = income_stmt.loc["EBIT", c0] if "EBIT" in income_stmt.index else 0
        tl = balance_sheet.loc["Total Liabilities Net Minority Interest", c0] if "Total Liabilities Net Minority Interest" in balance_sheet.index else 1
        sales = income_stmt.loc["Total Revenue", c0] if "Total Revenue" in income_stmt.index else 0

        z = 1.2 * (wc / ta) + 1.4 * (re / ta) + 3.3 * (ebit / ta) + 0.6 * (mkt_cap / tl) + 1.0 * (sales / ta)
        return float(z)
    except Exception:
        return float('nan')
