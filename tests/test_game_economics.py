"""
Tests for the property economics the game's return actually comes from.

An acquisition earns NOI, appreciates, and pays interest. These tests pin down
the three channels and the exact identity that lets the debrief explain a fund's
NAV change without appealing to opinion.

    NAV - starting equity  ==  sum(value - purchase price)
                               + income received
                               - interest paid
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from src.game.adjudicator import (
    Adjudicator,
    Bid,
    MarketState,
    PropertyHolding,
    RoundState,
    TeamState,
    realized_year_outcome,
)


def make_team(cash: float = 100.0) -> TeamState:
    return TeamState(
        team_id="T", team_name="T", cash=cash, equity_capital=100.0, nav=cash
    )


def make_holding(
    debt_amount: float = 0.0,
    debt_rate: float = 0.063,
    noi: float = 2.0,
    value: float = 40.0,
    price: float = 40.0,
) -> PropertyHolding:
    return PropertyHolding(
        property_id="P1",
        purchase_price=price,
        purchase_round=0,
        equity_invested=price - debt_amount,
        debt_amount=debt_amount,
        debt_rate=debt_rate,
        amortization_years=25,
        current_noi=noi,
        current_value=value,
        property_type="Industrial",
        submarket="Anaheim",
    )


class TestPropertyIncome:
    def test_income_credited_to_cash(self):
        adj = Adjudicator()
        team = make_team(100.0)
        team.properties["P1"] = make_holding(noi=2.5)

        adj.collect_property_income(team)

        assert team.cash == pytest.approx(102.5)
        assert team.cumulative_income == pytest.approx(2.5)

    def test_income_accumulates_across_holdings(self):
        adj = Adjudicator()
        team = make_team(100.0)
        team.properties["P1"] = make_holding(noi=2.0)
        team.properties["P2"] = make_holding(noi=3.0)

        adj.collect_property_income(team)

        assert team.cumulative_income == pytest.approx(5.0)

    def test_team_with_no_holdings_earns_nothing(self):
        adj = Adjudicator()
        team = make_team(100.0)
        adj.collect_property_income(team)
        assert team.cash == pytest.approx(100.0)
        assert team.cumulative_income == 0.0


class TestDebtInterest:
    def test_interest_is_debt_times_rate(self):
        adj = Adjudicator()
        team = make_team(100.0)
        team.properties["P1"] = make_holding(debt_amount=60.0, debt_rate=0.065)
        team.debt = 60.0

        adj.accrue_debt_interest(team)

        assert team.cash == pytest.approx(100.0 - 60.0 * 0.065)
        assert team.cumulative_interest == pytest.approx(60.0 * 0.065)

    def test_no_debt_means_no_interest(self):
        adj = Adjudicator()
        team = make_team(100.0)
        team.properties["P1"] = make_holding(debt_amount=0.0)
        adj.accrue_debt_interest(team)
        assert team.cash == pytest.approx(100.0)
        assert team.cumulative_interest == 0.0

    def test_interest_scales_with_leverage(self):
        """Two identical assets, different leverage, different interest."""
        adj = Adjudicator()
        low = make_team(100.0)
        low.properties["P1"] = make_holding(debt_amount=30.0)
        low.debt = 30.0
        high = make_team(100.0)
        high.properties["P1"] = make_holding(debt_amount=70.0)
        high.debt = 70.0

        adj.accrue_debt_interest(low)
        adj.accrue_debt_interest(high)

        assert high.cumulative_interest > low.cumulative_interest


class TestNavDecomposition:
    def test_identity_holds_after_a_full_round(self):
        """The three channels must sum exactly to the NAV change."""
        from src.game.manager import GameConfig, GameManager

        gm = GameManager(GameConfig(seed=20240331, total_rounds=4))
        gm.add_team("A", "A")
        gm.add_team("B", "B")
        gm.start_game()
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

        pid = next(iter(gm.current_properties))
        prop = gm.current_properties[pid]
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.95, 0.6, 0, "t"))
        gm.lock_round()
        gm.resolve_round()

        for team in gm.teams.values():
            gain = sum(h.current_value - h.purchase_price for h in team.properties.values())
            residual = (
                (team.nav - team.equity_capital)
                - (gain + team.cumulative_income - team.cumulative_interest)
            )
            # NAV is rounded to 6 decimals by calculate_nav, so the identity is
            # exact to that precision rather than to machine epsilon.
            assert residual == pytest.approx(0.0, abs=1e-6), (
                f"NAV decomposition failed for {team.team_name}: residual {residual}"
            )

    def test_practice_round_does_not_charge_income_or_interest(self):
        from src.game.manager import GameConfig, GameManager

        gm = GameManager(GameConfig(seed=20240331))
        gm.add_team("A", "A")
        gm.start_game()
        assert gm.current_round == -1

        gm.lock_round()
        gm.resolve_round()

        team = gm.teams["A"]
        assert team.cumulative_income == 0.0
        assert team.cumulative_interest == 0.0
        assert team.nav == pytest.approx(100.0)


class TestLeverageIsNotNeutral:
    def test_nav_decomposition_tracks_interest(self):
        """Leverage must show up in the numbers, or it is not a decision."""
        adj = Adjudicator()
        unlevered = make_team(100.0)
        unlevered.properties["P1"] = make_holding(debt_amount=0.0)
        levered = make_team(100.0)
        levered.properties["P1"] = make_holding(debt_amount=60.0, debt_rate=0.065)
        levered.debt = 60.0

        adj.collect_property_income(unlevered)
        adj.accrue_debt_interest(unlevered)
        adj.collect_property_income(levered)
        adj.accrue_debt_interest(levered)

        # Same asset, same income, but the levered book carries a real cash cost.
        assert levered.cumulative_income == unlevered.cumulative_income
        assert levered.cash < unlevered.cash


class TestRealizedYearOutcome:
    def test_reproducible_for_same_seed(self):
        a = realized_year_outcome("OC-INDU-01", "Industrial", 1.0, 0.055, 0.055, 7, 0)
        b = realized_year_outcome("OC-INDU-01", "Industrial", 1.0, 0.055, 0.055, 7, 0)
        assert a["value"] == b["value"]
        assert a["noi_growth"] == b["noi_growth"]

    def test_value_is_next_noi_over_cap_rate(self):
        o = realized_year_outcome("OC-INDU-01", "Industrial", 1.0, 0.055, 0.055, 7, 0)
        assert o["value"] == pytest.approx(o["next_noi"] / o["cap_rate"])
        assert o["next_noi"] == pytest.approx(1.0 * (1 + o["noi_growth"]))

    def test_different_properties_get_different_years(self):
        a = realized_year_outcome("OC-INDU-01", "Industrial", 1.0, 0.055, 0.055, 7, 0)
        b = realized_year_outcome("OC-INDU-02", "Industrial", 1.0, 0.055, 0.055, 7, 0)
        assert a["noi_growth"] != b["noi_growth"]
