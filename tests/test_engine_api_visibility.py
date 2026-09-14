"""
The hidden-information boundary.

Everything about this game depends on a player not being able to read the answer.
If the seller's reserve or the year's realised value reaches a browser before the
round resolves, the exercise stops testing valuation and starts testing dev tools.

These tests attack the boundary rather than describe it, because a documented
guarantee with no adversarial test is a hope:

* the reserve key, and the reserve **value under any name**;
* every realised outcome field, before resolution;
* one fund's model and bids, in another fund's payload;
* the seed, which is engine metadata and never a player input.

The value check is the load-bearing one. A key check passes the moment somebody
renames `reserve_price` to `floor`, which is exactly what a leak looks like when it
is not deliberate.
"""

from __future__ import annotations

import pytest

from service.engine_api import public, serde, visibility
from service.engine_api.contracts import Decision, TeamSpec
from service.engine_api.engine import create_game_state, open_round, resolve_round
from src.game.adjudicator import Bid
from src.game.manager import GameConfig, GameManager

SEED = 20240331


def _submissions() -> list[dict]:
    from service.engine_api.fixtures import student_submissions

    return student_submissions()


def _started_game():
    """A session two funds into round one, which is the state worth attacking."""
    _, state, _ = create_game_state(
        "real605-fall26-v1",
        [
            TeamSpec(team_id="student", team_name="Student Fund", submissions=_submissions()),
            TeamSpec(team_id="rival", team_name="Rival Fund"),
        ],
    )
    state, _public, _analytics, _rejected, _done = resolve_round(state, [])
    state, round_one, _complete = open_round(state)
    return serde.restore_game(state), round_one


def _all_numbers(payload) -> list[float]:
    return visibility.collect_numbers(payload)


# ── the reserve ───────────────────────────────────────────────────────────


def test_round_payload_contains_no_reserve_key():
    game, round_payload = _started_game()
    assert round_payload["deals"], "no deals offered"
    assert not visibility.collect_keys(round_payload) & visibility.PRE_RESOLVE_SECRET_KEYS


def test_round_payload_contains_no_reserve_value_even_unnamed():
    """The attack the key check misses: shipping the number under a new name."""
    game, round_payload = _started_game()
    numbers = _all_numbers(round_payload)
    for prop in game.current_properties.values():
        assert not any(abs(n - prop.reserve_price) < 1e-9 for n in numbers), (
            f"the reserve for {prop.property_id} appears in the round payload"
        )


def test_reserve_value_check_catches_a_renamed_field():
    """Proves the guard is real: rename it and it still fails."""
    game, _ = _started_game()
    prop = next(iter(game.current_properties.values()))
    sneaky = {"deals": [{"property_id": prop.property_id, "floor": prop.reserve_price}]}
    with pytest.raises(visibility.LeakError, match="secret value"):
        visibility.assert_no_leaks(
            sneaky,
            "renamed reserve",
            forbidden=visibility.FORBIDDEN_IN_BROADCAST,
            secret_values={f"reserve_price[{prop.property_id}]": prop.reserve_price},
        )


def test_reserve_key_check_catches_the_obvious_mistake():
    with pytest.raises(visibility.LeakError, match="forbidden field"):
        visibility.assert_no_leaks(
            {"reserve_price": 12.5}, "naive leak", forbidden=visibility.FORBIDDEN_IN_BROADCAST
        )


def test_reserve_is_not_carried_inside_the_deal_dto():
    """Belt and braces: the DTO builder itself must not include the field."""
    game, _ = _started_game()
    for prop in game.current_properties.values():
        deal = public.public_deal(prop)
        assert "reserve_price" not in deal
        # The cap rate is published under the buyer's name for it. The engine's own
        # field name (`current_cap`) is internal, so the DTO is not a rename of the
        # engine object and cannot smuggle a new engine field out by accident.
        assert deal["going_in_cap"] == pytest.approx(prop.current_cap, abs=1e-6)
        assert "current_cap" not in deal


# ── realised outcomes ─────────────────────────────────────────────────────


def test_future_outcomes_are_absent_before_resolution():
    """The year's NOI growth and value must not exist until the round is resolved."""
    game, round_payload = _started_game()
    keys = visibility.collect_keys(round_payload)
    for field in ("noi_growth_actual", "cap_rate_actual", "exit_value",
                  "exit_noi", "occupancy_change"):
        assert field not in keys


def test_outcomes_are_published_after_resolution():
    """The other half of the contract: hidden before, revealed after, not never."""
    _, state, round_payload = create_game_state(
        "real605-fall26-v1",
        [TeamSpec(team_id="only", team_name="Only Fund")],
    )
    state, _public, _analytics, _rejected, _done = resolve_round(state, [])
    state, round_payload, _complete = open_round(state)
    prop = round_payload["deals"][0]

    resolved = serde.restore_game(state)
    reserve = resolved.current_properties[prop["property_id"]].reserve_price
    state, results, _, _, _ = resolve_round(state, [Decision(
        team_id="only", property_id=prop["property_id"], action="BID",
        bid=round(reserve * 1.05, 4), ltv=0.5,
    )])

    auction = next(
        a for a in results["auctions"] if a["property_id"] == prop["property_id"]
    )
    assert auction["reserve_price"] == pytest.approx(reserve, abs=1e-6)
    assert auction["realized_value"] is not None
    assert auction["noi_growth_actual"] is not None


def test_sealed_bids_are_never_published_not_even_after_the_round():
    """First-price sealed: you learn whether you won, not what the others bid."""
    resolved = _played_round_with_two_bidders()
    for payload in (resolved["results"], resolved["analytics"]):
        assert "all_bids" not in visibility.collect_keys(payload)
    for auction in resolved["results"]["auctions"]:
        assert "all_bids" not in auction


def _played_round_with_two_bidders():
    _, state, round_payload = create_game_state(
        "real605-fall26-v1",
        [TeamSpec(team_id="one", team_name="One"), TeamSpec(team_id="two", team_name="Two")],
    )
    state, _public, _analytics, _rejected, _done = resolve_round(state, [])
    state, round_payload, _complete = open_round(state)
    game = serde.restore_game(state)
    prop = round_payload["deals"][0]["property_id"]
    reserve = game.current_properties[prop].reserve_price
    decisions = [
        Decision(team_id="one", property_id=prop, action="BID",
                 bid=round(reserve * 1.05, 4), ltv=0.55),
        Decision(team_id="two", property_id=prop, action="BID",
                 bid=round(reserve * 1.02, 4), ltv=0.5),
    ]
    state, results, analytics, _, _ = resolve_round(state, decisions)
    return {"results": results, "analytics": analytics}


# ── other funds' private state ────────────────────────────────────────────


def test_team_view_names_only_that_team():
    state = _state_after_a_round()
    game = serde.restore_game(state)
    view = public.team_private_view(game, "student")
    visibility.assert_single_team(view, "student", "team view")
    assert visibility.collect_team_ids(view) == {"student"}


def test_team_view_refuses_to_include_another_funds_model():
    """The leak this payload could actually cause, tested directly."""
    state = _state_after_a_round()
    game = serde.restore_game(state)
    view = public.team_private_view(game, "student")
    # A rival's model must not be reachable from this fund's payload.
    assert "rival" not in visibility.collect_team_ids(view)
    assert set(view["model_output"]) <= set(game.teams["student"].model_predictions)


def test_single_team_assertion_rejects_a_payload_naming_a_rival():
    with pytest.raises(visibility.LeakError, match="also names"):
        visibility.assert_single_team(
            {"funds": {"student": {}, "rival": {}}}, "student", "mixed payload"
        )


def test_broadcast_payload_never_carries_a_model():
    _, round_payload = _started_game()
    for fund in round_payload["funds"]:
        assert "model_predictions" not in fund
        assert "model_output" not in fund


def test_standings_never_carry_holdings_or_models():
    state = _state_after_a_round()
    game = serde.restore_game(state)
    for row in public.public_standings(game):
        assert "properties" not in row
        assert "model_predictions" not in row
        assert "override_history" not in row


def _state_after_a_round() -> dict:
    _, state, _ = create_game_state(
        "real605-fall26-v1",
        [
            TeamSpec(team_id="student", team_name="Student Fund", submissions=_submissions()),
            TeamSpec(team_id="rival", team_name="Rival Fund"),
        ],
    )
    state, _public, _analytics, _rejected, _done = resolve_round(state, [])
    state, round_payload, _complete = open_round(state)
    game = serde.restore_game(state)
    prop = round_payload["deals"][0]["property_id"]
    decision = Decision(
        team_id="student", property_id=prop, action="BID",
        bid=round(game.current_properties[prop].reserve_price * 1.05, 4), ltv=0.55,
    )
    state, _, _, _, _ = resolve_round(state, [decision])
    return state


# ── the seed ──────────────────────────────────────────────────────────────


def test_seed_never_appears_in_a_player_payload():
    """The seed is engine metadata. A seed plus the generator is the whole game."""
    state = _state_after_a_round()
    game = serde.restore_game(state)
    for payload in (
        public.public_round(game),
        public.public_standings(game),
        public.public_analytics(game),
        public.team_private_view(game, "student"),
    ):
        keys = visibility.collect_keys(payload)
        assert "seed" not in keys
        assert "adjudicator_seed" not in keys
        assert "config" not in keys


def test_engine_state_is_never_mistaken_for_a_public_payload():
    """The snapshot is server-only; putting it in a broadcast must fail."""
    state = _state_after_a_round()
    with pytest.raises(visibility.LeakError):
        visibility.assert_no_leaks(
            {"state": state}, "snapshot broadcast",
            forbidden=visibility.FORBIDDEN_IN_BROADCAST,
        )


# ── the candidate pool (Phase 1) ──────────────────────────────────────────


def test_candidate_pool_lists_no_reserve_key():
    """The pool is what the game service hands a model validator, so a reserve
    in it would be published to every student on upload, before any auction."""
    from service.engine_api import engine

    payload = engine.bundle_pool("real605-fall26-v1")
    assert payload["properties"], "the pool is empty"
    assert not visibility.collect_keys(payload) & visibility.PRE_RESOLVE_SECRET_KEYS


def test_candidate_pool_carries_no_reserve_value_even_unnamed():
    """The same attack the round payload is tested against: renaming the number.

    Checked against the *real* reserves for this bundle's seed, so the assertion
    is about the actual secret rather than a guessed one.
    """
    from service.engine_api import engine

    gm = GameManager(GameConfig(
        seed=SEED, starting_equity=100.0, total_rounds=4,
        properties_per_round=4, practice_round=True,
    ))
    reserves = [p.reserve_price for p in gm.all_properties.values()]
    assert reserves

    numbers = set(_all_numbers(engine.bundle_pool("real605-fall26-v1")))
    leaked = [r for r in reserves if round(float(r), 6) in numbers]
    assert not leaked, f"{len(leaked)} reserve prices appear in the candidate pool"


def test_candidate_pool_carries_no_future_outcome():
    from service.engine_api import engine

    keys = visibility.collect_keys(engine.bundle_pool("real605-fall26-v1"))
    for forbidden in (
        "exit_value", "realized_value", "realized_noi", "noi_growth_actual",
        "cap_rate_actual", "next_year_noi", "next_year_value",
        "transaction_price", "reserve_price", "winning_bid", "winner",
    ):
        assert forbidden not in keys, f"the candidate pool exposes '{forbidden}'"


# ── fail-closed classification ────────────────────────────────────────────


def test_an_unclassified_field_defaults_to_server_only():
    """The default has to be the safe one, because the next field is unknown."""
    assert visibility.required_phase_for("some_new_field_nobody_classified") is \
        visibility.Visibility.SERVER_ONLY_ALWAYS


def test_every_secret_field_is_classified_as_secret():
    """A named list, so publishing one is a deliberate act rather than an accident."""
    assert visibility.required_phase_for("reserve_price") is \
        visibility.Visibility.SERVER_SECRET_UNTIL_RESOLVE
    for field in ("noi_growth_actual", "cap_rate_actual", "exit_value",
                  "exit_noi", "occupancy_change", "all_bids"):
        assert visibility.required_phase_for(field) is \
            visibility.Visibility.SERVER_SECRET_UNTIL_RESOLVE, field


def test_the_three_forbidden_sets_are_ordered_as_designed():
    broadcast = visibility.FORBIDDEN_IN_BROADCAST
    results = visibility.FORBIDDEN_IN_RESULTS
    team_view = visibility.FORBIDDEN_IN_TEAM_VIEW
    # A broadcast is the strictest: it forbids everything the other two do, plus
    # the pre-resolve secrets.
    assert results < broadcast
    assert team_view < results
    assert "reserve_price" in broadcast and "reserve_price" not in results
