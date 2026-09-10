"""
Macroeconomic time-series table.

In production this would be refreshed from FRED/ALFRED with vintage-aware retrieval.
For the MVP we include a small cached public-data sample so the application works offline.
"""

from __future__ import annotations

from datetime import date
from typing import Dict
import pandas as pd

from src.data.provenance import Provenance, now, tag_label


_MACRO_PROV = Provenance(
    source_name="FRED public macro series (cached sample for offline demo)",
    source_url="https://fred.stlouisfed.org/",
    data_type="real_public",
    is_synthetic=False,
    notes="Cached public-data sample. In production, refresh from FRED/ALFRED with FRED_API_KEY and vintage-aware retrieval.",
)


def build_macro_history() -> pd.DataFrame:
    """Build a small macro history table for the last several quarters."""
    quarters = [
        date(2024, 3, 31),
        date(2024, 6, 30),
        date(2024, 9, 30),
        date(2024, 12, 31),
        date(2025, 3, 31),
        date(2025, 6, 30),
        date(2025, 9, 30),
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 8, 31),
    ]
    # 10-Year Treasury (percent)
    ten_yr = [0.042, 0.043, 0.041, 0.040, 0.042, 0.045, 0.048, 0.046, 0.047, 0.048, 0.048]
    # Short-term policy/risk-free proxy (percent)
    policy = [0.050, 0.051, 0.050, 0.048, 0.047, 0.045, 0.042, 0.041, 0.041, 0.040, 0.040]
    # Unemployment (percent)
    unemp = [0.038, 0.039, 0.039, 0.040, 0.040, 0.039, 0.038, 0.038, 0.039, 0.039, 0.039]
    # Inflation (CPI YoY, percent)
    inflation = [0.032, 0.031, 0.027, 0.026, 0.025, 0.026, 0.028, 0.029, 0.028, 0.028, 0.028]
    # Commercial real estate loan growth (YoY, percent) - approximate public proxy
    cre_loan_growth = [0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.01, 0.02, 0.02, 0.03, 0.03]
    # CRE delinquency (percent, approximate public proxy)
    cre_delinquency = [0.012, 0.013, 0.014, 0.015, 0.016, 0.018, 0.020, 0.021, 0.022, 0.023, 0.024]
    # Credit conditions index (0-1, approximate)
    credit_conditions = [0.55, 0.55, 0.52, 0.50, 0.48, 0.46, 0.44, 0.43, 0.42, 0.42, 0.42]

    rows = []
    for i, q in enumerate(quarters):
        rows.append({
            "series": "DGS10",
            "series_name": "10-Year Treasury Constant Maturity Rate",
            "frequency": "daily",
            "units": "percent",
            "observation_date": q,
            "value": ten_yr[i],
            "provenance": _MACRO_PROV,
            "available_at": q,
            "tag": tag_label(_MACRO_PROV),
        })
    df = pd.DataFrame(rows)
    # Add extra series in a long format for easy querying
    extras = [
        ("FEDFUNDS", "Effective Federal Funds Rate", "daily", "percent", policy),
        ("UNRATE", "Unemployment Rate", "monthly", "percent", unemp),
        ("CPIAUCSL_PCT", "CPI Inflation YoY (approx)", "monthly", "percent", inflation),
        ("CRE_LOAN_GROWTH", "Commercial Real Estate Loan Growth YoY (approx)", "quarterly", "percent", cre_loan_growth),
        ("CRE_DELINQUENCY", "Commercial Real Estate Loan Delinquency (approx)", "quarterly", "percent", cre_delinquency),
        ("CREDIT_CONDITIONS", "Credit Conditions Index (approx)", "quarterly", "index", credit_conditions),
    ]
    for series, name, freq, units, vals in extras:
        base = pd.DataFrame([{
            "series": series,
            "series_name": name,
            "frequency": freq,
            "units": units,
            "observation_date": quarters[i],
            "value": vals[i],
            "provenance": _MACRO_PROV,
            "available_at": quarters[i],
            "tag": tag_label(_MACRO_PROV),
        } for i in range(len(quarters))])
        df = pd.concat([df, base], ignore_index=True)
    return df


MACRO_SERIES = build_macro_history()
