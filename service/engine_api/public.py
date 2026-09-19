"""
Student-safe serialisers.

Every payload a browser can see is built here, by **naming** the fields it exposes.
Nothing is produced by copying the engine snapshot and deleting keys: subtraction
fails open the first time a field is added, and the field that would leak is the
seller's reserve.

Each function ends by calling :func:`visibility.assert_no_leaks`, so the guarantee
is enforced at runtime rather than documented and hoped for.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.game.adjudicator import (
    ACQUISITION_COST_RATE,
    CAPITAL_RESERVE_RATE,
    MANAGEMENT_INVEST_RESERVE_ADDER,
    MANAGEMENT_SHOCK_PROBABILITY,
    MANAGEMENT_STANCE_MAINTENANCE_RATE,
    MANAGEMENT_STANCE_SHOCK_MULTIPLIER,
    MANAGEMENT_STANCE_SHOCK_NOI_IMPACT,
    STANCES,
    STANCE_DEFAULT,
    MarketState,
    PropertyMarket,
    RoundResult,
    TeamState,
)
from src.game.analytics import (
    AttemptAssessment,
    FundChannels,
    TeamAnalytics,
    analytics_leaderboard,
    debrief_answers,
    fund_channels,
)
from src.game.manager import GameManager, game_stage

from . import visibility
from .visibility import (
    FORBIDDEN_IN_BROADCAST,
    FORBIDDEN_IN_RESULTS,
    FORBIDDEN_IN_TEAM_VIEW,
)

POLICY_KEYS = ("max_bid", "target_ltv")
FORECAST_KEYS = (
    "predicted_fair_value",
    "predicted_noi_growth",
    "probability_of_downside",
    "confidence",
    "predicted_exit_cap",
)


def _num(value: Any) -> Optional[float]:
    """JSON-native float. numpy scalars from pandas rows are coerced here."""
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except TypeError:
        return None
    return round(float(value), 6)


# ── the single property DTO ───────────────────────────────────────────────

def public_deal(prop: PropertyMarket) -> Dict[str, Any]:
    """One building, as a player sees it before deciding. The ONLY property shape.

    Carries the full underwriting context the engine itself uses, so the game never
    reads a CSV and there is never a second, disagreeing representation of an asset.
    """
    payload = {
        "property_id": prop.property_id,
        "property_name": prop.property_name,
        "property_type": prop.property_type,
        "submarket": prop.submarket,
        # physical
        "building_sf": _num(prop.building_sf),
        "units": prop.units,
        "year_built": prop.year_built,
        # operations
        "current_noi": _num(prop.current_noi),
        "occupancy": _num(prop.occupancy),
        "market_rent": _num(prop.market_rent),
        "in_place_rent": _num(prop.in_place_rent),
        "walt": _num(prop.walt),
        "tenant_concentration": _num(prop.tenant_concentration),
        "opex_ratio": _num(prop.opex_ratio),
        "lease_expiry_profile": prop.lease_expiry_profile,
        "property_quality": _num(prop.property_quality),
        "primary_risk": prop.primary_risk,
        # capital markets
        "asking_price": _num(prop.asking_price),
        "going_in_cap": _num(prop.current_cap),
        "debt_rate": _num(prop.debt_rate),
        "max_ltv": _num(prop.max_ltv),
        "amortization_years": prop.amortization_years,
        # game economics, so the underwriting drawer can be honest about charges
        "acquisition_cost_rate": _num(ACQUISITION_COST_RATE),
        "capital_reserve_rate": _num(
            CAPITAL_RESERVE_RATE.get(prop.property_type, 0.012)
        ),
        # Descriptive building-condition feature. NOT the recurring cash charge --
        # that is capital_reserve_rate above. Named to prevent the confusion.
        "indicative_capex_exposure": _num(prop.indicative_capex_exposure),
        "indicative_capex_note": (
            "Descriptive condition feature only. The simulation charges "
            "capital_reserve_rate, not this figure."
        ),
    }
    visibility.assert_no_leaks(payload, f"public_deal({prop.property_id})",
                              forbidden=FORBIDDEN_IN_BROADCAST)
    return payload


def public_properties(properties) -> List[Dict[str, Any]]:
    return [public_deal(p) for p in properties]


# ── before the round resolves ─────────────────────────────────────────────

def public_market(market: Optional[MarketState]) -> Optional[Dict[str, Any]]:
    if market is None:
        return None
    return {
        "round_number": market.round_number,
        "policy_rate": _num(market.policy_rate),
        "unemployment": _num(market.unemployment),
        "employment_growth": _num(market.employment_growth),
        "inflation": _num(market.inflation),
        "vacancy": {k: _num(v) for k, v in market.vacancy.items()},
        "cap_rate": {k: _num(v) for k, v in market.cap_rate.items()},
        "credit_conditions": _num(market.credit_conditions),
    }


def public_fund_summary(team: TeamState) -> Dict[str, Any]:
    """The public scoreboard line for a fund. No holdings, no model, no bids."""
    return {
        "team_id": team.team_id,
        "team_name": team.team_name,
        "nav": _num(team.nav),
        "cash": _num(team.cash),
        "debt": _num(team.debt),
        "assets": len(team.properties),
        "cumulative_return": _num(team.cumulative_return),
    }


def public_round(gm: GameManager) -> Dict[str, Any]:
    """Everything a fund may see while the current round is open.

    Deliberately excludes: every reserve price, every future outcome, every fund's
    model, and every submitted bid.
    """
    payload = {
        "round_number": gm.current_round,
        "stage": game_stage(gm),
        "is_practice": gm.current_round < 0,
        "round_state": gm.round_state.value,
        "total_rounds": gm.config.total_rounds,
        "deals": public_properties(gm.current_properties.values()),
        "market": public_market(gm.market_history[-1] if gm.market_history else None),
        "funds": [public_fund_summary(t) for t in gm.teams.values()],
        "economics": {
            "acquisition_cost_rate": _num(ACQUISITION_COST_RATE),
            "capital_reserve_rate": {
                k: _num(v) for k, v in CAPITAL_RESERVE_RATE.items()
            },
            # V2: the management layer's own coefficients, so a fund can price
            # its stances before deciding — the same "no hidden rule" principle
            # that publishes the acquisition and reserve rates.
            "management": {
                "enabled": bool(gm.config.management_active),
                "course_mode": str(gm.config.course_mode),
                "course_label": gm.config.profile.label,
                "required_models": list(gm.config.profile.required_models),
                # The stances this tier accepts. A one-entry list means the tier
                # shows no stance choice at all, so a student UI can decide from
                # config whether to render the control.
                "stances": list(gm.config.profile.stances),
                "all_stances": list(STANCES),
                "has_stance_choice": gm.config.profile.has_stance_choice,
                "default_stance": STANCE_DEFAULT,
                "invest_reserve_adder": _num(MANAGEMENT_INVEST_RESERVE_ADDER),
                "shock_probability": {
                    k: _num(v) for k, v in MANAGEMENT_SHOCK_PROBABILITY.items()
                },
                "stance_shock_multiplier": {
                    k: _num(v) for k, v in MANAGEMENT_STANCE_SHOCK_MULTIPLIER.items()
                },
                "stance_shock_noi_impact": {
                    k: _num(v) for k, v in MANAGEMENT_STANCE_SHOCK_NOI_IMPACT.items()
                },
                "stance_maintenance_rate": {
                    k: _num(v) for k, v in MANAGEMENT_STANCE_MAINTENANCE_RATE.items()
                },
            },
        },
    }
    secrets = {
        f"reserve_price[{p.property_id}]": p.reserve_price
        for p in gm.current_properties.values()
    }
    visibility.assert_no_leaks(
        payload, f"public_round(round={gm.current_round})",
        forbidden=FORBIDDEN_IN_BROADCAST, secret_values=secrets,
    )
    return payload


# ── after the round resolves ──────────────────────────────────────────────

def public_results(gm: GameManager, result: RoundResult) -> Dict[str, Any]:
    """The reveal: winners, the now-published reserve, and what the year did.

    ``all_bids`` is never included. A fund learns whether it won, what the winning
    bid was, and what the seller's floor had been -- not what every other fund bid.
    """
    auctions = []
    for pid, auction in result.auction_results.items():
        deal = gm.all_properties.get(pid)
        outcome = result.property_outcomes.get(pid)
        auctions.append({
            "property_id": pid,
            "sold": auction.sold,
            "reason": auction.reason,
            "winning_team_id": auction.winning_team_id,
            "winning_bid": _num(auction.winning_bid),
            "winning_ltv": _num(auction.winning_ltv),
            "reserve_price": _num(auction.reserve_price),
            "realized_value": _num(outcome.exit_value) if outcome else None,
            "realized_noi": _num(outcome.exit_noi) if outcome else None,
            "noi_growth_actual": _num(outcome.noi_growth_actual) if outcome else None,
            "cap_rate_actual": _num(outcome.cap_rate_actual) if outcome else None,
            "asking_price": _num(deal.asking_price) if deal else None,
        })

    payload = {
        "round_number": result.round_number,
        "auctions": auctions,
        "market": public_market(result.market_state),
        "pnl": [_channels_to_dict(fund_channels(gm, tid)) for tid in gm.teams],
        "standings": public_standings(gm),
    }
    visibility.assert_no_leaks(
        payload, f"public_results(round={result.round_number})",
        forbidden=FORBIDDEN_IN_RESULTS,
    )
    return payload


def _channels_to_dict(c: FundChannels) -> Dict[str, Any]:
    return {
        "team_id": c.team_id,
        "team_name": c.team_name,
        "nav": _num(c.nav),
        "cumulative_return": _num(c.cumulative_return),
        "value_channel": _num(c.value_channel),
        "noi_income": _num(c.noi_income),
        "interest_paid": _num(c.interest_paid),
        "acquisition_costs": _num(c.acquisition_costs),
        "reserves": _num(c.reserves),
        "net_carry": _num(c.net_carry),
        "gross_ltv": _num(c.gross_ltv),
        "weighted_debt_rate": _num(c.weighted_debt_rate),
        "return_on_cost": _num(c.return_on_cost),
        "assets": c.assets,
    }


def public_standings(gm: GameManager) -> List[Dict[str, Any]]:
    board = gm.get_leaderboard()
    payload = [
        {
            "rank": i + 1,
            "team_id": row["team_id"],
            "team_name": row["team_name"],
            "nav": _num(row["nav"]),
            "cash": _num(row["cash"]),
            "debt": _num(row["debt"]),
            "assets": row["properties"],
            "cumulative_return": _num(row["cumulative_return"]),
        }
        for i, row in enumerate(board)
    ]
    visibility.assert_no_leaks(
        payload, "public_standings", forbidden=FORBIDDEN_IN_RESULTS
    )
    return payload


def _analytics_to_dict(a: TeamAnalytics) -> Dict[str, Any]:
    return {
        "team_id": a.team_id,
        "team_name": a.team_name,
        "properties_scored": a.properties_scored,
        "valuation_mae": _num(a.valuation_mae),
        "valuation_mape": _num(a.valuation_mape),
        "noi_growth_mae": _num(a.noi_growth_mae),
        "downside_brier": _num(a.downside_brier),
        "naive_valuation_mae": _num(a.naive_valuation_mae),
        "value_added_vs_naive": _num(a.value_added_vs_naive),
        "override_count": a.override_count,
        "avg_bid_override": _num(a.avg_bid_override),
        "avg_ltv_override": _num(a.avg_ltv_override),
        "properties_won": a.properties_won,
        "avg_realized_return": _num(a.avg_realized_return),
    }


def public_analytics(gm: GameManager) -> List[Dict[str, Any]]:
    """The analytics board. Deliberately separate from the NAV board."""
    payload = [_analytics_to_dict(a) for a in analytics_leaderboard(gm)]
    visibility.assert_no_leaks(
        payload, "public_analytics", forbidden=FORBIDDEN_IN_RESULTS
    )
    return payload


def _attempt_to_dict(a: AttemptAssessment) -> Dict[str, Any]:
    return {
        "team_id": a.team_id,
        "property_id": a.property_id,
        "round_number": a.round_number,
        "model_label": a.model_label,
        "decision_label": a.decision_label,
        "outcome_label": a.outcome_label,
        "override_label": a.override_label,
        "headline": a.headline,
        "case_labels": list(a.case_labels),
        "valuation_error_pct": _num(a.valuation_error_pct),
        "asking_price": _num(a.asking_price),
        "bid_override": _num(a.bid_override),
        "ltv_override": _num(a.ltv_override),
        "realized_return": _num(a.realized_return),
        "won": a.won,
    }


def public_debrief(gm: GameManager) -> Dict[str, Any]:
    """The ten questions, answered from recorded history. Computed, never narrated."""
    debrief = debrief_answers(gm)
    payload = {
        "answers": [
            {
                "number": a.number,
                "question": a.question,
                "answer": a.answer,
                "detail": a.detail,
                "team_id": a.team_id,
            }
            for a in debrief.answers
        ],
        "channels": [_channels_to_dict(c) for c in debrief.channels],
        "standings": public_standings(gm),
        "analytics": [_analytics_to_dict(a) for a in debrief.analytics],
        "override_summary": {
            k: (_num(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            for k, v in debrief.override_summary.items()
        },
        "case_counts": dict(debrief.case_counts),
        "examples": {
            case: _attempt_to_dict(attempt)
            for case, attempt in debrief.examples.items()
        },
    }
    visibility.assert_no_leaks(
        payload, "public_debrief", forbidden=FORBIDDEN_IN_RESULTS
    )
    return payload


# ── addressed to one fund ─────────────────────────────────────────────────

def team_private_view(gm: GameManager, team_id: str) -> Dict[str, Any]:
    """What ONE fund sees about itself: its forecast, its policy, its book.

    Scoped to a single team by construction and checked for it: this is the payload
    where another fund's model could leak, so the guarantee is asserted, not assumed.
    """
    if team_id not in gm.teams:
        raise KeyError(f"unknown team: {team_id}")
    team = gm.teams[team_id]

    predictions = {
        pid: {
            "property_id": pid,
            "forecast": {
                "model_name": pred.model_name,
                "predicted_fair_value": _num(pred.predicted_fair_value),
                "predicted_noi_growth": _num(pred.predicted_noi_growth),
                "probability_of_downside": _num(pred.probability_of_downside),
                "confidence": _num(pred.confidence),
                "predicted_exit_cap": _num(pred.predicted_exit_cap),
            },
            "policy": {
                "max_bid": _num(pred.max_bid),
                "target_ltv": _num(pred.target_ltv),
            },
        }
        for pid, pred in team.model_predictions.items()
    }

    payload = {
        "team_id": team.team_id,
        "team_name": team.team_name,
        "cash": _num(team.cash),
        "nav": _num(team.nav),
        "debt": _num(team.debt),
        "cumulative_return": _num(team.cumulative_return),
        # Ordered by acquisition, then by id. A holdings dict loses its order when
        # a snapshot is canonically encoded, so listing it as-is would show a fund's
        # book in a different order after a restart -- with the same buildings at the
        # same values, which is the hardest kind of difference to notice.
        "holdings": [
            {
                "property_id": h.property_id,
                "property_type": h.property_type,
                "submarket": h.submarket,
                "purchase_price": _num(h.purchase_price),
                "purchase_round": h.purchase_round,
                "equity_invested": _num(h.equity_invested),
                "debt_amount": _num(h.debt_amount),
                "debt_rate": _num(h.debt_rate),
                "current_noi": _num(h.current_noi),
                "current_value": _num(h.current_value),
            }
            for h in sorted(
                team.properties.values(),
                key=lambda holding: (holding.purchase_round, holding.property_id),
            )
        ],
        "model_output": predictions,
        "overrides": [
            {
                "property_id": o.property_id,
                "round_number": o.round_number,
                "model_max_bid": _num(o.model_max_bid),
                "actual_bid": _num(o.actual_bid),
                "model_target_ltv": _num(o.model_target_ltv),
                "actual_ltv": _num(o.actual_ltv),
                "bid_override": _num(o.bid_override),
                "ltv_override": _num(o.ltv_override),
            }
            for o in team.override_history
        ],
        "channels": _channels_to_dict(fund_channels(gm, team_id)),
        # V2: the fund's own resolved operating years, oldest first. Professor
        # and fund share this view; no other fund's stances or shocks appear.
        "operating_history": [
            {
                "round": int(round_number),
                "results": [
                    {
                        "property_id": r.property_id,
                        "stance": r.stance,
                        "shock_hit": r.shock_hit,
                        "shock_probability": _num(r.shock_probability),
                        "shock_noi_impact": _num(r.shock_noi_impact),
                        "maintenance_hit": r.maintenance_hit,
                        "maintenance_charge": _num(r.maintenance_charge),
                        "rent_miss": _num(r.rent_miss),
                        "total_noi_impact": _num(r.total_noi_impact),
                        "total_cash_impact": _num(r.total_cash_impact),
                    }
                    for r in results
                ],
            }
            for round_number, results in sorted(
                gm.teams[team_id].operating_history.items(), key=lambda kv: int(kv[0])
            )
        ],
    }
    visibility.assert_no_leaks(
        payload, f"team_private_view({team_id})", forbidden=FORBIDDEN_IN_TEAM_VIEW
    )
    visibility.assert_single_team(payload, team_id, f"team_private_view({team_id})")
    return payload
