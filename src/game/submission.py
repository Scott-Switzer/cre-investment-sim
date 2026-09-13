"""
Student model output contract for the live game.

Students build their model OUTSIDE the game (Excel / Python / R / anything) and
upload a prediction CSV before play. This module is the single authoritative
definition of that contract, plus validation and conversion into the
:class:`~src.game.adjudicator.ModelPrediction` objects the adjudicator uses.

The game never computes these predictions. It only *displays* what the team's own
model said, so that the analytical work drives the decision.

Required columns
----------------
team_id, property_id, model_name, predicted_fair_value, predicted_noi_growth,
probability_of_downside, max_bid, target_ltv

Optional columns
----------------
predicted_noi, predicted_exit_cap, confidence, notes, model_version

Units: money columns are in **millions of dollars**; rates and probabilities are
**decimals** (0.03 == 3%).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

import numpy as np
import pandas as pd

from src.game.adjudicator import ModelPrediction

REQUIRED_COLUMNS: List[str] = [
    "team_id",
    "property_id",
    "model_name",
    "predicted_fair_value",
    "predicted_noi_growth",
    "probability_of_downside",
    "max_bid",
    "target_ltv",
]

OPTIONAL_COLUMNS: List[str] = [
    "predicted_noi",
    "predicted_exit_cap",
    "confidence",
    "notes",
    "model_version",
]

ALL_COLUMNS: List[str] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Explicit, auditable numeric bounds. These are game rules, not heuristics.
MAX_TARGET_LTV = 0.95
MIN_NOI_GROWTH = -0.50
MAX_NOI_GROWTH = 0.50
MAX_PLAUSIBLE_FAIR_VALUE = 5_000.0  # $5bn per asset, in millions


@dataclass
class SubmissionValidation:
    """Result of validating a student model submission."""

    ok: bool
    errors: List[str]
    warnings: List[str]
    stats: Dict[str, float]
    teams: List[str]
    properties_covered: int
    unknown_property_ids: List[str]

    def summary(self) -> str:
        lines = [
            f"Valid: {self.ok}",
            f"Teams: {len(self.teams)} {self.teams}",
            f"Rows: {int(self.stats.get('rows', 0))}",
            f"Properties covered: {self.properties_covered}",
        ]
        if self.errors:
            lines.append("Errors: " + "; ".join(self.errors))
        if self.warnings:
            lines.append("Warnings: " + "; ".join(self.warnings))
        return "\n".join(lines)


def validate_game_submission(
    df: pd.DataFrame,
    valid_property_ids: Optional[Iterable[str]] = None,
    *,
    max_target_ltv: float = MAX_TARGET_LTV,
) -> SubmissionValidation:
    """Validate a student prediction submission against the game contract.

    ``valid_property_ids`` is the set of property ids the game can actually offer.
    When supplied, every submitted ``property_id`` must appear in it -- this is
    what stops a student from modelling a dataset that the game never uses.

    Validation deliberately reports *structural* facts only. It must never reveal
    whether the predictions are accurate; accuracy is only revealed as rounds
    resolve.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(df, pd.DataFrame):
        return SubmissionValidation(
            ok=False,
            errors=["Submission must be a pandas DataFrame"],
            warnings=[],
            stats={},
            teams=[],
            properties_covered=0,
            unknown_property_ids=[],
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing required column(s): {', '.join(missing)}")
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            warnings.append(f"Optional column absent: {col}")

    if errors:
        return SubmissionValidation(
            ok=False,
            errors=errors,
            warnings=warnings,
            stats={"rows": float(len(df))},
            teams=[],
            properties_covered=0,
            unknown_property_ids=[],
        )

    # --- null checks -----------------------------------------------------
    for col in REQUIRED_COLUMNS:
        if df[col].isna().any():
            errors.append(f"{col} must not contain nulls ({int(df[col].isna().sum())} found)")

    # --- numeric coercion & finiteness -----------------------------------
    numeric_cols = [
        "predicted_fair_value",
        "predicted_noi_growth",
        "probability_of_downside",
        "max_bid",
        "target_ltv",
    ]
    coerced: Dict[str, pd.Series] = {}
    for col in numeric_cols:
        try:
            coerced[col] = pd.to_numeric(df[col], errors="raise").astype(float)
        except (ValueError, TypeError):
            errors.append(f"{col} must be numeric")
    if errors:
        return SubmissionValidation(
            ok=False,
            errors=errors,
            warnings=warnings,
            stats={"rows": float(len(df))},
            teams=sorted({str(t) for t in df.get("team_id", [])}),
            properties_covered=0,
            unknown_property_ids=[],
        )

    for col, series in coerced.items():
        if not np.isfinite(series.to_numpy()).all():
            errors.append(f"{col} contains non-finite values")

    # --- range checks ----------------------------------------------------
    fv = coerced["predicted_fair_value"]
    if (fv <= 0).any():
        errors.append("predicted_fair_value must be > 0 for every row")
    if (fv > MAX_PLAUSIBLE_FAIR_VALUE).any():
        errors.append(f"predicted_fair_value above plausible cap (${MAX_PLAUSIBLE_FAIR_VALUE:,.0f}M)")
    if (coerced["max_bid"] <= 0).any():
        errors.append("max_bid must be > 0 for every row")
    if (coerced["max_bid"] > MAX_PLAUSIBLE_FAIR_VALUE).any():
        errors.append(f"max_bid above plausible cap (${MAX_PLAUSIBLE_FAIR_VALUE:,.0f}M)")

    pod = coerced["probability_of_downside"]
    if ((pod < 0) | (pod > 1)).any():
        errors.append("probability_of_downside must be in [0, 1]")

    ltv = coerced["target_ltv"]
    if (ltv <= 0).any() or (ltv > max_target_ltv).any():
        errors.append(f"target_ltv must be in (0, {max_target_ltv}]")

    growth = coerced["predicted_noi_growth"]
    if ((growth < MIN_NOI_GROWTH) | (growth > MAX_NOI_GROWTH)).any():
        errors.append(
            f"predicted_noi_growth must be between {MIN_NOI_GROWTH} and {MAX_NOI_GROWTH}"
        )

    if "confidence" in df.columns:
        conf = pd.to_numeric(df["confidence"], errors="coerce")
        if conf.notna().any() and ((conf.dropna() < 0) | (conf.dropna() > 1)).any():
            errors.append("confidence must be in [0, 1]")
    if "predicted_exit_cap" in df.columns:
        cap = pd.to_numeric(df["predicted_exit_cap"], errors="coerce")
        if cap.notna().any() and ((cap.dropna() <= 0) | (cap.dropna() > 0.5)).any():
            errors.append("predicted_exit_cap must be in (0, 0.5]")

    # --- duplicate team/property pairs -----------------------------------
    dupes = df.duplicated(subset=["team_id", "property_id"], keep=False)
    if dupes.any():
        sample = df.loc[dupes, ["team_id", "property_id"]].head(3).to_dict("records")
        errors.append(f"Duplicate team_id/property_id rows ({int(dupes.sum())}), e.g. {sample}")

    # --- unknown property ids --------------------------------------------
    unknown: List[str] = []
    if valid_property_ids is not None:
        valid = {str(p) for p in valid_property_ids}
        submitted = {str(p) for p in df["property_id"].unique()}
        unknown = sorted(submitted - valid)
        if unknown:
            errors.append(
                f"{len(unknown)} unknown property_id value(s) not offered by the game: "
                f"{unknown[:5]}{'...' if len(unknown) > 5 else ''}"
            )

    # --- strategy warnings (not errors: overriding your own model is allowed)
    above = (coerced["max_bid"] > fv).sum()
    if above:
        warnings.append(
            f"{int(above)} row(s) have max_bid above your own predicted_fair_value"
        )

    teams = sorted({str(t) for t in df["team_id"].unique()})
    stats = {
        "rows": float(len(df)),
        "teams": float(len(teams)),
        "avg_predicted_fair_value": float(fv.mean()),
        "avg_max_bid": float(coerced["max_bid"].mean()),
        "avg_target_ltv": float(ltv.mean()),
        "avg_probability_of_downside": float(pod.mean()),
        "avg_noi_growth": float(growth.mean()),
    }

    return SubmissionValidation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        teams=teams,
        properties_covered=int(df["property_id"].nunique()),
        unknown_property_ids=unknown,
    )


def to_model_predictions(
    df: pd.DataFrame,
    team_id: Optional[str] = None,
) -> Dict[str, ModelPrediction]:
    """Convert an (already validated) submission into adjudicator predictions.

    If ``team_id`` is given, only that team's rows are converted. This is the
    privacy boundary: a team only ever receives its own model predictions.
    """
    frame = df
    if team_id is not None:
        frame = df[df["team_id"].astype(str) == str(team_id)]

    predictions: Dict[str, ModelPrediction] = {}
    for _, row in frame.iterrows():
        pid = str(row["property_id"])
        predictions[pid] = ModelPrediction(
            property_id=pid,
            predicted_fair_value=float(row["predicted_fair_value"]),
            predicted_noi_growth=float(row["predicted_noi_growth"]),
            probability_of_downside=(
                float(row["probability_of_downside"])
                if pd.notna(row.get("probability_of_downside"))
                else None
            ),
            max_bid=float(row["max_bid"]),
            target_ltv=float(row["target_ltv"]),
            model_name=str(row.get("model_name", "student model")),
            confidence=(
                float(row["confidence"]) if pd.notna(row.get("confidence")) else None
            ),
            predicted_exit_cap=(
                float(row["predicted_exit_cap"])
                if pd.notna(row.get("predicted_exit_cap"))
                else None
            ),
        )
    return predictions


def load_submission(path: str, team_id: Optional[str] = None) -> Dict[str, ModelPrediction]:
    """Load a prediction CSV from disk and convert it for one team."""
    return to_model_predictions(pd.read_csv(path), team_id=team_id)
