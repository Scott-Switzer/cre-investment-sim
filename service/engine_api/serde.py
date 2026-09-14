"""
The JSON serialisation boundary.

The engine is stateful in memory: ``GameManager`` owns the property pool, the round
machine, the market history and every fund's portfolio, and ``Adjudicator`` holds a
live numpy generator whose stream advances inside ``advance_market``. A Cloud Run
container cannot hold that between calls, so this module makes every byte of it
round-trippable through JSON with **no loss**.

Nothing here changes a rule or a coefficient. It is a faithful description of the
state the engine already keeps, written explicitly rather than by reflection, so a
new field on any engine dataclass fails loudly in a test instead of being silently
dropped from a snapshot.

Why the RNG state is serialised rather than re-derived
-----------------------------------------------------
``advance_market`` draws from a generator that has already been consumed by earlier
rounds. Re-seeding it per round would change every market path, which is an
economics change. Capturing the generator's bit state keeps the engine bit-for-bit
identical across a serialisation boundary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np

from src.game.adjudicator import (
    Adjudicator,
    AuctionResult,
    Bid,
    MarketState,
    ModelPrediction,
    OverrideRecord,
    PropertyHolding,
    PropertyMarket,
    PropertyOutcome,
    RoundResult,
    RoundState,
    TeamState,
)
from src.game.manager import GameConfig, GameManager

# Bumped to 2 when `team_order` and `property_order` were added. The bump is
# deliberate, not cosmetic: a version guard only earns its keep if adding a field
# forces a decision.
#
# Both fields exist for the same reason. A snapshot is transported as *canonical*
# JSON, and canonical JSON sorts object keys, so insertion order is silently lost
# across the boundary while two things still depend on it:
#
#   teams      -- which fund appears first on a tied leaderboard, and the order of
#                 the fund list and the P&L bridge.
#   properties -- which four buildings each round offers. `_setup_scored_round`
#                 slices the pool by position, so losing the order changes the
#                 lineup; with state now persisting between HTTP calls, the same
#                 session could offer different assets before and after a restart.
#
# Recording both orders explicitly removes the dependency on an ordering the
# encoding is entitled to discard, rather than relying on it holding by luck.
SERDE_SCHEMA_VERSION = 2


class SerdeError(RuntimeError):
    """Raised when a snapshot cannot be read back into an identical engine."""


# ── scalar helpers ────────────────────────────────────────────────────────

def _f(value: Any) -> Optional[float]:
    """Floats are stored at full repr precision; None passes through."""
    if value is None:
        return None
    return float(value)


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


# ── leaf types ────────────────────────────────────────────────────────────

def game_config_to_dict(cfg: GameConfig) -> Dict[str, Any]:
    return {
        "seed": int(cfg.seed),
        "starting_equity": _f(cfg.starting_equity),
        "total_rounds": int(cfg.total_rounds),
        "properties_per_round": int(cfg.properties_per_round),
        "practice_round": bool(cfg.practice_round),
        "scenario": str(cfg.scenario),
    }


def game_config_from_dict(d: Dict[str, Any]) -> GameConfig:
    return GameConfig(
        seed=int(d["seed"]),
        starting_equity=float(d["starting_equity"]),
        total_rounds=int(d["total_rounds"]),
        properties_per_round=int(d["properties_per_round"]),
        practice_round=bool(d["practice_round"]),
        scenario=str(d["scenario"]),
    )


def model_prediction_to_dict(p: ModelPrediction) -> Dict[str, Any]:
    return {
        "property_id": p.property_id,
        "predicted_fair_value": _f(p.predicted_fair_value),
        "predicted_noi_growth": _f(p.predicted_noi_growth),
        "probability_of_downside": _f(p.probability_of_downside),
        "max_bid": _f(p.max_bid),
        "target_ltv": _f(p.target_ltv),
        "model_name": p.model_name,
        "confidence": _f(p.confidence),
        "predicted_exit_cap": _f(p.predicted_exit_cap),
    }


def model_prediction_from_dict(d: Dict[str, Any]) -> ModelPrediction:
    return ModelPrediction(
        property_id=d["property_id"],
        predicted_fair_value=float(d["predicted_fair_value"]),
        predicted_noi_growth=float(d["predicted_noi_growth"]),
        probability_of_downside=(
            None if d.get("probability_of_downside") is None
            else float(d["probability_of_downside"])
        ),
        max_bid=float(d["max_bid"]),
        target_ltv=float(d["target_ltv"]),
        model_name=d.get("model_name", "unknown"),
        confidence=None if d.get("confidence") is None else float(d["confidence"]),
        predicted_exit_cap=(
            None if d.get("predicted_exit_cap") is None
            else float(d["predicted_exit_cap"])
        ),
    )


def property_holding_to_dict(h: PropertyHolding) -> Dict[str, Any]:
    return {
        "property_id": h.property_id,
        "purchase_price": _f(h.purchase_price),
        "purchase_round": int(h.purchase_round),
        "equity_invested": _f(h.equity_invested),
        "debt_amount": _f(h.debt_amount),
        "debt_rate": _f(h.debt_rate),
        "amortization_years": int(h.amortization_years),
        "current_noi": _f(h.current_noi),
        "current_value": _f(h.current_value),
        "property_type": h.property_type,
        "submarket": h.submarket,
    }


def property_holding_from_dict(d: Dict[str, Any]) -> PropertyHolding:
    return PropertyHolding(
        property_id=d["property_id"],
        purchase_price=float(d["purchase_price"]),
        purchase_round=int(d["purchase_round"]),
        equity_invested=float(d["equity_invested"]),
        debt_amount=float(d["debt_amount"]),
        debt_rate=float(d["debt_rate"]),
        amortization_years=int(d["amortization_years"]),
        current_noi=float(d["current_noi"]),
        current_value=float(d["current_value"]),
        property_type=d["property_type"],
        submarket=d["submarket"],
    )


def override_record_to_dict(o: OverrideRecord) -> Dict[str, Any]:
    return {
        "property_id": o.property_id,
        "round_number": int(o.round_number),
        "model_max_bid": _f(o.model_max_bid),
        "actual_bid": _f(o.actual_bid),
        "model_target_ltv": _f(o.model_target_ltv),
        "actual_ltv": _f(o.actual_ltv),
        "bid_override": _f(o.bid_override),
        "ltv_override": _f(o.ltv_override),
    }


def override_record_from_dict(d: Dict[str, Any]) -> OverrideRecord:
    return OverrideRecord(
        property_id=d["property_id"],
        round_number=int(d["round_number"]),
        model_max_bid=float(d["model_max_bid"]),
        actual_bid=float(d["actual_bid"]),
        model_target_ltv=float(d["model_target_ltv"]),
        actual_ltv=float(d["actual_ltv"]),
        bid_override=float(d["bid_override"]),
        ltv_override=float(d["ltv_override"]),
    )


def team_state_to_dict(t: TeamState) -> Dict[str, Any]:
    return {
        "team_id": t.team_id,
        "team_name": t.team_name,
        "cash": _f(t.cash),
        "equity_capital": _f(t.equity_capital),
        "properties": {pid: property_holding_to_dict(h) for pid, h in t.properties.items()},
        "debt": _f(t.debt),
        "nav": _f(t.nav),
        "cumulative_return": _f(t.cumulative_return),
        # PRIVATE_TEAM_ONLY: never emitted by a public serialiser.
        "model_predictions": {
            pid: model_prediction_to_dict(p) for pid, p in t.model_predictions.items()
        },
        "override_history": [override_record_to_dict(o) for o in t.override_history],
        "cumulative_income": _f(t.cumulative_income),
        "cumulative_interest": _f(t.cumulative_interest),
        "cumulative_purchase_price": _f(t.cumulative_purchase_price),
        "cumulative_acquisition_costs": _f(t.cumulative_acquisition_costs),
        "cumulative_reserves": _f(t.cumulative_reserves),
    }


def team_state_from_dict(d: Dict[str, Any]) -> TeamState:
    return TeamState(
        team_id=d["team_id"],
        team_name=d["team_name"],
        cash=float(d["cash"]),
        equity_capital=float(d["equity_capital"]),
        properties={
            pid: property_holding_from_dict(h) for pid, h in d.get("properties", {}).items()
        },
        debt=float(d["debt"]),
        nav=float(d["nav"]),
        cumulative_return=float(d["cumulative_return"]),
        model_predictions={
            pid: model_prediction_from_dict(p)
            for pid, p in d.get("model_predictions", {}).items()
        },
        override_history=[
            override_record_from_dict(o) for o in d.get("override_history", [])
        ],
        cumulative_income=float(d.get("cumulative_income", 0.0)),
        cumulative_interest=float(d.get("cumulative_interest", 0.0)),
        cumulative_purchase_price=float(d.get("cumulative_purchase_price", 0.0)),
        cumulative_acquisition_costs=float(d.get("cumulative_acquisition_costs", 0.0)),
        cumulative_reserves=float(d.get("cumulative_reserves", 0.0)),
    )


def property_market_to_dict(p: PropertyMarket) -> Dict[str, Any]:
    return {
        "property_id": p.property_id,
        "property_name": p.property_name,
        "property_type": p.property_type,
        "submarket": p.submarket,
        "asking_price": _f(p.asking_price),
        "current_noi": _f(p.current_noi),
        "current_cap": _f(p.current_cap),
        "occupancy": _f(p.occupancy),
        "building_sf": _f(p.building_sf),
        "year_built": int(p.year_built),
        "max_ltv": _f(p.max_ltv),
        "debt_rate": _f(p.debt_rate),
        "amortization_years": int(p.amortization_years),
        # SERVER_SECRET_UNTIL_RESOLVE
        "reserve_price": _f(p.reserve_price),
        "units": None if p.units is None else int(p.units),
        "market_rent": _f(p.market_rent),
        "in_place_rent": _f(p.in_place_rent),
        "walt": _f(p.walt),
        "tenant_concentration": _f(p.tenant_concentration),
        "opex_ratio": _f(p.opex_ratio),
        "lease_expiry_profile": p.lease_expiry_profile,
        "property_quality": _f(p.property_quality),
        "primary_risk": p.primary_risk,
        "indicative_capex_exposure": _f(p.indicative_capex_exposure),
    }


def property_market_from_dict(d: Dict[str, Any]) -> PropertyMarket:
    return PropertyMarket(
        property_id=d["property_id"],
        property_name=d["property_name"],
        property_type=d["property_type"],
        submarket=d["submarket"],
        asking_price=float(d["asking_price"]),
        current_noi=float(d["current_noi"]),
        current_cap=float(d["current_cap"]),
        occupancy=float(d["occupancy"]),
        building_sf=float(d["building_sf"]),
        year_built=int(d["year_built"]),
        max_ltv=float(d["max_ltv"]),
        debt_rate=float(d["debt_rate"]),
        amortization_years=int(d["amortization_years"]),
        reserve_price=float(d["reserve_price"]),
        units=None if d.get("units") is None else int(d["units"]),
        market_rent=None if d.get("market_rent") is None else float(d["market_rent"]),
        in_place_rent=None if d.get("in_place_rent") is None else float(d["in_place_rent"]),
        walt=None if d.get("walt") is None else float(d["walt"]),
        tenant_concentration=(
            None if d.get("tenant_concentration") is None
            else float(d["tenant_concentration"])
        ),
        opex_ratio=None if d.get("opex_ratio") is None else float(d["opex_ratio"]),
        lease_expiry_profile=d.get("lease_expiry_profile"),
        property_quality=(
            None if d.get("property_quality") is None else float(d["property_quality"])
        ),
        primary_risk=d.get("primary_risk"),
        indicative_capex_exposure=(
            None if d.get("indicative_capex_exposure") is None
            else float(d["indicative_capex_exposure"])
        ),
    )


def market_state_to_dict(m: MarketState) -> Dict[str, Any]:
    return {
        "round_number": int(m.round_number),
        "policy_rate": _f(m.policy_rate),
        "unemployment": _f(m.unemployment),
        "employment_growth": _f(m.employment_growth),
        "inflation": _f(m.inflation),
        "vacancy": {k: _f(v) for k, v in m.vacancy.items()},
        "asking_rent_index": {k: _f(v) for k, v in m.asking_rent_index.items()},
        "cap_rate": {k: _f(v) for k, v in m.cap_rate.items()},
        "credit_conditions": _f(m.credit_conditions),
        "seed": int(m.seed),
    }


def market_state_from_dict(d: Dict[str, Any]) -> MarketState:
    return MarketState(
        round_number=int(d["round_number"]),
        policy_rate=float(d["policy_rate"]),
        unemployment=float(d["unemployment"]),
        employment_growth=float(d["employment_growth"]),
        inflation=float(d["inflation"]),
        vacancy={k: float(v) for k, v in d["vacancy"].items()},
        asking_rent_index={k: float(v) for k, v in d["asking_rent_index"].items()},
        cap_rate={k: float(v) for k, v in d["cap_rate"].items()},
        credit_conditions=float(d["credit_conditions"]),
        seed=int(d["seed"]),
    )


def bid_to_dict(b: Bid) -> Dict[str, Any]:
    return {
        "team_id": b.team_id,
        "property_id": b.property_id,
        "bid_price": _f(b.bid_price),
        "ltv": _f(b.ltv),
        "round_number": int(b.round_number),
        "timestamp": b.timestamp,
        "confidence": _f(b.confidence),
    }


def bid_from_dict(d: Dict[str, Any]) -> Bid:
    return Bid(
        team_id=d["team_id"],
        property_id=d["property_id"],
        bid_price=float(d["bid_price"]),
        ltv=float(d["ltv"]),
        round_number=int(d["round_number"]),
        timestamp=d.get("timestamp", ""),
        confidence=None if d.get("confidence") is None else float(d["confidence"]),
    )


def auction_result_to_dict(a: AuctionResult) -> Dict[str, Any]:
    return {
        "property_id": a.property_id,
        "winning_team_id": a.winning_team_id,
        "winning_bid": _f(a.winning_bid),
        "winning_ltv": _f(a.winning_ltv),
        "all_bids": [bid_to_dict(b) for b in a.all_bids],
        "reserve_price": _f(a.reserve_price),
        "sold": bool(a.sold),
        "reason": a.reason,
    }


def auction_result_from_dict(d: Dict[str, Any]) -> AuctionResult:
    return AuctionResult(
        property_id=d["property_id"],
        winning_team_id=d.get("winning_team_id"),
        winning_bid=None if d.get("winning_bid") is None else float(d["winning_bid"]),
        winning_ltv=None if d.get("winning_ltv") is None else float(d["winning_ltv"]),
        all_bids=[bid_from_dict(b) for b in d.get("all_bids", [])],
        reserve_price=float(d["reserve_price"]),
        sold=bool(d["sold"]),
        reason=d.get("reason", ""),
    )


def property_outcome_to_dict(o: PropertyOutcome) -> Dict[str, Any]:
    return {
        "property_id": o.property_id,
        "noi_growth_actual": _f(o.noi_growth_actual),
        "cap_rate_actual": _f(o.cap_rate_actual),
        "exit_value": _f(o.exit_value),
        "exit_noi": _f(o.exit_noi),
        "occupancy_change": _f(o.occupancy_change),
    }


def property_outcome_from_dict(d: Dict[str, Any]) -> PropertyOutcome:
    return PropertyOutcome(
        property_id=d["property_id"],
        noi_growth_actual=float(d["noi_growth_actual"]),
        cap_rate_actual=float(d["cap_rate_actual"]),
        exit_value=float(d["exit_value"]),
        exit_noi=float(d["exit_noi"]),
        occupancy_change=float(d["occupancy_change"]),
    )


def round_result_to_dict(r: RoundResult) -> Dict[str, Any]:
    return {
        "round_number": int(r.round_number),
        "auction_results": {
            pid: auction_result_to_dict(a) for pid, a in r.auction_results.items()
        },
        "portfolio_updates": {
            tid: team_state_to_dict(t) for tid, t in r.portfolio_updates.items()
        },
        "market_state": market_state_to_dict(r.market_state),
        "property_outcomes": {
            pid: property_outcome_to_dict(o) for pid, o in r.property_outcomes.items()
        },
    }


def round_result_from_dict(d: Dict[str, Any]) -> RoundResult:
    return RoundResult(
        round_number=int(d["round_number"]),
        auction_results={
            pid: auction_result_from_dict(a) for pid, a in d["auction_results"].items()
        },
        portfolio_updates={
            tid: team_state_from_dict(t) for tid, t in d["portfolio_updates"].items()
        },
        market_state=market_state_from_dict(d["market_state"]),
        property_outcomes={
            pid: property_outcome_from_dict(o)
            for pid, o in d["property_outcomes"].items()
        },
    )


# ── whole-engine snapshot ─────────────────────────────────────────────────

def snapshot_game(gm: GameManager) -> Dict[str, Any]:
    """Every piece of engine state needed to reconstruct it in another process."""
    return {
        "serde_schema_version": SERDE_SCHEMA_VERSION,
        "config": game_config_to_dict(gm.config),
        "adjudicator_seed": int(gm.adjudicator.seed),
        "adjudicator_rng_state": json.loads(
            json.dumps(gm.adjudicator.rng.bit_generator.state)
        ),
        "team_order": list(gm.teams.keys()),
        "teams": {tid: team_state_to_dict(t) for tid, t in gm.teams.items()},
        "current_round": int(gm.current_round),
        "round_state": _enum_value(gm.round_state),
        "game_started": bool(gm.game_started),
        "game_complete": bool(gm.game_complete),
        "current_properties": {
            pid: property_market_to_dict(p) for pid, p in gm.current_properties.items()
        },
        "submitted_bids": [bid_to_dict(b) for b in gm.submitted_bids],
        "current_round_result": (
            None if gm.current_round_result is None
            else round_result_to_dict(gm.current_round_result)
        ),
        "round_history": {
            str(rn): round_result_to_dict(rr) for rn, rr in gm.round_history.items()
        },
        "market_history": [market_state_to_dict(m) for m in gm.market_history],
        # Load-bearing: rounds are drawn from this pool by position.
        "property_order": list(gm.all_properties.keys()),
        "all_properties": {
            pid: property_market_to_dict(p) for pid, p in gm.all_properties.items()
        },
        "event_log": list(gm.event_log),
    }


def restore_game(snapshot: Dict[str, Any]) -> GameManager:
    """Rebuild a live ``GameManager`` identical to the one that was snapshotted."""
    version = snapshot.get("serde_schema_version")
    if version != SERDE_SCHEMA_VERSION:
        raise SerdeError(
            f"snapshot schema {version} cannot be read by this service "
            f"(expects {SERDE_SCHEMA_VERSION})"
        )

    gm = GameManager(game_config_from_dict(snapshot["config"]))
    gm.adjudicator = Adjudicator(seed=int(snapshot["adjudicator_seed"]))
    gm.adjudicator.rng.bit_generator.state = snapshot["adjudicator_rng_state"]

    # Rebuilt in the recorded join order, not in the order the JSON happened to
    # carry. Falls back to the object's own order for a v1 snapshot that predates
    # `team_order`, so an old snapshot still loads.
    team_order = snapshot.get("team_order") or list(snapshot["teams"].keys())
    restored = {tid: team_state_from_dict(t) for tid, t in snapshot["teams"].items()}
    gm.teams = {tid: restored[tid] for tid in team_order if tid in restored}
    gm.current_round = int(snapshot["current_round"])
    gm.round_state = RoundState(snapshot["round_state"])
    gm.game_started = bool(snapshot["game_started"])
    gm.game_complete = bool(snapshot["game_complete"])
    current = {
        pid: property_market_from_dict(p)
        for pid, p in snapshot["current_properties"].items()
    }
    # Ordered by the pool, not by the JSON. `auction_results` is built by iterating
    # the round's properties, so restoring them alphabetically would reorder the
    # results a fund sees without changing a single number in them -- the kind of
    # difference that is invisible until two screens disagree about the same round.
    gm.submitted_bids = [bid_from_dict(b) for b in snapshot["submitted_bids"]]
    gm.current_round_result = (
        None
        if snapshot["current_round_result"] is None
        else round_result_from_dict(snapshot["current_round_result"])
    )
    gm.round_history = {
        int(rn): round_result_from_dict(rr)
        for rn, rr in snapshot["round_history"].items()
    }
    gm.market_history = [market_state_from_dict(m) for m in snapshot["market_history"]]
    pool = {
        pid: property_market_from_dict(p)
        for pid, p in snapshot["all_properties"].items()
    }
    # Rebuilt in the recorded pool order, because `_setup_scored_round` selects a
    # round's properties by slicing this dict. Restoring in the order the JSON
    # happens to carry would re-deal every round.
    property_order = snapshot.get("property_order") or list(pool.keys())
    gm.all_properties = {pid: pool[pid] for pid in property_order if pid in pool}
    for pid, prop in pool.items():
        gm.all_properties.setdefault(pid, prop)

    ordered_current = [pid for pid in gm.all_properties if pid in current]
    gm.current_properties = {pid: current[pid] for pid in ordered_current}
    gm.event_log = list(snapshot.get("event_log", []))
    return gm


# ── canonical JSON ────────────────────────────────────────────────────────

def dumps(obj: Any) -> str:
    """Canonical JSON: sorted keys, tight separators, full float precision.

    Canonical output is what makes "same request, same response" a byte comparison
    rather than a lenient field-by-field one.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def loads(text: str) -> Any:
    return json.loads(text)


def assert_no_numpy(obj: Any, _path: str = "$") -> None:
    """Guard against numpy scalars sneaking into a payload.

    A ``np.float64`` serialises to a JSON number but is not JSON-native, and it
    would make canonical output differ between environments.
    """
    if isinstance(obj, np.generic):
        raise SerdeError(f"numpy scalar at {_path}: {type(obj).__name__}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert_no_numpy(v, f"{_path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_no_numpy(v, f"{_path}[{i}]")
