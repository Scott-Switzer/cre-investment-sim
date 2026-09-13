"""
Analytics leaderboard and the model / manager / luck debrief.

Deliberately separate from the game leaderboard.

* **Game leaderboard** — who wins: ending fund NAV. A student understands it
  instantly with no explanation.
* **Analytics leaderboard** — was the analysis any good: valuation MAE, NOI
  forecast MAE, downside calibration (Brier), value added versus a naive
  benchmark, and the measured contribution of human overrides.

Blending those into one weighted score would produce the "17% model + 23% risk +
28% decision" opacity the course explicitly wants to avoid.

Evaluating predictions
----------------------
A team's ``predicted_fair_value`` is made before play. It is scored against the
property's *realized* value in the round the property was offered -- i.e. the
value the market put on the asset one simulated year later. That is the honest
reading of "was your valuation right", and it is exactly what the round feedback
card shows the team.

The naive benchmark is the asking price: a model that adds no information should
at least be able to say "it's worth what it is being offered for". Value added is
reported relative to that, so a team cannot look good by making easy predictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.game.adjudicator import ModelPrediction, TeamState

# A prediction is "good" if its absolute percentage error is within this band.
GOOD_MODEL_MAPE = 0.15

# A realized levered return at or above this is a good outcome.
GOOD_OUTCOME_RETURN = 0.0


@dataclass
class TeamAnalytics:
    """Analytical performance for one team."""

    team_id: str
    team_name: str
    properties_scored: int = 0

    valuation_mae: Optional[float] = None
    valuation_mape: Optional[float] = None
    noi_growth_mae: Optional[float] = None
    downside_brier: Optional[float] = None

    naive_valuation_mae: Optional[float] = None
    value_added_vs_naive: Optional[float] = None

    override_count: int = 0
    avg_bid_override: Optional[float] = None
    avg_ltv_override: Optional[float] = None
    properties_won: int = 0
    realized_returns: List[float] = field(default_factory=list)

    @property
    def avg_realized_return(self) -> Optional[float]:
        if not self.realized_returns:
            return None
        return float(np.mean(self.realized_returns))


@dataclass
class AttemptAssessment:
    """A single investment attempt, decomposed three ways."""

    team_id: str
    property_id: str
    round_number: int

    model_label: str  # GOOD_MODEL | BAD_MODEL
    decision_label: str  # GOOD_DECISION | BAD_DECISION
    outcome_label: str  # GOOD_OUTCOME | BAD_OUTCOME

    valuation_error_pct: Optional[float]
    bid_override: Optional[float]
    realized_return: Optional[float]
    won: bool

    @property
    def headline(self) -> str:
        return f"{self.model_label} / {self.decision_label} / {self.outcome_label}"

    def teaching_note(self) -> str:
        """Plain-language reading of the three axes."""
        if self.model_label == "GOOD_MODEL" and self.decision_label == "GOOD_DECISION":
            if self.outcome_label == "BAD_OUTCOME":
                return (
                    "Your analysis and your decision were both sound; the year simply "
                    "went against you. Do not change this process because of one draw."
                )
            return "Sound analysis, disciplined decision, and it worked. Repeat this."

        if self.model_label == "BAD_MODEL" and self.decision_label == "GOOD_DECISION":
            return (
                "Your model mispriced this and your discipline still protected you. "
                "The lesson is about the model, not the decision."
            )

        if self.model_label == "GOOD_MODEL" and self.decision_label == "BAD_DECISION":
            return (
                "Your model was right and you overrode it. This is the most expensive "
                "and most common failure mode in the game."
            )

        if self.model_label == "BAD_MODEL" and self.outcome_label == "GOOD_OUTCOME":
            return (
                "Bad model, bad decision, good outcome. You were paid for a mistake. "
                "Nothing here is repeatable."
            )

        return "Both the model and the decision need work before the next round."


def _safe_mean(values: List[float]) -> Optional[float]:
    return float(np.mean(values)) if values else None


def compute_team_analytics(game_manager, team_id: str) -> TeamAnalytics:
    """Score one team's predictions against everything the game actually realized."""
    team: TeamState = game_manager.teams[team_id]
    result = TeamAnalytics(team_id=team_id, team_name=team.team_name)

    preds: Dict[str, ModelPrediction] = team.model_predictions or {}
    val_errors: List[float] = []
    val_pct_errors: List[float] = []
    naive_errors: List[float] = []
    noi_errors: List[float] = []
    brier_terms: List[float] = []

    for round_number, round_result in sorted(game_manager.round_history.items()):
        for prop_id, outcome in round_result.property_outcomes.items():
            pred = preds.get(prop_id)
            if pred is None:
                # Naive benchmark only needs the ask, which is not always known
                # once a round has passed; skip when we cannot compute it.
                continue

            actual_value = outcome.exit_value
            if actual_value and np.isfinite(actual_value) and actual_value > 0:
                val_errors.append(abs(pred.predicted_fair_value - actual_value))
                val_pct_errors.append(
                    abs(pred.predicted_fair_value - actual_value) / actual_value
                )

            if pred.predicted_noi_growth is not None:
                noi_errors.append(
                    abs(pred.predicted_noi_growth - outcome.noi_growth_actual)
                )

            if pred.probability_of_downside is not None:
                downside_realized = 1.0 if outcome.noi_growth_actual < 0 else 0.0
                brier_terms.append(
                    (pred.probability_of_downside - downside_realized) ** 2
                )

    # Naive benchmark: "it is worth the asking price."
    for prop_id, prop_market in game_manager.all_properties.items():
        for round_number, round_result in sorted(game_manager.round_history.items()):
            outcome = round_result.property_outcomes.get(prop_id)
            if outcome is None:
                continue
            if outcome.exit_value and outcome.exit_value > 0:
                naive_errors.append(
                    abs(prop_market.asking_price - outcome.exit_value)
                )

    if val_errors:
        result.valuation_mae = float(np.mean(val_errors))
        result.properties_scored = len(val_errors)
    if val_pct_errors:
        result.valuation_mape = float(np.mean(val_pct_errors))
    if noi_errors:
        result.noi_growth_mae = float(np.mean(noi_errors))
    if brier_terms:
        result.downside_brier = float(np.mean(brier_terms))
    if naive_errors:
        result.naive_valuation_mae = float(np.mean(naive_errors))
        if result.valuation_mae is not None and result.naive_valuation_mae > 0:
            result.value_added_vs_naive = float(
                1.0 - result.valuation_mae / result.naive_valuation_mae
            )

    overrides = team.override_history or []
    result.override_count = len(overrides)
    if overrides:
        result.avg_bid_override = float(np.mean([o.bid_override for o in overrides]))
        result.avg_ltv_override = float(np.mean([o.ltv_override for o in overrides]))

    result.properties_won = len(team.properties)
    for holding in team.properties.values():
        if holding.purchase_price and holding.purchase_price > 0:
            result.realized_returns.append(
                (holding.current_value - holding.purchase_price) / holding.purchase_price
            )

    return result


def analytics_leaderboard(game_manager) -> List[TeamAnalytics]:
    """Analytics ranking, best valuation first. Pure teaching output, not the win condition."""
    board = [compute_team_analytics(game_manager, tid) for tid in game_manager.teams]
    board.sort(
        key=lambda t: (t.valuation_mae if t.valuation_mae is not None else float("inf"))
    )
    return board


def assess_attempts(game_manager) -> List[AttemptAssessment]:
    """Separate model quality, manager quality and realized outcome for each attempt.

    Decision quality is judged **ex ante** against the team's own stated policy,
    never against what the dice did. A disciplined bid at or below the model's max
    bid is a good decision even when the year turns out badly.
    """
    attempts: List[AttemptAssessment] = []

    for round_number, round_result in sorted(game_manager.round_history.items()):
        for prop_id, auction in round_result.auction_results.items():
            outcome = round_result.property_outcomes.get(prop_id)
            if outcome is None:
                continue

            for team_id, team in game_manager.teams.items():
                pred = (team.model_predictions or {}).get(prop_id)
                if pred is None:
                    continue

                team_bid = next(
                    (b for b in auction.all_bids if b.team_id == team_id), None
                )
                won = auction.sold and auction.winning_team_id == team_id

                # --- model quality: was the valuation close? ---
                if outcome.exit_value and outcome.exit_value > 0:
                    model_mape = (
                        abs(pred.predicted_fair_value - outcome.exit_value)
                        / outcome.exit_value
                    )
                    model_label = (
                        "GOOD_MODEL" if model_mape <= GOOD_MODEL_MAPE else "BAD_MODEL"
                    )
                else:
                    model_mape = None
                    model_label = "BAD_MODEL"

                # --- decision quality (ex ante) ---
                bid_override: Optional[float] = None
                if team_bid is None:
                    # Passing is a decision. Passing when the ask sat above your
                    # own max bid is disciplined; passing on a property your model
                    # said to buy is not.
                    decision_label = (
                        "GOOD_DECISION"
                        if pred.max_bid <= outcome.exit_value
                        else "BAD_DECISION"
                    )
                    if team_bid is None and not won and pred.max_bid <= outcome.exit_value:
                        decision_label = "BAD_DECISION" if pred.max_bid > 0 else "GOOD_DECISION"
                else:
                    bid_override = team_bid.bid_price - pred.max_bid
                    decision_label = "GOOD_DECISION" if bid_override <= 0 else "BAD_DECISION"

                # --- realized outcome ---
                realized_return: Optional[float] = None
                if won and auction.winning_bid:
                    realized_return = (
                        outcome.exit_value - auction.winning_bid
                    ) / auction.winning_bid
                    outcome_label = (
                        "GOOD_OUTCOME"
                        if realized_return >= GOOD_OUTCOME_RETURN
                        else "BAD_OUTCOME"
                    )
                else:
                    outcome_label = "GOOD_OUTCOME" if model_label == "GOOD_MODEL" else "BAD_OUTCOME"

                attempts.append(
                    AttemptAssessment(
                        team_id=team_id,
                        property_id=prop_id,
                        round_number=round_number,
                        model_label=model_label,
                        decision_label=decision_label,
                        outcome_label=outcome_label,
                        valuation_error_pct=model_mape,
                        bid_override=bid_override,
                        realized_return=realized_return,
                        won=won,
                    )
                )

    return attempts


def override_contribution(game_manager) -> Dict[str, float]:
    """Average realized return on overridden purchases vs disciplined ones.

    Positive means overrides helped; negative means discipline would have paid
    better. Reported, not scored -- the point is the classroom conversation.
    """
    overridden: List[float] = []
    disciplined: List[float] = []

    for attempt in assess_attempts(game_manager):
        if not attempt.won or attempt.realized_return is None:
            continue
        if attempt.bid_override is not None and attempt.bid_override > 0:
            overridden.append(attempt.realized_return)
        elif attempt.bid_override is not None:
            disciplined.append(attempt.realized_return)

    return {
        "overridden_count": len(overridden),
        "overridden_avg_return": _safe_mean(overridden),
        "disciplined_count": len(disciplined),
        "disciplined_avg_return": _safe_mean(disciplined),
    }
