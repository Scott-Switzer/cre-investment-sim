"""
Service operations.

Every function here is stateless: it takes a snapshot, restores a live
``GameManager``, performs exactly one engine operation, and returns the new
snapshot plus the student-safe projection. Nothing is cached between calls, so a
Cloud Run instance can be recycled mid-game without any effect on the result.

No game rule lives in this module. It orchestrates; the engine decides.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.game.adjudicator import Bid
from src.game.manager import GameManager, game_stage

from . import bundles, public, serde
from .bundles import GameBundle
from .contracts import (
    Decision,
    PropertySubmission,
    TeamSpec,
    submissions_to_predictions,
)

GAME_NAME = "cre-investment-committee"


class EngineOpError(RuntimeError):
    """A caller asked for something the engine's state machine forbids."""


# ── health ────────────────────────────────────────────────────────────────

def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "game": GAME_NAME,
        "engine_version": bundles.list_bundles()[0].engine_version
        if bundles.list_bundles()
        else "0.1.0",
        "economics_version": bundles.list_bundles()[0].economics_version
        if bundles.list_bundles()
        else "unfrozen",
        "economics_digest": bundles.economics_digest(),
        "schema_version": bundles.BUNDLE_SCHEMA_VERSION,
        "serde_schema_version": serde.SERDE_SCHEMA_VERSION,
    }


# ── the candidate pool ────────────────────────────────────────────────────


def bundle_pool(bundle_id: str) -> Dict[str, Any]:
    """Every candidate property a bundle's models were trained against.

    Added in Phase 1 because the game service must validate an uploaded model
    *before* it creates a game: `create-game-state` already hard-rejects a model
    that does not cover the pool, but it does so by refusing to start, which is far
    too late to tell a student which rows are wrong.

    It returns the pool through `public_deal`, the same projection a player sees
    during a round, so the game service never reads a CSV and there is never a
    second representation of a building (risk R5). Nothing here is hidden: these
    are precisely the fields the published student packet already contains. The
    seller's reserve and every future outcome stay inside the engine.

    `candidate_pool_hash` is recomputed live, so a caller can assert the pool it
    just received is the pool the bundle pins, rather than trusting the bundle file.
    """
    bundle = bundles.load_bundle(bundle_id)
    ok, message = bundles.verify_bundle_integrity(bundle)
    if not ok:
        raise bundles.BundleIntegrityError(
            f"bundle '{bundle_id}' failed its integrity check: {message}"
        )

    gm = GameManager(bundles.game_config_for_bundle(bundle))
    properties = [gm.all_properties[pid] for pid in sorted(gm.all_properties)]
    return {
        "bundle": bundle.to_dict(),
        "candidate_pool_hash": bundles.compute_candidate_pool_hash(properties),
        "pool_count": len(properties),
        "properties": public.public_properties(properties),
    }


# ── create ────────────────────────────────────────────────────────────────

def create_game_state(
    bundle_id: str,
    teams: List[TeamSpec],
    scenario: str = "Base Case",
) -> Tuple[GameBundle, Dict[str, Any], Dict[str, Any]]:
    """Open a session's initial state: the pool, the teams, and round one open.

    The seed comes from the bundle and nowhere else. There is no request field a
    caller could use to choose one, which is the point: a different seed would keep
    the property ids and change what they mean, silently invalidating every
    student's pre-class model.
    """
    bundle = bundles.load_bundle(bundle_id)
    ok, message = bundles.verify_bundle_integrity(bundle)
    if not ok:
        raise bundles.BundleIntegrityError(
            f"bundle '{bundle_id}' failed its integrity check: {message}"
        )

    config = bundles.game_config_for_bundle(bundle, scenario=scenario)
    gm = GameManager(config)

    seen: set[str] = set()
    for spec in teams:
        if spec.team_id in seen:
            raise EngineOpError(f"duplicate team_id '{spec.team_id}'")
        seen.add(spec.team_id)
        predictions = submissions_to_predictions(spec.submissions)
        _verify_submission_covers_pool(gm, spec, predictions)
        gm.add_team(spec.team_id, spec.team_name, predictions)

    gm.log("game created", bundle_id=bundle.bundle_id, teams=len(gm.teams))
    gm.start_game()

    return bundle, serde.snapshot_game(gm), public.public_round(gm)


def _verify_submission_covers_pool(
    gm: GameManager, spec: TeamSpec, predictions: Dict[str, Any]
) -> None:
    """A model must describe the pool it will be asked about -- or it is refused.

    No warning and no partial acceptance: a submission that does not match the
    bundle's pool is rejected before play, because a mismatched model produces
    confident nonsense and the student would never know why.
    """
    pool_ids = set(gm.all_properties.keys())
    submitted = set(predictions.keys())
    if not submitted:
        return  # a seat may play without a model; the engine treats it as no view
    missing = pool_ids - submitted
    extra = submitted - pool_ids
    if missing or extra:
        raise EngineOpError(
            f"model for '{spec.team_id}' does not match this dataset: "
            f"{len(missing)} properties missing, {len(extra)} unknown. "
            "This model was built for a different property dataset. Download the "
            "correct packet or create a session using the matching bundle."
        )


# ── open ──────────────────────────────────────────────────────────────────

def open_round(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """Advance to the next round and return what funds may see about it."""
    gm = serde.restore_game(state)
    if gm.game_complete:
        return serde.snapshot_game(gm), public.public_round(gm), True
    if gm.round_state.value != "resolved":
        raise EngineOpError(
            f"cannot open a round while the current round is "
            f"'{gm.round_state.value}'; resolve it first"
        )

    gm.advance_round()
    gm.log("round opened", stage=game_stage(gm))
    return serde.snapshot_game(gm), public.public_round(gm), gm.game_complete


# ── resolve ───────────────────────────────────────────────────────────────

def resolve_round(
    state: Dict[str, Any], decisions: List[Decision]
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, str]], bool]:
    """Submit this round's decisions, lock, and resolve the market.

    A decision the rules refuse is *reported*, not crashed on: an over-levered bid
    is a student error worth showing them, not a server fault. The engine's own
    validation decides, so there is never a second opinion about what is legal.
    """
    gm = serde.restore_game(state)
    if gm.round_state.value != "open":
        raise EngineOpError(
            f"cannot resolve while the round is '{gm.round_state.value}'"
        )

    rejected: List[Dict[str, str]] = []
    for decision in decisions:
        if decision.action != "BID":
            continue
        if decision.bid is None or decision.ltv is None:
            rejected.append({
                "team_id": decision.team_id,
                "property_id": decision.property_id,
                "reason": "a BID requires both a price and an LTV",
            })
            continue
        if decision.team_id not in gm.teams:
            rejected.append({
                "team_id": decision.team_id,
                "property_id": decision.property_id,
                "reason": f"unknown team '{decision.team_id}'",
            })
            continue
        _record_override(gm, decision)
        try:
            gm.submit_bid(Bid(
                team_id=decision.team_id,
                property_id=decision.property_id,
                bid_price=decision.bid,
                ltv=decision.ltv,
                round_number=gm.current_round,
                timestamp="api",
            ))
        except (ValueError, RuntimeError) as exc:
            rejected.append({
                "team_id": decision.team_id,
                "property_id": decision.property_id,
                "reason": str(exc),
            })

    gm.lock_round()
    result = gm.resolve_round()
    gm.log("round resolved", round=result.round_number,
           rejected=len(rejected))

    snapshot = serde.snapshot_game(gm)
    results = public.public_results(gm, result)
    analytics = public.public_analytics(gm)
    return snapshot, results, analytics, rejected, gm.game_complete


def _record_override(gm: GameManager, decision: Decision) -> None:
    """Note a deliberate deviation from the team's own policy before the auction.

    Recorded on submission rather than on winning, because the interesting fact is
    that the manager chose to exceed their own ceiling -- whether or not the market
    happened to award them the asset.
    """
    team = gm.teams.get(decision.team_id)
    if team is None:
        return
    prediction = team.model_predictions.get(decision.property_id)
    max_bid = decision.model_max_bid
    target_ltv = decision.model_target_ltv
    if prediction is not None:
        max_bid = prediction.max_bid if max_bid is None else max_bid
        target_ltv = prediction.target_ltv if target_ltv is None else target_ltv
    if max_bid is None or decision.bid is None:
        return
    gm.log(
        "decision submitted",
        team=decision.team_id,
        property=decision.property_id,
        bid_override=round(decision.bid - float(max_bid), 6),
        ltv_override=(
            None if (target_ltv is None or decision.ltv is None)
            else round(decision.ltv - float(target_ltv), 6)
        ),
    )


# ── finalize ──────────────────────────────────────────────────────────────

def finalize_game(state: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """The debrief: standings, the analytics board, and the ten answers.

    Deliberately a *view* rather than a second resolution step. It adds no game
    logic -- every number comes from history that ``resolve-round`` already
    recorded -- so folding it into resolve-round would only hide when the debrief
    is allowed to be read.

    It is genuinely read-only, including of the event log. An earlier version
    appended a "game finalized" entry, which made the returned state differ from
    the state it was given; that quietly contradicted the word "view", and it made
    "call the debrief twice, get the same answer" a claim nobody could test.
    """
    gm = serde.restore_game(state)
    standings = public.public_standings(gm)
    analytics = public.public_analytics(gm)
    debrief = public.public_debrief(gm)
    return serde.snapshot_game(gm), standings, analytics, debrief
