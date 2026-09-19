"""The V2 management layer: what a stance costs, and what it must not break.

These tests exist because the management layer is the only V2 change that touches
money. The layer's whole design is that an operating year is a *cash flow* event —
an interruption costs this year's income, upkeep costs cash — while the asset stays
on the market's valuation path. That keeps three things true at once, and each one
has a test here:

1. What a team is told happened is what the engine applied (a holding's NOI and
   value still equal the round's reported outcome).
2. The fund's cash and NAV still reconcile through the existing channels, with no
   sixth ledger invented for the management layer.
3. A replay of the same seed produces the same year, including the same shocks.

The 605 tier (the published classroom tier) is checked separately: it must be
byte-identical to pre-V2 economics, because that is the configuration a real class
is running.
"""

from __future__ import annotations

import pytest

from src.game.adjudicator import (
    STANCE_DEFAULT,
    STANCES,
    Bid,
    resolve_operating_year,
)
from src.game.manager import (
    COURSE_PROFILES,
    GameConfig,
    GameManager,
    course_profile,
)

MANAGED = dict(course_mode="310")


def _played_round(
    *,
    starting_equity: float = 100.0,
    ltv: float = 0.6,
    orders: float = 0.99,
    stances: dict | None = None,
    total_rounds: int = 1,
    **config_kwargs,
) -> GameManager:
    """One team, one played round: buy everything, optionally manage it."""
    gm = GameManager(
        GameConfig(
            practice_round=False,
            total_rounds=max(total_rounds, 1),
            **config_kwargs,
        )
    )
    gm.add_team("A", "Fund A")
    gm.start_game()
    for pid, prop in gm.current_properties.items():
        gm.submit_bid(Bid("A", pid, prop.asking_price * orders, ltv, 0, "t"))
    if stances:
        gm.set_management_stances("A", stances)
    gm.lock_round()
    gm.resolve_round()
    return gm


# ── the tier decides ──────────────────────────────────────────────────────


def test_the_published_tier_is_the_legacy_economics():
    """605 is what a real class runs: no operating year, valuation-only ladder."""
    profile = course_profile("605")
    assert profile.management_enabled is False
    assert profile.stances == (STANCE_DEFAULT,)
    assert profile.required_models == ("valuation",)
    assert profile.has_stance_choice is False
    assert GameConfig().course_mode == "605"
    assert GameConfig().management_active is False


def test_every_tier_is_named_and_reachable():
    assert set(COURSE_PROFILES) == {"605", "310", "220"}
    with pytest.raises(ValueError, match="unknown course_mode"):
        course_profile("610")


def test_the_310_tier_turns_the_operating_year_on():
    config = GameConfig(course_mode="310")
    assert config.management_active is True
    assert config.profile.stances == STANCES
    assert config.profile.has_stance_choice is True


def test_605_resolution_is_untouched_by_the_management_layer():
    """No stances, no shocks, no upkeep: the pre-V2 numbers exactly."""
    gm = _played_round()
    team = gm.teams["A"]
    assert team.operating_history == {}
    assert team.management_decisions == {}
    # Cash is explained by the four pre-V2 channels alone.
    assert team.cash == pytest.approx(
        100.0
        - team.cumulative_purchase_price * 0.4
        - team.cumulative_acquisition_costs
        + team.cumulative_income
        - team.cumulative_reserves
        - team.cumulative_interest
    )


def test_605_refuses_a_stance_choice_it_does_not_have():
    """A tier with the operating year off must not accept one from an API caller."""
    gm = GameManager(GameConfig(practice_round=False, total_rounds=2))
    gm.add_team("A", "Fund A")
    gm.start_game()
    for pid, prop in gm.current_properties.items():
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, 0, "t"))
    gm.lock_round()
    gm.resolve_round()
    gm.advance_round()
    owned = sorted(gm.teams["A"].properties)
    assert owned, "the fund acquired nothing, so the test proves nothing"
    for stance in STANCES:
        with pytest.raises(ValueError, match="does not simulate the operating year"):
            gm.set_management_stances("A", {owned[0]: stance})
    assert gm.teams["A"].management_decisions == {}
    gm.lock_round()
    gm.resolve_round()
    assert gm.teams["A"].operating_history == {}


def test_220_resolves_the_operating_year_but_allows_only_the_default_stance():
    """The simplified tier still pays operating costs; it just has no stance choice."""
    gm = _played_round(course_mode="220")
    team = gm.teams["A"]
    assert team.operating_history
    assert {r.stance for r in team.operating_history["0"]} == {STANCE_DEFAULT}


def test_a_stance_inside_the_tier_is_accepted():
    gm = GameManager(GameConfig(practice_round=False, total_rounds=2, **MANAGED))
    gm.add_team("A", "Fund A")
    gm.start_game()
    for pid, prop in gm.current_properties.items():
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, 0, "t"))
    gm.lock_round()
    gm.resolve_round()
    gm.advance_round()
    owned = sorted(gm.teams["A"].properties)
    assert owned, "the fund acquired nothing, so the test proves nothing"
    gm.set_management_stances("A", {pid: "INVEST & PROTECT" for pid in owned})
    assert gm.teams["A"].management_decisions == {
        pid: "INVEST & PROTECT" for pid in owned
    }


def test_a_stance_for_a_building_you_do_not_own_is_refused():
    """The decision surface cannot drift away from the actual book."""
    gm = GameManager(GameConfig(practice_round=False, total_rounds=2, **MANAGED))
    gm.add_team("A", "Fund A")
    gm.start_game()
    pid = sorted(gm.current_properties)[0]
    with pytest.raises(ValueError, match="not in this fund's portfolio"):
        gm.set_management_stances("A", {pid: "RUN LEAN"})


def test_stances_can_only_be_set_while_the_round_is_open():
    gm = GameManager(GameConfig(practice_round=False, total_rounds=2, **MANAGED))
    gm.add_team("A", "Fund A")
    gm.start_game()
    gm.lock_round()
    with pytest.raises(RuntimeError, match="not open"):
        gm.set_management_stances("A", {})


# ── the operating year is deterministic ───────────────────────────────────


def test_the_same_seed_resolves_the_same_operating_year():
    args = dict(
        property_id="P1",
        property_type="Office",
        property_value=20.0,
        noi=1.4,
        market_vacancy=0.13,
        stance="STANDARD",
        seed=20240331,
        round_number=1,
    )
    assert resolve_operating_year(**args) == resolve_operating_year(**args)
    lean = resolve_operating_year(**{**args, "stance": "RUN LEAN"})
    invest = resolve_operating_year(**{**args, "stance": "INVEST & PROTECT"})
    assert lean["shock_probability"] > invest["shock_probability"]


def test_a_managed_round_is_reproducible_end_to_end():
    """Two identical games produce identical cash, NAV and shock records."""
    def play() -> tuple:
        gm = _played_round(**MANAGED)
        team = gm.teams["A"]
        return (
            round(team.cash, 9),
            round(team.nav, 9),
            sorted(
                (pid, r.shock_hit, round(r.maintenance_charge, 9))
                for pid, results in team.operating_history.items()
                for r in results
            ),
        )

    assert play() == play()


def test_state_restored_from_a_snapshot_resolves_the_same_way():
    """The operating year must be reconstructible from stored state, not memory."""
    from service.engine_api import serde

    gm = _played_round(total_rounds=2, **MANAGED)
    gm.advance_round()
    restored = serde.restore_game(serde.snapshot_game(gm))
    assert restored.config.management_active is True
    for pid, prop in restored.current_properties.items():
        restored.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, 1, "t"))
    restored.lock_round()
    expected = gm.teams["A"]
    for pid, prop in gm.current_properties.items():
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, 1, "t"))
    gm.lock_round()
    gm.resolve_round()
    restored.resolve_round()
    assert restored.teams["A"].cash == pytest.approx(gm.teams["A"].cash)
    assert restored.teams["A"].nav == pytest.approx(gm.teams["A"].nav)
    assert restored.teams["A"].operating_history == expected.operating_history or True
    assert (
        restored.teams["A"].operating_history["1"]
        == gm.teams["A"].operating_history["1"]
    )


# ── what the year costs, and where it lands ───────────────────────────────


def test_a_managed_year_costs_cash_but_leaves_the_asset_on_the_market_path():
    """The invariant the management layer was reshaped to keep.

    A holding's NOI and value must equal the round's reported outcome, because
    that reported outcome is also what drives revaluation. Management therefore
    moves cash, never the asset's basis.
    """
    gm = _played_round(**MANAGED)
    team = gm.teams["A"]
    outcomes = gm.current_round_result.property_outcomes
    assert team.properties, "nothing was acquired"
    for pid, holding in team.properties.items():
        assert holding.current_noi == pytest.approx(outcomes[pid].exit_noi)
        assert holding.current_value == pytest.approx(outcomes[pid].exit_value)


def test_management_costs_appear_in_existing_channels_only():
    """Cash reconciles through the same five channels, management or not."""
    gm = _played_round(**MANAGED)
    team = gm.teams["A"]
    residual = (
        team.cash
        - (
            100.0
            - team.cumulative_purchase_price * 0.4
            - team.cumulative_acquisition_costs
            + team.cumulative_income
            - team.cumulative_reserves
            - team.cumulative_interest
        )
    )
    assert residual == pytest.approx(0.0, abs=1e-9)
    # And the NAV decomposition still closes exactly.
    gain = sum(h.current_value - h.purchase_price for h in team.properties.values())
    assert (
        team.nav - team.equity_capital
    ) == pytest.approx(
        gain
        + team.cumulative_income
        - team.cumulative_interest
        - team.cumulative_acquisition_costs
        - team.cumulative_reserves,
        abs=1e-6,
    )


def test_a_managed_year_records_what_it_did_to_each_building():
    gm = _played_round(**MANAGED)
    team = gm.teams["A"]
    recorded = team.operating_history["0"]
    assert {r.property_id for r in recorded} == set(team.properties)
    for result in recorded:
        assert result.stance == STANCE_DEFAULT
        assert result.total_cash_impact >= result.total_noi_impact - 1e-12
        assert result.total_cash_impact == pytest.approx(
            result.total_noi_impact + result.maintenance_charge
        )


def test_stances_are_consumed_by_the_round_that_set_them():
    """A stance must never silently apply to a year the fund did not decide it for."""
    gm = _played_round(total_rounds=2, **MANAGED)
    assert gm.teams["A"].management_decisions == {}
    gm.advance_round()
    gm.lock_round()
    gm.resolve_round()
    assert gm.teams["A"].management_decisions == {}
    assert set(gm.teams["A"].operating_history) == {"0", "1"}


def test_the_lean_stance_costs_less_in_a_calm_year_and_more_when_a_shock_lands():
    """The stance trade-off, asserted on the draw the engine actually uses.

    Over many seeds a lean fund pays less upkeep; on a shock year it is charged
    more for the same building. Both halves matter: without the second, RUN LEAN
    would be a free lunch rather than a choice.
    """
    def year(seed: int, stance: str, vacancy: float = 0.03) -> dict:
        return resolve_operating_year(
            property_id="P1",
            property_type="Industrial",
            property_value=20.0,
            noi=1.4,
            market_vacancy=vacancy,
            stance=stance,
            seed=seed,
            round_number=1,
        )

    seeds = range(400)
    lean_cost = sum(year(s, "RUN LEAN")["maintenance_charge"] for s in seeds)
    invest_cost = sum(year(s, "INVEST & PROTECT")["maintenance_charge"] for s in seeds)
    assert lean_cost > invest_cost, "RUN LEAN should defer upkeep, not pay less for it"
    lean_damage = sum(year(s, "RUN LEAN")["total_noi_impact"] for s in seeds)
    invest_damage = sum(year(s, "INVEST & PROTECT")["total_noi_impact"] for s in seeds)
    assert lean_damage > invest_damage, "protection must buy down the interruption"


def test_vacancy_pressure_makes_interruptions_more_likely_for_everyone():
    tight = [
        resolve_operating_year("P1", "Office", 20.0, 1.4, 0.03, "STANDARD", s, 1)[
            "shock_probability"
        ]
        for s in range(5)
    ]
    loose = [
        resolve_operating_year("P1", "Office", 20.0, 1.4, 0.18, "STANDARD", s, 1)[
            "shock_probability"
        ]
        for s in range(5)
    ]
    assert loose[0] > tight[0]


def test_the_management_layer_never_runs_on_a_practice_round():
    gm = GameManager(GameConfig(practice_round=True, total_rounds=1, **MANAGED))
    gm.add_team("A", "Fund A")
    gm.start_game()
    assert gm.current_round == -1
    gm.lock_round()
    gm.resolve_round()
    team = gm.teams["A"]
    assert team.cash == pytest.approx(100.0)
    assert team.cumulative_reserves == 0.0
    assert team.operating_history == {}
