"""
Baseline linear-regression workflow for valuation.

This module provides a transparent baseline that students can inspect, improve, and replace.
It does NOT secretly choose the best model for them.

Students can download training data and optionally a starter notebook from the Valuation Lab page.
Future student models can submit predictions through a CSV with:
property_id, predicted_value, predicted_noi, optional probability_of_loss, model_name, model_version
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score


def example_training_data(seed: int = 20240331, count: int = 30) -> pd.DataFrame:
    """
    Build a training dataset for the baseline regression.

    Target: property value (asking price as proxy for observed value in the teaching dataset).
    Features: size, occupancy, WALT, going-in cap, tenant concentration, opex ratio, property quality,
              market rent, debt rate, submarket embeddings (one-hot), type one-hot.
    """
    from src.data.properties import generate_properties
    props = generate_properties(seed=seed, count=count).copy()
    df = props.copy()
    df["value_target"] = df["asking_price"]
    df = df.drop(columns=["property_name", "site_address", "apn", "lease_expiry_profile", "source_name", "source_url", "notes", "data_type", "is_synthetic"])
    # One-hot encode type and submarket
    df = pd.get_dummies(df, columns=["type", "submarket"], drop_first=False)
    # Keep numeric features
    feature_cols = [
        "size_sf", "occupancy", "walt", "going_in_cap", "tenant_concentration",
        "opex_ratio", "property_quality", "market_rent", "in_place_rent",
        "debt_rate", "amortization_years", "max_ltv", "capex_need",
    ]
    # plus one-hot columns
    onehot_cols = [c for c in df.columns if c.startswith("type_") or c.startswith("submarket_")]
    feat_cols = [c for c in feature_cols if c in df.columns] + onehot_cols
    target_col = "value_target"
    X = df[feat_cols].astype(float)
    y = df[target_col].astype(float)
    return pd.concat([X, y], axis=1)


def train_baseline(seed: int = 20240331, count: int = 30) -> Tuple[LinearRegression, pd.DataFrame, pd.Series, List[str]]:
    """
    Train a transparent baseline linear regression on the example training data.
    Returns (model, X_train, y_train, feature_names).
    Uses a fixed random split so results are reproducible.
    """
    data = example_training_data(seed=seed, count=count)
    feature_cols = [c for c in data.columns if c != "value_target"]
    X = data[feature_cols].astype(float)
    y = data["value_target"].astype(float)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed)
    model = LinearRegression()
    model.fit(X_train, y_train)
    return model, X_train, y_train, feature_cols


def baseline_regression_model(seed: int = 20240331, count: int = 30) -> Dict:
    """
    Run the baseline regression and return a report dict for the Valuation Lab page.
    Includes coefficients, train/test MAE, R^2, and predicted values for the training set.
    """
    model, X_train, y_train, feature_cols = train_baseline(seed=seed, count=count)
    y_pred_train = model.predict(X_train)
    train_mae = mean_absolute_error(y_train, y_pred_train)
    train_r2 = r2_score(y_train, y_pred_train)
    coefs = pd.DataFrame({"feature": feature_cols, "coefficient": model.coef_}).sort_values("coefficient", key=abs, ascending=False)
    # Predict on the full property set for the valuation lab
    from src.data.properties import generate_properties
    props = generate_properties(seed=seed, count=count)
    X_full = pd.get_dummies(props[[
        "size_sf", "occupancy", "walt", "going_in_cap", "tenant_concentration",
        "opex_ratio", "property_quality", "market_rent", "in_place_rent",
        "debt_rate", "amortization_years", "max_ltv", "capex_need",
        "type", "submarket",
    ]], columns=["type", "submarket"], drop_first=False)
    X_full = X_full.reindex(columns=feature_cols, fill_value=0).astype(float)
    preds = model.predict(X_full)
    return {
        "model": "baseline_linear_regression",
        "train_mae": float(train_mae),
        "train_r2": float(train_r2),
        "coefficients": coefs,
        "predictions": pd.DataFrame({
            "property_id": props["property_id"],
            "predicted_value_mm": np.round(preds, 3),
            "asking_price": props["asking_price"],
            "error_mm": np.round(preds - props["asking_price"], 3),
        }),
        "feature_cols": feature_cols,
        "note": "This is a transparent baseline. Students should build and submit their own models.",
    }


def train_ridge_baseline(seed: int = 20240331, count: int = 30) -> Dict:
    """Alternative regularized baseline (Ridge) for the valuation lab."""
    data = example_training_data(seed=seed, count=count)
    feature_cols = [c for c in data.columns if c != "value_target"]
    X = data[feature_cols].astype(float)
    y = data["value_target"].astype(float)
    from sklearn.model_selection import train_test_split
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, r2_score
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed)
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_train)
    return {
        "model": "ridge_baseline",
        "train_mae": float(mean_absolute_error(y_train, y_pred)),
        "train_r2": float(r2_score(y_train, y_pred)),
        "feature_cols": feature_cols,
        "note": "Ridge baseline with alpha=1.0. Included as an alternative regularized model.",
    }
