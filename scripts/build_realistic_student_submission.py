#!/usr/bin/env python3
"""
Build a realistic student submission from the packet — the authentic workflow.

This script does exactly what a REAL 605 student is asked to do, using nothing
but the files in ``student_packet/``:

    1. open the historical training data
    2. engineer features a CRE analyst would actually use
    3. fit a model, validated out of time
    4. predict fair value for every game candidate
    5. turn the forecast into an investment POLICY (max_bid, ltv, downside)
    6. fill in the official submission template
    7. save the CSV

The output is the fixture the test suite loads through the real Model Check-In
validator, so the "student path" is exercised by the same contract students use,
not by a shortcut into the game engine.

Run:

    uv run python scripts/build_realistic_student_submission.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score

from src.game.submission import validate_game_submission

REPO = Path(__file__).resolve().parent.parent
PACKET = REPO / "student_packet"
OUT = REPO / "tests" / "fixtures" / "student_submission_realistic.csv"

TEAM_ID = "REAL605 Student Fund"
MODEL_NAME = "student_gbm_v1"

# The student's stated policy, decided BEFORE seeing the game.
REQUIRED_MARGIN = 0.03   # never pay more than 3% below my own valuation
POLICY_MAX_LTV = 0.60    # discipline: below the lender maximum on every asset

FEATURES = [
    "noi",
    "occupancy",
    "going_in_cap",
    "opex_ratio",
    "walt",
    "tenant_concentration",
    "capex_need",
    "property_quality",
    "market_rent",
    "in_place_rent",
    "building_sf",
    "year_built",
    "employment_density",
    "treasury_rate",
    "market_vacancy",
]


def engineer(frame: pd.DataFrame) -> pd.DataFrame:
    """Features that encode the structure of a real estate valuation."""
    f = pd.DataFrame(index=frame.index)
    for col in FEATURES:
        f[col] = pd.to_numeric(frame[col], errors="coerce")

    f["noi_over_cap"] = f["noi"] / f["going_in_cap"].replace(0, np.nan)
    f["cap_vs_treasury"] = f["going_in_cap"] - f["treasury_rate"]
    f["rent_spread"] = f["in_place_rent"] / f["market_rent"].replace(0, np.nan) - 1.0
    f["occupancy_gap"] = 1.0 - f["occupancy"]
    f["noi_per_sf"] = f["noi"] * 1e6 / f["building_sf"].clip(lower=1)
    f["age"] = 2026 - f["year_built"]
    f["lease_risk"] = f["tenant_concentration"] / f["walt"].clip(lower=0.1)
    f["vacancy_burden"] = f["market_vacancy"] * f["occupancy_gap"]
    f["quality_x_occ"] = f["property_quality"] * f["occupancy"]

    for ptype in sorted(frame["property_type"].unique()):
        f[f"is_{ptype}"] = (frame["property_type"] == ptype).astype(float)

    return f.fillna(0.0)


def main() -> int:
    hist = pd.read_csv(PACKET / "historical_training.csv")
    cand = pd.read_csv(PACKET / "game_candidates.csv")
    vintages = sorted(hist["date"].unique())

    # ── validate out of time, so the student knows how much to trust the model
    train = hist[hist["date"] != vintages[-1]]
    test = hist[hist["date"] == vintages[-1]]
    holdout = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=6, random_state=605
    ).fit(engineer(train), train["next_year_value"])

    pred_holdout = holdout.predict(engineer(test))
    actual_holdout = test["next_year_value"].to_numpy(float)
    resid = pred_holdout - actual_holdout
    sigma = float(np.std(resid))
    holdout_mae = float(np.mean(np.abs(resid)))
    print("Out-of-time check (last vintage held back):")
    print(f"  MAE  ${holdout_mae:.3f}M   R2 {r2_score(actual_holdout, pred_holdout):.4f}   "
          f"residual sigma ${sigma:.3f}M")

    # ── refit on ALL available history to predict the live candidates
    model = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=6, random_state=605
    ).fit(engineer(hist), hist["next_year_value"])

    growth_model = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=6, random_state=605
    ).fit(engineer(hist), hist["noi_growth_realized"])

    fv = model.predict(engineer(cand))
    growth = growth_model.predict(engineer(cand))

    # ── convert forecast into policy
    ask = cand["asking_price"].to_numpy(float)
    max_bid = fv * (1.0 - REQUIRED_MARGIN)

    # Probability the property underperforms: P(next-year value < asking price),
    # using the model's own out-of-time error distribution. This is a normal
    # approximation of the forecast error, which is how an analyst would state it.
    from scipy.stats import norm

    pod = norm.cdf((ask - fv) / sigma) if sigma > 0 else np.full_like(fv, 0.5)
    pod = np.clip(pod, 0.01, 0.99)

    ltv = np.minimum(POLICY_MAX_LTV, cand["max_ltv"].to_numpy(float))

    submission = pd.DataFrame(
        {
            "team_id": TEAM_ID,
            "property_id": cand["property_id"].to_numpy(),
            "model_name": MODEL_NAME,
            "predicted_fair_value": np.round(fv, 4),
            "predicted_noi_growth": np.round(growth, 5),
            "probability_of_downside": np.round(pod, 4),
            "max_bid": np.round(max_bid, 4),
            "target_ltv": np.round(ltv, 4),
            "predicted_noi": np.round(cand["noi"].to_numpy(float) * (1 + growth), 4),
            "confidence": np.round(1.0 - pod, 4),
            "model_version": "1.0",
            "notes": "GBM on engineered CRE features; 3% required margin; 60% LTV cap",
        }
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    submission.to_csv(OUT, index=False)

    # ── validate through the REAL contract the app enforces
    valid_ids = cand["property_id"].astype(str).tolist()
    result = validate_game_submission(submission, valid_property_ids=valid_ids)

    print(f"\nWrote {len(submission)} predictions -> "
          f"{OUT.relative_to(REPO)}")
    print("Validated with the live-game contract:")
    print(result.summary())
    for key in (
        "avg_predicted_fair_value",
        "avg_max_bid",
        "avg_target_ltv",
        "avg_probability_of_downside",
        "avg_noi_growth",
    ):
        print(f"  {key:<30} {result.stats[key]:.4f}")

    # Sanity: the policy must be internally consistent, or the game will reject it.
    assert result.ok, f"submission failed validation: {result.errors}"
    assert (submission["max_bid"] <= submission["predicted_fair_value"]).all()
    assert (submission["target_ltv"] <= POLICY_MAX_LTV + 1e-9).all()
    assert submission["property_id"].nunique() == len(submission)
    print("\nSTUDENT SUBMISSION = VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
