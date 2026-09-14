"""
The serialisation boundary.

`GameManager` is stateful and Cloud Run is not. Everything the engine needs between
two calls therefore has to survive a trip through JSON with no loss, and the only
way to know that is to check it rather than intend it.

Three properties are tested here:

1. **Losslessness.** Snapshot, encode, decode, snapshot again -- byte identical.
2. **Completeness.** Every field of every engine dataclass appears in the snapshot.
   This is the test that fails when somebody adds a field and forgets to serialise
   it, which would otherwise surface as a subtly wrong game rather than an error.
3. **Determinism across a process boundary.** A game reconstructed from JSON and
   continued produces exactly the same future as the game it was copied from. That
   is what makes a stateless service safe: the state is the whole truth.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from service.engine_api import serde
from src.game.adjudicator import (
    Bid,
    MarketState,
    ModelPrediction,
    OverrideRecord,
    PropertyHolding,
    PropertyMarket,
    PropertyOutcome,
    TeamState,
)
from src.game.manager import GameConfig, GameManager

SEED = 40416


def _game(seed: int = SEED) -> GameManager:
    game = GameManager(GameConfig(
        seed=seed, starting_equity=100.0, total_rounds=4,
        properties_per_round=4, practice_round=True,
    ))
    game.add_team("alpha", "Alpha Fund", {
        pid: ModelPrediction(
            property_id=pid,
            predicted_fair_value=prop.asking_price * 1.05,
            predicted_noi_growth=0.025,
            probability_of_downside=0.3,
            max_bid=prop.asking_price * 0.98,
            target_ltv=0.6,
            model_name="test-model",
            confidence=0.7,
        )
        for pid, prop in list(game.all_properties.items())[:20]
    })
    game.add_team("beta", "Beta Fund")
    game.start_game()
    return game


def _round_trip(game: GameManager) -> GameManager:
    return serde.restore_game(json.loads(serde.dumps(serde.snapshot_game(game))))


# ── 1. losslessness ───────────────────────────────────────────────────────


def test_snapshot_survives_json_unchanged():
    game = _game()
    once = serde.dumps(serde.snapshot_game(game))
    twice = serde.dumps(serde.snapshot_game(_round_trip(game)))
    assert once == twice


def test_round_trip_preserves_the_pool_and_its_order():
    game = _game()
    restored = _round_trip(game)
    assert list(restored.all_properties) == list(game.all_properties)
    assert set(restored.all_properties) == set(game.all_properties)
    for pid, prop in game.all_properties.items():
        other = restored.all_properties[pid]
        assert other.reserve_price == prop.reserve_price
        assert other.asking_price == prop.asking_price
        assert other.units == prop.units
        assert other.indicative_capex_exposure == prop.indicative_capex_exposure


def test_round_trip_preserves_none_units_rather_than_turning_them_into_zero():
    """`units` is absent for an office building, not zero. The difference matters.

    A generator cell that is genuinely blank has to stay blank through the round
    trip; converting a missing value into a number would silently invent data.
    """
    game = _game()
    restored = _round_trip(game)
    absent = [p for p in game.all_properties.values() if p.units is None]
    assert absent, "this seed has no unit-less property, so nothing is being tested"
    for prop in absent:
        assert restored.all_properties[prop.property_id].units is None


def test_round_trip_preserves_team_order():
    game = _game()
    restored = _round_trip(game)
    assert list(restored.teams) == list(game.teams)


def test_round_trip_preserves_the_rng_stream():
    """The generator's bit state is serialised, not re-derived.

    Re-seeding per round would change every market path, which would be an
    economics change disguised as a serialisation detail.

    The copy is taken *before* either side draws, because a copy taken after would
    describe a generator that has already been consumed and would prove nothing.
    """
    game = _game()
    restored = _round_trip(game)
    assert [game.adjudicator.rng.normal(0, 1) for _ in range(5)] == [
        restored.adjudicator.rng.normal(0, 1) for _ in range(5)
    ]


def test_a_restored_game_continues_to_the_same_future():
    game = _game()
    restored = _round_trip(game)

    for subject in (game, restored):
        subject.lock_round()
        subject.resolve_round()
        subject.advance_round()

    assert serde.dumps(serde.snapshot_game(game)) == serde.dumps(serde.snapshot_game(restored))


def test_snapshot_rejects_an_unknown_schema_version():
    snapshot = serde.snapshot_game(_game())
    snapshot["serde_schema_version"] = serde.SERDE_SCHEMA_VERSION + 99
    with pytest.raises(serde.SerdeError, match="schema"):
        serde.restore_game(snapshot)


def test_snapshot_carries_no_numpy_scalars():
    """A numpy scalar serialises to a number but is not JSON-native.

    Left in, it makes canonical output differ between environments, which would
    break every digest comparison for reasons that have nothing to do with the game.
    """
    snapshot = serde.snapshot_game(_game())
    serde.assert_no_numpy(snapshot)


# ── 2. completeness ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def played_game():
    """A game one practice round in, so every engine object type actually exists.

    Samples are taken from a real game rather than hand-built instances, because a
    hand-built sample would let a serialiser pass while failing on real data.
    """
    game = _game()
    # Practice must be resolved before a scored round exists -- and practice never
    # awards property, so the round that produces a holding is round 1.
    game.lock_round()
    game.resolve_round()
    game.advance_round()

    team = next(iter(game.teams.values()))
    prop = next(iter(game.current_properties.values()))
    game.submit_bid(Bid(
        team_id=team.team_id,
        property_id=prop.property_id,
        bid_price=prop.reserve_price * 1.05,
        ltv=min(prop.max_ltv, 0.6),
        round_number=game.current_round,
        timestamp="test",
    ))
    game.lock_round()
    game.resolve_round()
    return game, prop, team


SERIALISED_TYPES = [
    (GameConfig, "game_config"),
    (ModelPrediction, "model_prediction"),
    (PropertyHolding, "property_holding"),
    (OverrideRecord, "override_record"),
    (TeamState, "team_state"),
    (PropertyMarket, "property_market"),
    (MarketState, "market_state"),
    (PropertyOutcome, "property_outcome"),
]


@pytest.mark.parametrize("dataclass_type,serialiser_name", SERIALISED_TYPES)
def test_every_engine_field_is_serialised(dataclass_type, serialiser_name, played_game):
    """Adding a field to an engine dataclass must fail here, not in class.

    The serialisers are written by hand rather than by reflection, which is the
    right call for a state boundary -- but a hand-written list drifts. This closes
    the gap: a forgotten field becomes a failing test that names the field.
    """
    serialiser = getattr(serde, f"{serialiser_name}_to_dict")
    fields = {f.name for f in dataclasses.fields(dataclass_type)}
    keys = set(serialiser(_sample(dataclass_type, played_game)).keys())
    assert fields - keys == set(), f"{dataclass_type.__name__} fields not serialised"
    assert keys - fields == set(), f"{serialiser_name}_to_dict emits unknown keys"


def _sample(dataclass_type, played_game):
    game, prop, team = played_game
    if dataclass_type is GameConfig:
        return game.config
    if dataclass_type is ModelPrediction:
        return next(iter(team.model_predictions.values()))
    if dataclass_type is PropertyHolding:
        winner = next(
            (t for t in game.teams.values() if t.properties), None
        )
        if winner is None:
            pytest.skip("no holding was purchased in this seed")
        return next(iter(winner.properties.values()))
    if dataclass_type is OverrideRecord:
        return OverrideRecord(
            property_id=prop.property_id, round_number=0, model_max_bid=10.0,
            actual_bid=11.0, model_target_ltv=0.6, actual_ltv=0.65,
            bid_override=1.0, ltv_override=0.05,
        )
    if dataclass_type is TeamState:
        return team
    if dataclass_type is PropertyMarket:
        return prop
    if dataclass_type is MarketState:
        return game.market_history[-1]
    if dataclass_type is PropertyOutcome:
        return next(iter(game.current_round_result.property_outcomes.values()))
    raise AssertionError(f"no sample defined for {dataclass_type}")


def test_snapshot_top_level_keys_are_the_documented_set():
    """A named list, so a new top-level key is a deliberate act."""
    snapshot = serde.snapshot_game(_game())
    assert set(snapshot) == {
        "serde_schema_version", "config", "adjudicator_seed", "adjudicator_rng_state",
        "team_order", "teams", "current_round", "round_state", "game_started",
        "game_complete", "current_properties", "submitted_bids", "current_round_result",
        "round_history", "market_history", "property_order", "all_properties",
        "event_log",
    }


# ── 3. determinism across a restart ───────────────────────────────────────


def test_two_independent_services_produce_identical_games():
    """Standing in for two Cloud Run instances handling the same session."""
    first = serde.dumps(serde.snapshot_game(_game()))
    second = serde.dumps(serde.snapshot_game(_game()))
    assert first == second


def test_serialising_repeatedly_is_stable():
    """No accumulating drift: snapshot -> restore -> snapshot -> restore ..."""
    game = _game()
    reference = serde.dumps(serde.snapshot_game(game))
    for _ in range(3):
        game = _round_trip(game)
        assert serde.dumps(serde.snapshot_game(game)) == reference


def test_round_selection_is_stable_across_a_round_trip():
    """The four featured assets must not change because state was persisted.

    `_setup_scored_round` slices the pool by position, so this is the property that
    would break first if the pool's order were lost -- and it would break silently,
    by offering a different building rather than by erroring.
    """
    game = _game()
    restored = _round_trip(game)
    for subject in (game, restored):
        subject.lock_round()
        subject.resolve_round()
        subject.advance_round()
    assert list(game.current_properties) == list(restored.current_properties)
