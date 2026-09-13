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
    """A single investment attempt, decomposed four ways.

    The axes are deliberately independent, because collapsing them is the single
    most common analytical error the course is trying to break:

    ``model_label``     empirical — was the valuation close to what happened?
    ``decision_label``  ex ante  — was the choice sensible given only what was
                        knowable BEFORE the outcome (the asking price, your own
                        policy)? Never scored on what the dice did.
    ``override_label``  policy  — did you follow, exceed, or undercut your own
                        stated maximum bid?
    ``outcome_label``   realized — did the money actually work?

    Crucially, exceeding your own model's max bid is **not** automatically a bad
    decision. Disagreeing with a model is a legitimate analytical act; it is
    recorded, then judged on whether the price you paid was defensible ex ante.
    """

    team_id: str
    property_id: str
    round_number: int

    model_label: str  # GOOD_MODEL | BAD_MODEL
    decision_label: str  # GOOD_DECISION | BAD_DECISION
    outcome_label: str  # GOOD_OUTCOME | BAD_OUTCOME | NO_POSITION
    override_label: str = "NO_BID"  # FOLLOWED | OVERRODE_UP | OVERRODE_DOWN | NO_BID

    valuation_error_pct: Optional[float] = None
    bid_override: Optional[float] = None
    ltv_override: Optional[float] = None
    realized_return: Optional[float] = None
    asking_price: Optional[float] = None
    won: bool = False

    @property
    def headline(self) -> str:
        return f"{self.model_label} / {self.decision_label} / {self.outcome_label}"

    @property
    def case_labels(self) -> List[str]:
        """Every named teaching case this attempt genuinely satisfies.

        An attempt can satisfy more than one: a fund that overpays and still makes
        money is both a bad override *and* a lucky outcome, and both are true. The
        list is ordered by teaching priority -- the sharpest lesson first -- so the
        debrief can lead with the most pointed case without denying the others.
        """
        cases: List[str] = []
        if self.won and self.decision_label == "GOOD_DECISION" \
                and self.outcome_label == "BAD_OUTCOME":
            cases.append("GOOD DECISION + BAD REALIZED OUTCOME")
        if self.won and self.decision_label == "BAD_DECISION" \
                and self.outcome_label == "GOOD_OUTCOME":
            cases.append("BAD DECISION + LUCKY REALIZED OUTCOME")
        if self.won and self.model_label == "BAD_MODEL" and self.decision_label == \
                "GOOD_DECISION" and self.override_label in ("OVERRODE_UP", "OVERRODE_DOWN"):
            cases.append("MODEL WRONG + GOOD OVERRIDE")
        if self.won and self.model_label == "GOOD_MODEL" and self.decision_label == \
                "BAD_DECISION" and self.override_label == "OVERRODE_UP":
            cases.append("MODEL GOOD + BAD OVERRIDE")
        if self.won and self.model_label == "GOOD_MODEL" and self.decision_label == \
                "GOOD_DECISION" and self.override_label == "FOLLOWED":
            cases.append("MODEL GOOD + FOLLOWED MODEL")
        return cases

    @property
    def case_label(self) -> Optional[str]:
        """The single most instructive named case, or None."""
        cases = self.case_labels
        return cases[0] if cases else None

    def teaching_note(self) -> str:
        """Plain-language reading of the axes."""
        if self.bid_override is not None and self.bid_override > 0:
            if self.decision_label == "BAD_DECISION":
                return (
                    f"You bid ${self.bid_override:+.2f}M above your own model's ceiling "
                    f"and above the asking price. The model was not the constraint here -- "
                    f"your price discipline was."
                )
            return (
                f"You overrode your model by ${self.bid_override:+.2f}M but still bought at "
                f"or below the asking price. Recorded as a deliberate override; whether it "
                f"was right depends on the model, not on the rule."
            )

        if self.model_label == "GOOD_MODEL" and self.decision_label == "GOOD_DECISION":
            if self.outcome_label == "BAD_OUTCOME":
                return (
                    "Your analysis and your decision were both sound; the year simply "
                    "went against you. Do not change this process because of one draw."
                )
            if self.outcome_label == "GOOD_OUTCOME":
                return "Sound analysis, disciplined decision, and it worked. Repeat this."
            return "Sound analysis and a disciplined decision. The outcome is not in yet."

        if self.model_label == "BAD_MODEL" and self.decision_label == "GOOD_DECISION":
            return (
                "Your model mispriced this and your discipline still protected you. "
                "The lesson is about the model, not the decision."
            )

        if self.model_label == "GOOD_MODEL" and self.decision_label == "BAD_DECISION":
            return (
                "Your model was right and you paid above the offering price anyway. "
                "This is the most expensive and most common failure mode in the game."
            )

        if self.model_label == "BAD_MODEL" and self.outcome_label == "GOOD_OUTCOME" \
                and self.won:
            return (
                "Bad model, questionable decision, good outcome. You were paid for a "
                "mistake. Nothing here is repeatable."
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

            prop = game_manager.all_properties.get(prop_id)
            asking = prop.asking_price if prop is not None else None

            for team_id, team in game_manager.teams.items():
                pred = (team.model_predictions or {}).get(prop_id)
                if pred is None:
                    continue

                team_bid = next(
                    (b for b in auction.all_bids if b.team_id == team_id), None
                )
                won = auction.sold and auction.winning_team_id == team_id

                # --- 1. model quality: empirical, uses the realized value ---
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

                # --- 2. decision quality: ex ante only ---------------------
                # The asking price is public before the decision and it is the
                # only defensible yardstick that does not peek at the outcome.
                # This is what keeps "overrode my model" from being an automatic
                # bad mark: disagreeing with your model is allowed and useful.
                bid_override: Optional[float] = None
                ltv_override: Optional[float] = None
                override_label = "NO_BID"

                if team_bid is not None:
                    bid_override = team_bid.bid_price - pred.max_bid
                    ltv_override = team_bid.ltv - pred.target_ltv
                    if abs(bid_override) <= 1e-9:
                        override_label = "FOLLOWED"
                    elif bid_override > 0:
                        override_label = "OVERRODE_UP"
                    else:
                        override_label = "OVERRODE_DOWN"

                    if asking is not None and asking > 0:
                        decision_label = (
                            "GOOD_DECISION"
                            if team_bid.bid_price <= asking
                            else "BAD_DECISION"
                        )
                    else:
                        decision_label = "GOOD_DECISION"
                else:
                    # Passing is a decision too. Passing on a property your own
                    # policy authorised you to buy is a failure of execution;
                    # passing because the ask was above your ceiling is discipline.
                    if asking is not None and asking > 0:
                        decision_label = (
                            "GOOD_DECISION"
                            if pred.max_bid <= asking
                            else "BAD_DECISION"
                        )
                    else:
                        decision_label = "GOOD_DECISION"

                # --- 3. realized outcome: only exists if you actually bought -#
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
                    outcome_label = "NO_POSITION"

                attempts.append(
                    AttemptAssessment(
                        team_id=team_id,
                        property_id=prop_id,
                        round_number=round_number,
                        model_label=model_label,
                        decision_label=decision_label,
                        outcome_label=outcome_label,
                        override_label=override_label,
                        valuation_error_pct=model_mape,
                        bid_override=bid_override,
                        ltv_override=ltv_override,
                        realized_return=realized_return,
                        asking_price=asking,
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


# ── the final debrief ─────────────────────────────────────────────────────


@dataclass
class FundChannels:
    """Where a fund's NAV change actually came from. The channels sum exactly.

        NAV - starting equity = value_channel + noi_income
                                - interest_paid - acquisition_costs - reserves

    Verified against the engine to machine precision, so the debrief can point at
    arithmetic rather than assert an opinion.
    """

    team_id: str
    team_name: str
    nav: float
    cumulative_return: float
    value_channel: float
    noi_income: float
    interest_paid: float
    acquisition_costs: float
    reserves: float
    net_carry: float
    gross_ltv: Optional[float]
    weighted_debt_rate: Optional[float]
    return_on_cost: Optional[float]
    assets: int

    @property
    def leverage_verdict(self) -> str:
        """Did borrowing pay for itself? Return on cost versus cost of debt."""
        if not self.gross_ltv or self.gross_ltv <= 0:
            return "no leverage used"
        if self.return_on_cost is None or self.weighted_debt_rate is None:
            return "insufficient data"
        if self.return_on_cost > self.weighted_debt_rate:
            return "accretive (return on cost beat the debt rate)"
        return "dilutive (borrowed above what the assets earn)"


def fund_channels(game_manager, team_id: str) -> FundChannels:
    """Decompose one fund's NAV change into its three real channels."""
    team = game_manager.teams[team_id]
    props = list(team.properties.values())

    gross_value = sum(h.current_value for h in props)
    value_channel = sum(h.current_value - h.purchase_price for h in props)
    interest = team.cumulative_interest
    gross_ltv = (team.debt / gross_value) if gross_value > 0 else None
    wd_rate = (
        sum(h.debt_amount * h.debt_rate for h in props) / team.debt
        if team.debt > 0
        else None
    )
    # Return on cost: what the assets produced net of the capital they consumed,
    # relative to what was paid for them. Comparing this to the debt rate is the
    # honest test of whether leverage paid for itself.
    cost = team.cumulative_purchase_price
    return_on_cost = (
        (value_channel + team.cumulative_income - team.cumulative_reserves) / cost
        if cost > 0
        else None
    )

    return FundChannels(
        team_id=team_id,
        team_name=team.team_name,
        nav=team.nav,
        cumulative_return=team.cumulative_return,
        value_channel=value_channel,
        noi_income=team.cumulative_income,
        interest_paid=interest,
        acquisition_costs=team.cumulative_acquisition_costs,
        reserves=team.cumulative_reserves,
        net_carry=team.cumulative_income - interest - team.cumulative_reserves,
        gross_ltv=gross_ltv,
        weighted_debt_rate=wd_rate,
        return_on_cost=return_on_cost,
        assets=len(props),
    )


@dataclass
class DebriefAnswer:
    """One instructor-facing question and the game history's answer to it."""

    number: int
    question: str
    answer: str
    detail: str = ""
    team_id: Optional[str] = None


@dataclass
class GameDebrief:
    """Everything the final screen needs, all computed from recorded history."""

    answers: List[DebriefAnswer] = field(default_factory=list)
    channels: List[FundChannels] = field(default_factory=list)
    standings: List[Dict] = field(default_factory=list)
    analytics: List[TeamAnalytics] = field(default_factory=list)
    override_summary: Dict = field(default_factory=dict)
    case_counts: Dict[str, int] = field(default_factory=dict)
    examples: Dict[str, AttemptAssessment] = field(default_factory=dict)


def _example_for(case: str, attempts: List[AttemptAssessment]) -> Optional[AttemptAssessment]:
    """A representative won attempt for a named case.

    Uses the full ``case_labels`` list, not just the primary label, so a case is
    not reported as missing merely because another label outranked it.
    """
    for a in attempts:
        if a.won and case in a.case_labels:
            return a
    return None


def debrief_answers(game_manager) -> GameDebrief:
    """Answer the ten questions the final debrief must be able to answer.

    Every number here is computed from recorded game history. No language model
    adjudicates anything, and no answer is scored on an assumption about what
    "should" have happened.
    """
    standings = game_manager.get_leaderboard()
    analytics = analytics_leaderboard(game_manager)
    attempts = assess_attempts(game_manager)
    channels = [fund_channels(game_manager, t) for t in game_manager.teams]
    channels.sort(key=lambda c: c.nav, reverse=True)
    override = override_contribution(game_manager)

    case_counts: Dict[str, int] = {}
    for a in attempts:
        for case in a.case_labels:
            case_counts[case] = case_counts.get(case, 0) + 1

    examples = {
        case: ex
        for case in (
            "MODEL GOOD + FOLLOWED MODEL",
            "MODEL GOOD + BAD OVERRIDE",
            "MODEL WRONG + GOOD OVERRIDE",
            "GOOD DECISION + BAD REALIZED OUTCOME",
            "BAD DECISION + LUCKY REALIZED OUTCOME",
        )
        if (ex := _example_for(case, attempts)) is not None
    }

    answers: List[DebriefAnswer] = []

    # 1 ── who won
    if standings:
        w = standings[0]
        answers.append(DebriefAnswer(
            1, "Who won the game?",
            f"{w['team_name']} finished with ${w['nav']:,.2f}M NAV "
            f"({w['cumulative_return']:+.1%} on ${game_manager.config.starting_equity:,.0f}M of equity).",
            f"{w['properties']} assets, ${w['debt']:,.1f}M of debt.",
            w["team_id"],
        ))

    # 2 ── who had the best model
    scored = [t for t in analytics if t.valuation_mae is not None]
    best_model = scored[0] if scored else None
    if best_model:
        answers.append(DebriefAnswer(
            2, "Who had the best model?",
            f"{best_model.team_name}, with a valuation MAE of "
            f"${best_model.valuation_mae:.2f}M over {best_model.properties_scored} "
            f"properties priced.",
            f"NOI-growth MAE {best_model.noi_growth_mae:.4f}."
            if best_model.noi_growth_mae is not None else "",
            best_model.team_id,
        ))

    # 3 ── were they the same team
    if standings and best_model:
        same = standings[0]["team_id"] == best_model.team_id
        answers.append(DebriefAnswer(
            3, "Were the winner and the best model the same team?",
            "Yes — the best analysis also won." if same else
            "No. The best model did not win the game.",
            "When these differ, the gap is decision quality or luck, and the "
            "rest of this debrief says which." if not same else
            "Analytical quality and game outcome agreed in this run.",
        ))

    # 4 ── who overrode their model most
    by_team_overrides: Dict[str, int] = {}
    for a in attempts:
        if a.override_label in ("OVERRODE_UP", "OVERRODE_DOWN"):
            by_team_overrides[a.team_id] = by_team_overrides.get(a.team_id, 0) + 1
    if by_team_overrides:
        top_id = max(by_team_overrides, key=lambda k: by_team_overrides[k])
        top_name = game_manager.teams[top_id].team_name
        total = sum(by_team_overrides.values())
        answers.append(DebriefAnswer(
            4, "Who overrode their own model most often?",
            f"{top_name} deviated from its own stated bid ceiling "
            f"{by_team_overrides[top_id]} times.",
            f"{total} deliberate overrides across all funds.",
            top_id,
        ))
    else:
        answers.append(DebriefAnswer(
            4, "Who overrode their own model most often?",
            "Nobody did. Every fund bid at or below its own ceiling all game.",
            "That makes the override question untestable in this run; consider "
            "having a team deliberately disagree with its model next time.",
        ))

    # 5 ── did overrides help or hurt
    oc, dc = override["overridden_count"], override["disciplined_count"]
    if oc and override["overridden_avg_return"] is not None \
            and override["disciplined_avg_return"] is not None:
        delta = override["overridden_avg_return"] - override["disciplined_avg_return"]
        answers.append(DebriefAnswer(
            5, "Did those overrides help or hurt?",
            f"Overridden purchases returned "
            f"{override['overridden_avg_return']:+.1%} against "
            f"{override['disciplined_avg_return']:+.1%} for disciplined ones "
            f"({delta:+.1%} difference, {oc} vs {dc} deals).",
            "Overrides helped." if delta > 0 else
            "Overrides hurt — discipline would have paid better.",
        ))
    else:
        answers.append(DebriefAnswer(
            5, "Did those overrides help or hurt?",
            f"Cannot be measured: {oc} overridden purchases and {dc} disciplined "
            f"ones were completed.",
            "One side of the comparison is empty, so there is nothing to compare.",
        ))

    # 6 ── who used the most leverage
    levered = [c for c in channels if c.gross_ltv is not None and c.assets > 0]
    if levered:
        top_lev = max(levered, key=lambda c: c.gross_ltv)
        answers.append(DebriefAnswer(
            6, "Who used the most leverage?",
            f"{top_lev.team_name} ran {top_lev.gross_ltv:.0%} gross LTV across "
            f"{top_lev.assets} assets, at a weighted debt rate of "
            f"{top_lev.weighted_debt_rate:.2%}.",
            f"${{:.1f}}M of debt outstanding.".format(
                game_manager.teams[top_lev.team_id].debt
            ),
            top_lev.team_id,
        ))

    # 7 ── did leverage create or destroy value
    if levered:
        lines = []
        for c in levered:
            lines.append(
                f"{c.team_name}: {c.gross_ltv:.0%} LTV, return on cost "
                f"{c.return_on_cost:+.1%} vs debt rate {c.weighted_debt_rate:.2%} "
                f"→ {c.leverage_verdict}"
            )
        accretive = sum(1 for c in levered if c.net_carry > 0)
        answers.append(DebriefAnswer(
            7, "Did leverage create or destroy value?",
            f"{accretive} of {len(levered)} levered funds earned positive net carry "
            f"(NOI received minus interest paid).",
            " | ".join(lines),
        ))

    # 8 ── good decision, bad outcome
    ex8 = examples.get("GOOD DECISION + BAD REALIZED OUTCOME")
    if ex8:
        nm = game_manager.teams[ex8.team_id].team_name
        answers.append(DebriefAnswer(
            8, "Which decision looked right beforehand but went wrong?",
            f"{nm} bought {ex8.property_id} in round {ex8.round_number + 1} at or below "
            f"the asking price and still lost money "
            f"({ex8.realized_return:+.1%} over the year).",
            "Nothing was wrong with the process; the realised year differed from "
            "the ex-ante expectation.",
            ex8.team_id,
        ))
    else:
        answers.append(DebriefAnswer(
            8, "Which decision looked right beforehand but went wrong?",
            "No clean example this run.",
        ))

    # 9 ── who got lucky
    ex9 = examples.get("BAD DECISION + LUCKY REALIZED OUTCOME")
    lucky = [k for k in case_counts if k == "BAD DECISION + LUCKY REALIZED OUTCOME"]
    if ex9:
        nm = game_manager.teams[ex9.team_id].team_name
        answers.append(DebriefAnswer(
            9, "Which team got lucky?",
            f"{nm} paid above the asking price for {ex9.property_id} in round "
            f"{ex9.round_number + 1} and was still rewarded "
            f"({ex9.realized_return:+.1%}).",
            f"{case_counts.get('BAD DECISION + LUCKY REALIZED OUTCOME', 0)} such "
            f"outcomes in total. Being paid for a mistake is not repeatable.",
            ex9.team_id,
        ))
    else:
        answers.append(DebriefAnswer(
            9, "Which team got lucky?",
            "No team was paid for an above-market bid this run.",
        ))

    # 10 ── conclusion
    if standings and best_model:
        best_won = standings[0]["team_id"] == best_model.team_id
        best_in_game = standings[0]["team_id"]
        best_rank = next(
            (i + 1 for i, s in enumerate(standings) if s["team_id"] == best_model.team_id),
            None,
        )
        if best_won:
            conclusion = (
                "The best model won, so analytical quality and decision quality "
                "were aligned. Check the override record before concluding the "
                "model alone earned it."
            )
        else:
            winner_channels = next(
                (c for c in channels if c.team_id == best_in_game), None
            )
            conclusion = (
                f"The best model finished {best_rank} of {len(standings)}. "
                f"{standings[0]['team_name']} won instead. Compare the two funds' "
                f"channels: winning came from "
                + ("capital deployed into positive carry rather than from superior "
                   "valuation." if winner_channels and winner_channels.net_carry > 0
                   else "somewhere other than valuation accuracy.")
            )
        answers.append(DebriefAnswer(
            10, "What should a student conclude?",
            conclusion,
            "A good forecast is necessary but not sufficient: it has to be converted "
            "into a bid you are actually willing to win with, under a capital "
            "constraint, and then it has to survive the year.",
        ))

    return GameDebrief(
        answers=answers,
        channels=channels,
        standings=standings,
        analytics=analytics,
        override_summary=override,
        case_counts=case_counts,
        examples=examples,
    )
