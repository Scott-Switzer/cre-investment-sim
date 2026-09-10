"""
Scoring metrics.

Implements transparent scoring aligned to the brief:
- Forecast accuracy (MAE / MAPE, Brier for probability-of-loss)
- Risk discipline (DSCR, LTV, concentration)
- Decision quality (choice vs expected outcome given hidden model BEFORE realization)
- Outcome quality (realized financial performance)
- Process quality (point-in-time data use, no leakage)

Decision-quality scoring compares the choice with EXPECTED outcomes based on the
hidden probability model available BEFORE realization, to avoid rewarding only the
stochastic outcome that happened to occur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import math

from src.scoring.weights import load_weights


@dataclass
class Scorecard:
    round_index: int
    property_id: str
    decision: str
    financial_score: float
    forecast_score: float
    risk_score: float
    decision_score: float
    process_score: float
    total_score: float
    weights: Dict[str, float]
    details: Dict


def brier_score(predicted_prob: float, outcome: int) -> float:
    """Brier score for a binary event. Lower is better."""
    if predicted_prob is None or math.isnan(predicted_prob):
        return 0.25  # uninformative prior baseline (0.5 probability)
    p = max(0.0, min(1.0, float(predicted_prob)))
    return round((p - outcome) ** 2, 6)


def mae(actual: float, predicted: float) -> float:
    return round(abs(actual - predicted), 6)


def mape(actual: float, predicted: float, cap: float = 1.0) -> float:
    if abs(actual) < 1e-9:
        return 0.0 if abs(predicted) < 1e-9 else cap
    raw = abs((actual - predicted) / actual)
    return round(min(cap, raw), 6)


def forecast_value_error(actual_value: float, predicted_value: float, cap: float = 0.5) -> float:
    return mape(actual_value, predicted_value, cap=cap)


def forecast_noi_error(actual_noi: float, predicted_noi: float, cap: float = 0.5) -> float:
    return mape(actual_noi, predicted_noi, cap=cap)


def forecast_cap_error(actual_cap: float, predicted_cap: float, cap: float = 0.5) -> float:
    return mape(actual_cap, predicted_cap, cap=cap)


def forecast_quality_score(
    actual_value: float,
    predicted_value: float,
    actual_noi: float,
    predicted_noi: float,
    actual_cap: float,
    predicted_cap: float,
    mape_cap: float = 0.5,
) -> float:
    """
    Forecast accuracy score on a 0–100 scale.
    Combines value, NOI, and cap-rate forecast accuracy.
    """
    ve = forecast_value_error(actual_value, predicted_value, cap=mape_cap)
    ne = forecast_noi_error(actual_noi, predicted_noi, cap=mape_cap)
    ce = forecast_cap_error(actual_cap, predicted_cap, cap=mape_cap)
    # average percentage error, then convert to 0–100 where 0% error => 100
    avg_err = (ve + ne + ce) / 3.0
    score = max(0.0, 100.0 * (1.0 - avg_err))
    return round(score, 6)


def outcome_quality_score(
    actual_levered_return: float,
    required_return: float,
    hurdle_buffer: float = 0.20,
) -> float:
    """
    Outcome quality: how the realized return compares to the required return.
    Scales linearly between (required - buffer) => 0 and (required + buffer) => 100.
    """
    lo = required_return - hurdle_buffer
    hi = required_return + hurdle_buffer
    if actual_levered_return is None or math.isnan(actual_levered_return):
        return 50.0  # no outcome / pass
    r = max(lo, min(hi, actual_levered_return))
    return round(100.0 * (r - lo) / (hi - lo), 6)


def expected_levered_return_from_world(
    current_noi: float,
    current_cap: float,
    debt_rate: float,
    amortization_years: int,
    bid: float,
    ltv: float,
    world_noi_growth: float,
    world_cap_delta: float,
) -> float:
    """
    Compute the EXPECTED levered return from the hidden world-state parameters
    BEFORE realization, to support decision-quality scoring without hindsight bias.
    """
    from src.finance.calculations import (
        loan_amount,
        annual_debt_service,
        dscr,
        property_value_from_noi,
        levered_equity_return,
    )
    loan = loan_amount(bid, ltv)
    equity = bid - loan
    if equity <= 0:
        return float("nan")
    ds = annual_debt_service(loan, debt_rate, amortization_years)
    exit_noi = current_noi * (1.0 + world_noi_growth)
    exit_cap = max(0.03, current_cap + world_cap_delta)
    exit_value = property_value_from_noi(exit_noi, exit_cap)
    cf = exit_noi - ds
    return levered_equity_return(exit_value, cf, equity, loan)


def decision_quality_score(
    decision: str,
    bid: float,
    ltv: float,
    current_noi: float,
    current_cap: float,
    debt_rate: float,
    amortization_years: int,
    world_noi_growth: float,
    world_cap_delta: float,
    required_return: float,
    min_dscr: float,
    max_ltv: float,
) -> float:
    """
    Decision quality evaluated against the hidden world-state EXPECTED outcome,
    not the realized stochastic outcome.

    BUY: rewarded if expected levered return exceeds required return and loan metrics
         are disciplined. Penalized for poor leverage/discipline even if expected return is high.
    PASS: rewarded if the underlying opportunity's EXPECTED unlevered return is below hurdle.
    """
    from src.finance.calculations import property_value_from_noi, annual_debt_service, dscr, unlevered_property_return
    if decision == "PASS":
        # expected unlevered deal return from world parameters
        exit_noi = current_noi * (1 + world_noi_growth)
        exit_cap = max(0.03, current_cap + world_cap_delta)
        exit_value = property_value_from_noi(exit_noi, exit_cap)
        cf = exit_noi
        unlevered = unlevered_property_return(exit_value, cf, bid if bid > 0 else current_noi / current_cap)
        # PASS is good if the deal would have failed the hurdle
        if unlevered < required_return:
            return 80.0
        else:
            return 40.0
    # BUY
    exp_ret = expected_levered_return_from_world(
        current_noi, current_cap, debt_rate, amortization_years, bid, ltv,
        world_noi_growth, world_cap_delta,
    )
    ds = annual_debt_service(bid * ltv, debt_rate, amortization_years)
    noi = current_noi
    dscr_val = dscr(noi, ds) if ds > 0 else float("inf")
    # base on expected return vs required
    if math.isnan(exp_ret):
        return 50.0
    ret_score = max(0.0, min(100.0, 60.0 * (exp_ret + 0.20) / 0.40))
    # leverage discipline
    ltv_score = 100.0 if ltv <= max_ltv else max(0.0, 100.0 - 200.0 * (ltv - max_ltv))
    dscr_score = 100.0 if dscr_val >= min_dscr else max(0.0, 100.0 * dscr_val / min_dscr)
    score = 0.5 * ret_score + 0.25 * ltv_score + 0.25 * dscr_score
    return round(score, 6)


def risk_discipline_score(
    dscr: float,
    ltv: float,
    max_ltv: float,
    min_dscr: float,
) -> float:
    """
    Risk discipline on 0–100.
    Rewards staying inside LTV and DSCR constraints.
    """
    if dscr is None or math.isnan(dscr) or dscr == float("inf"):
        dscr_score = 90.0
    else:
        dscr_score = 100.0 if dscr >= min_dscr else max(0.0, 100.0 * dscr / min_dscr)
    ltv_score = 100.0 if ltv <= max_ltv else max(0.0, 100.0 - 200.0 * (ltv - max_ltv))
    return round(0.5 * dscr_score + 0.5 * ltv_score, 6)


def process_score(*, used_future_data: bool = False, leakage_trap_hit: bool = False) -> float:
    """
    Process / data integrity score.
    Penalizes use of data not available at decision time and hitting leakage traps.
    """
    if used_future_data:
        return 40.0
    if leakage_trap_hit:
        return 50.0
    return 100.0


def scorecard(
    round_index: int,
    property_id: str,
    decision: str,
    bid: float,
    ltv: float,
    noi_growth_forecast: float,
    exit_cap_forecast: float,
    confidence: float,
    probability_of_loss: Optional[float],
    thesis: str,
    # actuals
    actual_noi_growth: float,
    actual_cap_delta: float,
    actual_exit_noi: float,
    actual_exit_cap: float,
    actual_exit_value: float,
    actual_levered_return: float,
    actual_unlevered_return: float,
    # forecasts for scoring
    predicted_value: Optional[float],
    predicted_noi: Optional[float],
    # world-state hidden parameters for decision quality
    world_noi_growth: float,
    world_cap_delta: float,
    current_noi: float,
    current_cap: float,
    debt_rate: float,
    amortization_years: int,
    required_return: float,
    min_dscr: float,
    max_ltv: float,
    # process
    used_future_data: bool = False,
    leakage_trap_hit: bool = False,
) -> Scorecard:
    w = load_weights()["weights"]
    thr = load_weights()["thresholds"]

    # Forecast
    pq = forecast_quality_score(
        actual_exit_value, predicted_value or actual_exit_value,
        actual_exit_noi, predicted_noi or actual_exit_noi,
        actual_exit_cap, exit_cap_forecast,
        mape_cap=thr["value_mape_cap"],
    )

    # Outcome
    oc = outcome_quality_score(actual_levered_return if decision == "BUY" else actual_unlevered_return, required_return)

    # Risk
    from src.finance.calculations import annual_debt_service, dscr as dscr_fn
    ds = annual_debt_service(bid * ltv, debt_rate, amortization_years) if decision == "BUY" and bid > 0 else 0.0
    dscr_val = dscr_fn(current_noi, ds) if ds > 0 else float("inf")
    rk = risk_discipline_score(dscr_val, ltv, max_ltv, min_dscr)

    # Decision quality (uses hidden world params, not realized)
    dq = decision_quality_score(
        decision, bid, ltv, current_noi, current_cap, debt_rate, amortization_years,
        world_noi_growth, world_cap_delta, required_return, min_dscr, max_ltv,
    )

    # Process
    pr = process_score(used_future_data=used_future_data, leakage_trap_hit=leakage_trap_hit)

    # Composite
    total = (
        w["financial"] * oc
        + w["forecast"] * pq
        + w["risk"] * rk
        + w["decision"] * dq
        + w["process"] * pr
    )

    details = {
        "forecast_value_error": forecast_value_error(actual_exit_value, predicted_value or actual_exit_value),
        "forecast_noi_error": forecast_noi_error(actual_exit_noi, predicted_noi or actual_exit_noi),
        "forecast_cap_error": forecast_cap_error(actual_exit_cap, exit_cap_forecast),
        "brier_loss": brier_score(probability_of_loss, 1 if (actual_levered_return is not None and actual_levered_return < 0) else 0) if probability_of_loss is not None else None,
        "actual_levered_return": actual_levered_return,
        "actual_unlevered_return": actual_unlevered_return,
        "expected_levered_return": expected_levered_return_from_world(
            current_noi, current_cap, debt_rate, amortization_years, bid, ltv,
            world_noi_growth, world_cap_delta,
        ) if decision == "BUY" else None,
        "dscr": dscr_val,
        "ltv": ltv,
        "decision_quality_score": dq,
        "risk_score": rk,
        "forecast_score": pq,
        "outcome_score": oc,
        "process_score": pr,
        "thesis": thesis,
    }

    return Scorecard(
        round_index=round_index,
        property_id=property_id,
        decision=decision,
        financial_score=round(oc, 6),
        forecast_score=round(pq, 6),
        risk_score=round(rk, 6),
        decision_score=round(dq, 6),
        process_score=round(pr, 6),
        total_score=round(total, 6),
        weights=w,
        details=details,
    )
