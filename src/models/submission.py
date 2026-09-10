"""
Model prediction submission.

Students (or future automated pipelines) can submit predictions as a CSV with:
property_id, predicted_value, predicted_noi, optional probability_of_loss, model_name, model_version

Validation checks schema and ranges. Scoring compares submitted predictions to actuals where available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd
import numpy as np

from src.scoring.metrics import mae, mape, forecast_value_error, forecast_noi_error


@dataclass
class PredictionSubmission:
    property_id: str
    predicted_value: float
    predicted_noi: float
    probability_of_loss: Optional[float]
    model_name: str
    model_version: str
    submitted_at: str


REQUIRED_COLUMNS = ["property_id", "predicted_value", "predicted_noi", "model_name", "model_version"]
OPTIONAL_COLUMNS = ["probability_of_loss"]


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
    if "probability_of_loss" in df.columns:
        p = df["probability_of_loss"]
        if ((p < 0) | (p > 1)).any():
            errors.append("probability_of_loss must be in [0, 1]")
    # Ensure property_ids look plausible
    if df["property_id"].isna().any():
        errors.append("property_id must not be null")
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
