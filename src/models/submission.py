"""
Model prediction submission.

Students (or future automated pipelines) can submit predictions as a CSV with:
property_id, predicted_value, predicted_noi, optional probability_of_loss, model_name, model_version

Validation checks schema and ranges. Scoring compares submitted predictions to actuals where available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from src.scoring.metrics import mae, mape, forecast_value_error, forecast_noi_error


@dataclass
class PredictionSubmission:
    property_id: str
    predicted_value: float
    predicted_noi: float
    predicted_noi_growth: float
    probability_of_downside: Optional[float]
    max_bid: float
    target_ltv: float
    model_name: str
    model_version: str
    submitted_at: str
    team_id: Optional[str] = None
    confidence: Optional[float] = None
    predicted_exit_cap: Optional[float] = None
    notes: Optional[str] = None


REQUIRED_COLUMNS = ["property_id", "predicted_value", "predicted_noi", "predicted_noi_growth", "max_bid", "target_ltv", "model_name", "model_version"]
OPTIONAL_COLUMNS = ["probability_of_downside", "confidence", "predicted_exit_cap", "notes", "team_id"]


def validate_submission(df: pd.DataFrame) -> Dict:
    """Validate a prediction submission CSV. Returns a dict with 'ok', 'errors', 'warnings'."""
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(df, pd.DataFrame):
        return {"ok": False, "errors": ["Submission must be a DataFrame"], "warnings": []}
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            errors.append(f"Missing required column: {col}")
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            warnings.append(f"Optional column missing: {col} (will be treated as None)")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    # Basic range checks
    if (df["predicted_value"] <= 0).any():
        errors.append("predicted_value must be > 0 for all rows")
    if (df["predicted_noi"] <= 0).any():
        errors.append("predicted_noi must be > 0 for all rows")
    if (df["predicted_noi_growth"] < -0.5).any() or (df["predicted_noi_growth"] > 0.5).any():
        errors.append("predicted_noi_growth must be between -0.5 and 0.5 for all rows")
    if (df["max_bid"] <= 0).any():
        errors.append("max_bid must be > 0 for all rows")
    if (df["target_ltv"] <= 0).any() or (df["target_ltv"] > 0.95).any():
        errors.append("target_ltv must be between 0 and 0.95 for all rows")
    if "probability_of_downside" in df.columns:
        p = df["probability_of_downside"]
        if ((p < 0) | (p > 1)).any():
            errors.append("probability_of_downside must be in [0, 1]")
    if "confidence" in df.columns:
        c = df["confidence"]
        if ((c < 0) | (c > 1)).any():
            errors.append("confidence must be in [0, 1]")
    # Ensure property_ids look plausible
    if df["property_id"].isna().any():
        errors.append("property_id must not be null")
    # Check for duplicate property_ids within submission
    if df["property_id"].duplicated().any():
        errors.append("property_id must be unique within submission")
    return {"ok": True, "errors": errors, "warnings": warnings}


def score_submission_predictions(
    submission: pd.DataFrame,
    actuals: pd.DataFrame,
) -> pd.DataFrame:
    """
    Score a submission against actual outcomes.

    actuals columns: property_id, exit_value, exit_noi, exit_cap, noi_growth_actual,
                     levered_return, decision, probability_of_loss_actual (0/1)
    Returns a DataFrame with per-property forecast scores.
    """
    m = submission.merge(actuals, on="property_id", how="left")
    m["value_mape"] = m.apply(lambda r: forecast_value_error(r["exit_value"], r["predicted_value"]) if pd.notna(r["exit_value"]) else np.nan, axis=1)
    m["noi_mape"] = m.apply(lambda r: forecast_noi_error(r["exit_noi"], r["predicted_noi"]) if pd.notna(r["exit_noi"]) else np.nan, axis=1)
    m["value_abs_error_mm"] = m.apply(lambda r: mae(r["exit_value"], r["predicted_value"]) if pd.notna(r["exit_value"]) else np.nan, axis=1)
    m["noi_abs_error_mm"] = m.apply(lambda r: mae(r["exit_noi"], r["predicted_noi"]) if pd.notna(r["exit_noi"]) else np.nan, axis=1)
    if "probability_of_loss" in m.columns:
        m["brier_loss"] = m.apply(lambda r: (r["probability_of_loss"] - r.get("probability_of_loss_actual", 0)) ** 2 if pd.notna(r.get("probability_of_loss_actual")) and pd.notna(r["probability_of_loss"]) else np.nan, axis=1)
    return m
