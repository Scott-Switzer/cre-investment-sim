"""
Transparent naive valuation benchmarks.

These give students a believable starting point and a straw-man to beat.
- NOI / market cap rate
- median comparable value by property type
- simple price-per-SF benchmark
"""

from __future__ import annotations

from typing import Dict, List
import pandas as pd
import numpy as np


def naive_value_benchmarks(properties: pd.DataFrame, market_cap_by_type: Dict[str, float]) -> pd.DataFrame:
    """
    Compute naive valuations for each property using three simple methods.
    Returns a DataFrame with the same index as properties, plus columns:
    - noi_cap_value
    - median_comp_value
    - price_per_sf_value
    - benchmark_value (simple average of the three)
    """
    df = properties.copy()
    # Method 1: NOI / market cap
    df["noi_cap_value"] = df.apply(lambda r: r["current_noi"] / market_cap_by_type.get(r["type"], r["going_in_cap"]), axis=1)
    # Method 2: median comparable value by type
    median_by_type = df.groupby("type")["asking_price"].median()
    df["median_comp_value"] = df["type"].map(median_by_type)
    # Method 3: price per SF benchmark by type (asking price / size_sf median)
    ppsf_by_type = (df["asking_price"] * 1_000_000 / df["size_sf"]).groupby(df["type"]).median()
    df["price_per_sf_value"] = (df["size_sf"] * ppsf_by_type.reindex(df["type"]).values) / 1_000_000
    df["benchmark_value"] = df[["noi_cap_value", "median_comp_value", "price_per_sf_value"]].mean(axis=1)
    return df
