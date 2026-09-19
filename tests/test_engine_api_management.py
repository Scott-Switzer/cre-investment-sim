"""The V2 management slice, exercised through the service boundary.

The engine tests in `test_management_layer.py` prove the rules. These prove the
*vertical slice*: that a session can be created at a tier, that a fund's stance
travels with the resolve call, that a stance the engine refuses is reported rather
than fatal, and that the resulting operating year reaches the fund's own view and
nobody else's.

The tier matters here in a way it does not in the engine tests: the published
classroom bundle ships the 605 tier, so the default session the professor creates
must behave exactly as before V2 existed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.engine_api import public, serde
from service.engine_api.app import app
from service.engine_api.contracts import ManagementStance, TeamSpec
from service.engine_api.engine import (
    create_game_state,
    open_round,
    resolve_round,
)
from src.game.adjudicator import Bid

BUNDLE = "real605-fall26-v1"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _funds():
    return [
        TeamSpec(team_id="alpha", team_name="Alpha Fund"),
        TeamSpec(team_id="beta", team_name="Beta Fund"),
    ]


def _session(course_mode: str | None = None, **kwargs):
    """A session one scored round in, so funds own buildings worth managing."""
    _bundle, state, _public = create_game_state(
        BUNDLE, _funds(), course_mode=course_mode, **kwargs
    )
    # Resolve the practice round, then play round one and buy something.
    state, _p, _a, _r, _rs, _done = resolve_round(state, [])
    state, _round_one, _complete = open_round(state)
    gm = serde.restore_game(state)
    for team_id in gm.teams:
        for pid, prop in gm.current_properties.items():
            gm.submit_bid(
                Bid(team_id, pid, prop.asking_price * 0.97, 0.6, gm.current_round, "t")
            )
    state = serde.snapshot_game(gm)
    state, _p, _a, _r, _rs, _done = resolve_round(state, [])
    state, _round_two, _complete = open_round(state)
    return serde.restore_game(state), state


# ── the tier is visible and recorded ──────────────────────────────────────


def test_the_default_session_plays_the_published_605_tier():
    game, state = _session()
    assert game.config.course_mode == "605"
    assert game.config.management_active is False
    config = public.public_round(game)["economics"]["management"]
    assert config["enabled"] is False
    assert config["course_mode"] == "605"
    assert config["stances"] == ["STANDARD"]
    assert config["has_stance_choice"] is False
    assert config["required_models"] == ["valuation"]


def test_a_session_can_be_opened_at_the_310_tier_and_records_that():
    game, state = _session(course_mode="310")
    assert game.config.management_active is True
    # The choice survives the snapshot round trip, so a restored session cannot
    # silently change tier halfway through a class.
    assert serde.restore_game(state).config.management_active is True
    config = public.public_round(game)["economics"]["management"]
    assert config["enabled"] is True
    assert config["course_mode"] == "310"
    assert config["has_stance_choice"] is True
    assert config["required_models"] == ["valuation", "vacancy", "income"]


def test_an_unknown_tier_is_refused_at_creation():
    from service.engine_api.engine import EngineOpError

    with pytest.raises(EngineOpError, match="unknown course_mode"):
        create_game_state(BUNDLE, _funds(), course_mode="605.5")


def test_the_tier_can_only_be_chosen_from_the_published_set(client):
    response = client.post(
        "/v1/create-game-state",
        json={"bundle_id": BUNDLE, "teams": [], "course_mode": "nope"},
    )
    assert response.status_code in (400, 422)


# ── stances ride the resolve call ─────────────────────────────────────────


def test_a_310_session_records_stances_and_reports_the_operating_year():
    game, state = _session(course_mode="310")
    owned = sorted(game.teams["alpha"].properties)
    assert owned, "no acquisitions, so nothing to manage"
    stances = [
        ManagementStance(team_id="alpha", property_id=pid, stance="INVEST & PROTECT")
        for pid in owned
    ]
    state, _public, _analytics, rejected, rejected_stances, _done = resolve_round(
        state, [], stances
    )
    assert rejected == []
    assert rejected_stances == []
    restored = serde.restore_game(state)
    history = restored.teams["alpha"].operating_history
    # Round 0 was played on the default stance; the round just resolved is round 1.
    assert set(history) == {"0", "1"}
    assert {r.property_id for r in history["1"]} == set(owned)
    assert {r.stance for r in history["1"]} == {"INVEST & PROTECT"}


def test_a_stance_for_a_building_the_fund_does_not_own_is_reported_not_fatal():
    """A bad stance is a student mistake, not a server fault. The round resolves."""
    game, state = _session(course_mode="310")
    owned = sorted(game.teams["alpha"].properties)
    state, _p, _a, rejected, rejected_stances, _done = resolve_round(
        state,
        [],
        [ManagementStance(team_id="alpha", property_id="NOT-MINE", stance="RUN LEAN")],
    )
    assert rejected == []
    assert len(rejected_stances) == 1
    assert rejected_stances[0]["property_id"] == "NOT-MINE"
    assert "not in this fund's portfolio" in rejected_stances[0]["reason"]
    restored = serde.restore_game(state)
    # The fund's holdings still resolved, on the default stance.
    assert {r.stance for r in restored.teams["alpha"].operating_history["1"]} == {
        "STANDARD"
    }


def test_a_605_session_refuses_stance_choices_but_still_resolves():
    """The published tier has no stance surface; asking for one is refused."""
    game, state = _session()
    owned = sorted(game.teams["alpha"].properties)
    state, _p, _a, rejected, rejected_stances, _done = resolve_round(
        state,
        [],
        [ManagementStance(team_id="alpha", property_id=owned[0], stance="RUN LEAN")],
    )
    assert rejected == []
    assert len(rejected_stances) == 1
    assert "does not simulate the operating year" in rejected_stances[0]["reason"]
    restored = serde.restore_game(state)
    # And no operating year was simulated at all.
    assert restored.teams["alpha"].operating_history == {}


def test_an_unknown_stance_name_is_refused_by_the_contract(client):
    response = client.post(
        "/v1/resolve-round",
        json={
            "state": {},
            "decisions": [],
            "management_stances": [
                {"team_id": "a", "property_id": "P", "stance": "YOLO"}
            ],
        },
    )
    assert response.status_code == 422


# ── what the fund sees, and what nobody else does ─────────────────────────


def test_the_fund_view_carries_its_own_operating_history():
    game, state = _session(course_mode="310")
    owned = sorted(game.teams["alpha"].properties)
    state, _p, _a, _r, _rs, _done = resolve_round(
        state,
        [],
        [
            ManagementStance(team_id="alpha", property_id=pid, stance="RUN LEAN")
            for pid in owned
        ],
    )
    restored = serde.restore_game(state)
    view = public.team_private_view(restored, "alpha")
    history = view["operating_history"]
    assert [entry["round"] for entry in history] == [0, 1]
    recorded = {r["property_id"]: r for r in history[-1]["results"]}
    assert set(recorded) == set(owned)
    for entry in recorded.values():
        assert entry["stance"] == "RUN LEAN"
        assert entry["shock_probability"] > 0
        # What the rule decided is reported, not just what it charged.
        assert set(entry) >= {
            "property_id", "stance", "shock_hit", "shock_probability",
            "shock_noi_impact", "maintenance_hit", "maintenance_charge",
            "rent_miss", "total_noi_impact", "total_cash_impact",
        }


def test_one_fund_never_sees_another_fund_operating_year():
    """Beta's own year is beta's; nothing of alpha's appears in beta's view."""
    game, state = _session(course_mode="310")
    owned = sorted(game.teams["alpha"].properties)
    state, _p, _a, _r, _rs, _done = resolve_round(
        state,
        [],
        [
            ManagementStance(team_id="alpha", property_id=pid, stance="INVEST & PROTECT")
            for pid in owned
        ],
    )
    restored = serde.restore_game(state)
    rival_view = public.team_private_view(restored, "beta")
    beta_property_ids = set(restored.teams["beta"].properties)
    for entry in rival_view["operating_history"]:
        for result in entry["results"]:
            assert result["property_id"] in beta_property_ids
            assert result["property_id"] not in owned
            # Beta never chose INVEST; only alpha did.
            assert result["stance"] != "INVEST & PROTECT"
    assert "alpha" not in str(rival_view)


def test_the_management_coefficients_are_published_not_hidden():
    """A fund must be able to price a stance before choosing it."""
    from src.game.adjudicator import (
        MANAGEMENT_INVEST_RESERVE_ADDER,
        MANAGEMENT_SHOCK_PROBABILITY,
        MANAGEMENT_STANCE_MAINTENANCE_RATE,
        MANAGEMENT_STANCE_SHOCK_MULTIPLIER,
        MANAGEMENT_STANCE_SHOCK_NOI_IMPACT,
    )

    game, _state = _session(course_mode="310")
    config = public.public_round(game)["economics"]["management"]
    assert config["invest_reserve_adder"] == pytest.approx(
        MANAGEMENT_INVEST_RESERVE_ADDER
    )
    assert config["shock_probability"] == pytest.approx(MANAGEMENT_SHOCK_PROBABILITY)
    assert config["stance_shock_multiplier"] == pytest.approx(
        MANAGEMENT_STANCE_SHOCK_MULTIPLIER
    )
    assert config["stance_shock_noi_impact"] == pytest.approx(
        MANAGEMENT_STANCE_SHOCK_NOI_IMPACT
    )
    assert config["stance_maintenance_rate"] == pytest.approx(
        MANAGEMENT_STANCE_MAINTENANCE_RATE
    )


# ── a v2 session still restores ───────────────────────────────────────────


def test_a_pre_v2_snapshot_still_resolves():
    """A deploy can land mid-class; a saved v2 game must keep playing.

    A v2 snapshot predates the course tier and the management fields, so every
    absent field must mean what the session was actually running: the 605 tier
    with the operating year off.
    """
    _bundle, state, _public = create_game_state(BUNDLE, _funds())
    legacy = dict(state)
    legacy["serde_schema_version"] = 2
    legacy["config"].pop("course_mode", None)
    legacy["config"].pop("management_enabled", None)
    for team in legacy["teams"].values():
        team.pop("management_decisions", None)
        team.pop("operating_history", None)

    restored = serde.restore_game(legacy)
    assert restored.config.course_mode == "605"
    assert restored.config.management_active is False
    state, _p, _a, _r, _rs, _done = resolve_round(legacy, [])
    assert serde.restore_game(state).config.management_active is False


def test_a_snapshot_from_the_future_is_refused():
    _bundle, state, _public = create_game_state(BUNDLE, _funds())
    state = dict(state, serde_schema_version=serde.SERDE_SCHEMA_VERSION + 1)
    with pytest.raises(serde.SerdeError, match="cannot be read"):
        serde.restore_game(state)


def test_the_published_tier_opens_the_management_surface_but_never_uses_it():
    """The 605 session is the control: the surface exists, the layer does not run.

    Exact NAV equality against a direct engine replay is already asserted by the
    pre-V2 suite; this checks the narrower thing V2 could have broken, which is
    that the published tier still simulates no operating year at all.
    """
    game, state = _session()
    assert game.config.management_active is False
    owned = sorted(game.teams["alpha"].properties)
    assert owned
    state, _p, _a, _r, _rs, _done = resolve_round(
        state,
        [],
        [
            ManagementStance(team_id="alpha", property_id=pid, stance="STANDARD")
            for pid in owned
        ],
    )
    restored = serde.restore_game(state)
    assert restored.teams["alpha"].operating_history == {}
    assert restored.teams["alpha"].management_decisions == {}
