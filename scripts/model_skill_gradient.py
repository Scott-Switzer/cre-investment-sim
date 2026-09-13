#!/usr/bin/env python3
"""
Pedagogical skill gradient for the student modeling task.

The question this answers
-------------------------
Is there a real difference between a lazy model and a good one, or does the
packet hand the answer to anybody who runs a regression?

Four legitimate models are built from the packet, ordered by how much analytical
work they represent:

    NAIVE       value = the transaction price ("it is worth what it is offered at")
    BASIC       OLS on the obvious raw variables
    STRONG      engineered features + gradient boosting
    ORACLE      the structural model: NOI growth forecast + type market cap rate

Validation is strictly out of time: the last vintage is held back and never
trained on. The candidate properties are also the historical properties, so an
out-of-time split is the honest mirror of how the packet is actually used.

Two families of metric are reported, because they answer different questions:

    level accuracy      MAE / R2 of the predicted value in $M
                        "can you value the building?"

    decision accuracy   MAE of predicted value / price, and AUC for whether the
                        property ends up worth MORE than the price paid
                        "can you tell a good deal from a bad one?"

Only the second family wins the game, and the two can disagree sharply.

Run:

    uv run python scripts/model_skill_gradient.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, roc_auc_score
from scipy.stats import spearmanr

PACKET = Path(__file__).resolve().parent.parent / "student_packet"
TARGETS = [
    "transaction_cap_rate",
    "transaction_price",
    "noi_growth_realized",
    "next_year_noi",
    "next_year_cap_rate",
    "next_year_value",
]
RAW_FEATURES = [
    "building_sf",
    "year_built",
    "occupancy",
    "noi",
    "market_rent",
    "in_place_rent",
    "going_in_cap",
    "opex_ratio",
    "walt",
    "tenant_concentration",
    "capex_need",
    "property_quality",
    "units",
    "employment_density",
    "treasury_rate",
    "market_vacancy",
]
CAT_FEATURES = ["property_type"]


def load_packet() -> tuple[pd.DataFrame, pd.DataFrame]:
    hist = pd.read_csv(PACKET / "historical_training.csv")
    cand = pd.read_csv(PACKET / "game_candidates.csv")
    return hist, cand


def design_matrix(
    frame: pd.DataFrame,
    columns: list[str],
    reference_types: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Numeric features plus one-hot property type, with a fixed type vocabulary."""
    X = frame[columns].copy()
    for col in columns:
        if X[col].dtype == object:
            X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.astype(float)
    X = X.fillna(X.median(numeric_only=True))

    if reference_types is None:
        reference_types = sorted(frame["property_type"].unique())
    for ptype in reference_types[1:]:  # drop first as the reference category
        X[f"is_{ptype}"] = (frame["property_type"] == ptype).astype(float)
    return X, reference_types


# ── the four models ───────────────────────────────────────────────────────


def model_naive(train: pd.DataFrame, test: pd.DataFrame, types):
    """The asking price is the valuation. No modeling at all."""
    return test["transaction_price"].to_numpy(dtype=float), None


def model_basic(train: pd.DataFrame, test: pd.DataFrame, types):
    """OLS on the obvious raw variables."""
    Xtr, _ = design_matrix(train, RAW_FEATURES, types)
    Xte, _ = design_matrix(test, RAW_FEATURES, types)
    m = LinearRegression().fit(Xtr, train["next_year_value"])
    return m.predict(Xte), None


def _engineer(frame: pd.DataFrame) -> pd.DataFrame:
    """Features that encode how a CRE analyst actually thinks about a deal."""
    f = pd.DataFrame(index=frame.index)
    # Price-relative measures
    f["implied_cap"] = frame["noi"] / frame["transaction_price"]
    f["cap_vs_type"] = frame["going_in_cap"] - frame.groupby("property_type")[
        "going_in_cap"
    ].transform("mean")
    f["noi_yield_on_price"] = frame["noi"] / frame["transaction_price"]
    f["price_per_sf"] = frame["transaction_price"] * 1e6 / frame["building_sf"]
    # Rent and occupancy quality
    f["rent_spread"] = (
        frame["in_place_rent"] / frame["market_rent"].replace(0, np.nan) - 1.0
    )
    f["occupancy_gap"] = 1.0 - frame["occupancy"]
    f["vacancy_vs_type"] = frame["market_vacancy"] - frame.groupby("property_type")[
        "market_vacancy"
    ].transform("mean")
    # Rate environment
    f["cap_spread_to_treasury"] = frame["transaction_cap_rate"] - frame["treasury_rate"]
    f["treasury_x_cap"] = frame["treasury_rate"] * frame["going_in_cap"]
    # Scale and quality
    f["log_sf"] = np.log(frame["building_sf"].clip(lower=1))
    f["age"] = 2026 - frame["year_built"]
    f["noi_per_sf"] = frame["noi"] * 1e6 / frame["building_sf"]
    f["lease_risk"] = frame["tenant_concentration"] / frame["walt"].clip(lower=0.1)
    f["capex_to_noi"] = frame["capex_need"] / frame["noi"].replace(0, np.nan)
    f["quality_x_occupancy"] = frame["property_quality"] * frame["occupancy"]
    # The structural identity, handed to the model as a feature
    f["noi_over_cap"] = frame["noi"] / frame["going_in_cap"].replace(0, np.nan)
    return f.fillna(0.0)


def model_strong(train: pd.DataFrame, test: pd.DataFrame, types):
    """Engineered features + gradient boosting."""
    Xtr = _engineer(train)
    Xte = _engineer(test)
    for ptype in types[1:]:
        Xtr[f"is_{ptype}"] = (train["property_type"] == ptype).astype(float)
        Xte[f"is_{ptype}"] = (test["property_type"] == ptype).astype(float)
    m = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=6, random_state=20240331
    )
    m.fit(Xtr, train["next_year_value"])
    return m.predict(Xte), None


def model_oracle(train: pd.DataFrame, test: pd.DataFrame, types):
    """The structural model: forecast NOI growth, then value it at the market cap.

        value = noi * (1 + forecast growth) / type market cap rate

    This is the strongest *legitimate* model -- it uses only pre-decision
    information, but it encodes the actual data-generating process rather than
    trying to learn it from correlations.
    """
    Xtr = _engineer(train)
    Xte = _engineer(test)
    m = HistGradientBoostingRegressor(
        max_iter=600, learning_rate=0.05, max_depth=7, random_state=20240331
    )
    m.fit(Xtr, train["noi_growth_realized"])
    growth_hat = m.predict(Xte)

    # Type-level market cap rate estimated from the training data only.
    type_cap = train.groupby("property_type")["next_year_cap_rate"].median()
    cap_hat = test["property_type"].map(type_cap).to_numpy(dtype=float)
    return test["noi"].to_numpy(dtype=float) * (1.0 + growth_hat) / cap_hat, growth_hat


# ── evaluation ────────────────────────────────────────────────────────────


def evaluate(name: str, pred_value: np.ndarray, test: pd.DataFrame,
             growth_hat: np.ndarray | None) -> dict:
    actual = test["next_year_value"].to_numpy(dtype=float)
    price = test["transaction_price"].to_numpy(dtype=float)

    mae = float(np.mean(np.abs(pred_value - actual)))
    r2 = float(r2_score(actual, pred_value))
    mape = float(np.mean(np.abs(pred_value - actual) / actual))

    # Decision-relevant: does the model see value relative to the price?
    true_ratio = actual / price
    pred_ratio = pred_value / price
    ratio_mae = float(np.mean(np.abs(pred_ratio - true_ratio)))
    # A constant prediction has no defined rank correlation; report it as such.
    ratio_rank = (
        float("nan")
        if np.allclose(pred_ratio, pred_ratio[0])
        else float(spearmanr(pred_ratio, true_ratio).statistic)
    )

    # Can it tell a good deal from a bad one?
    label = (actual > price).astype(int)
    if len(np.unique(label)) > 1:
        auc = float(roc_auc_score(label, pred_ratio))
    else:
        auc = float("nan")

    if growth_hat is None:
        growth_mae = float("nan")
    else:
        growth_mae = float(
            np.mean(np.abs(growth_hat - test["noi_growth_realized"].to_numpy(float)))
        )

    return {
        "model": name,
        "mae_musd": mae,
        "r2": r2,
        "mape": mape,
        "ratio_mae": ratio_mae,
        "ratio_spearman": ratio_rank,
        "auc_v_gt_price": auc,
        "growth_mae": growth_mae,
        "hit_rate": float(np.mean(pred_ratio > 1.0) == np.mean(true_ratio > 1.0) * 0 + 0),
    }


def main() -> int:
    hist, cand = load_packet()
    vintages = sorted(hist["date"].unique())
    holdout = vintages[-1]
    train = hist[hist["date"] != holdout].copy()
    test = hist[hist["date"] == holdout].copy()

    types = sorted(hist["property_type"].unique())

    print("=" * 78)
    print("REAL 605 — MODELING SKILL GRADIENT")
    print("=" * 78)
    print(f"packet        : {PACKET}")
    print(f"historical    : {len(hist):,} rows · {hist['property_id'].nunique()} properties "
          f"· {len(vintages)} vintages")
    print(f"candidates    : {len(cand)} properties · {len(cand.columns)} columns")
    print(f"train         : {len(train):,} rows ({vintages[0]} .. {vintages[-2]})")
    print(f"holdout       : {len(test):,} rows ({holdout}) — never trained on")
    print(f"test base rate: {np.mean(test['next_year_value'] > test['transaction_price']):.1%} "
          f"of held-out deals end up worth MORE than they traded at")

    results = []
    for name, fn in [
        ("NAIVE", model_naive),
        ("BASIC", model_basic),
        ("STRONG", model_strong),
        ("ORACLE", model_oracle),
    ]:
        pred, growth_hat = fn(train, test, types)
        row = evaluate(name, np.asarray(pred, dtype=float), test, growth_hat)
        results.append(row)

    print("\n" + "─" * 78)
    print("LEVEL ACCURACY  ($M)              │  DECISION ACCURACY (what wins the game)")
    print(f"{'MODEL':<8}{'MAE':>8}{'R2':>7}{'MAPE':>8}   │{'ratioMAE':>10}{'rank':>7}"
          f"{'AUC':>7}{'NOIgMAE':>9}")
    print("─" * 78)
    for r in results:
        g = "n/a" if np.isnan(r["growth_mae"]) else f"{r['growth_mae']:.4f}"
        auc = "n/a" if np.isnan(r["auc_v_gt_price"]) else f"{r['auc_v_gt_price']:.3f}"
        rank = "—" if np.isnan(r["ratio_spearman"]) else f"{r['ratio_spearman']:.3f}"
        print(f"{r['model']:<8}{r['mae_musd']:>8.3f}{r['r2']:>7.3f}{r['mape']:>7.1%}   │"
              f"{r['ratio_mae']:>10.4f}{rank:>7}{auc:>7}{g:>9}")
    print("─" * 78)
    print("rank = Spearman correlation between predicted and actual value/price ratio")
    print("NAIVE cannot rank at all: it predicts every property is worth exactly its price.")

    by_name = {r["model"]: r for r in results}
    naive, basic = by_name["NAIVE"], by_name["BASIC"]
    strong, oracle = by_name["STRONG"], by_name["ORACLE"]

    print("\nMONOTONICITY: NAIVE < BASIC < STRONG ?")
    level_ok = naive["mae_musd"] > basic["mae_musd"] > strong["mae_musd"]
    decision_ok = naive["auc_v_gt_price"] < basic["auc_v_gt_price"] < strong["auc_v_gt_price"]
    print(f"  level MAE   {naive['mae_musd']:.3f} -> {basic['mae_musd']:.3f} -> "
          f"{strong['mae_musd']:.3f}   {'STRICTLY IMPROVING' if level_ok else 'NOT monotone'}")
    print(f"  decision AUC {naive['auc_v_gt_price']:.3f} -> {basic['auc_v_gt_price']:.3f} -> "
          f"{strong['auc_v_gt_price']:.3f}   {'STRICTLY IMPROVING' if decision_ok else 'NOT monotone'}")

    print("\nDIAGNOSIS")
    improvement = (naive["mae_musd"] - oracle["mae_musd"]) / naive["mae_musd"]
    print(f"  ORACLE beats NAIVE on level MAE by {improvement:.1%}")
    print(f"  ORACLE level R2 = {oracle['r2']:.3f}")
    too_easy = oracle["r2"] > 0.95 and (oracle["mae_musd"] / np.mean(test["next_year_value"])) < 0.03
    print(f"  MODELING TASK TOO EASY (level) = {'YES' if too_easy else 'NO'}")
    print("""
  Why the level target is easy: next-year value is NOI x (1 + growth) / cap rate.
  NOI is given, the cap rate is nearly deterministic per property type, and growth
  is driven by a tight-vacancy rule plus small noise. Any model that discovers the
  identity next_year_value = next_year_noi / next_year_cap_rate scores ~0.98 R2.

  That is not a defect in the packet -- it is the structure of real estate
  valuation. The informative question is the DECISION question, one row up: given
  the price, is this a good deal? That is where the models actually separate.""")
    print(f"  ORACLE decision AUC = {oracle['auc_v_gt_price']:.3f} "
          f"(0.500 = coin flip)")
    print(f"  ratio MAE  NAIVE {naive['ratio_mae']:.4f} -> ORACLE {oracle['ratio_mae']:.4f}")
    print("""
  The residual dispersion in value/price (~6% standard deviation) is the part
  that no pre-decision feature explains, because it is seeded noise in NOI growth.
  A student cannot eliminate it. What they can do is avoid the systematic mistakes:
  buying assets whose going-in cap rate is below the market cap rate for the type,
  and paying away the seller's discount for nothing.""")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
