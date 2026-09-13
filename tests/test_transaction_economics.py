"""
Tests for the transaction economics: deal costs, capital reserves, and the
balance-gate conditions they exist to protect.

These rules are what stop "buy everything at any price" from beating analysis, so
they are asserted directly rather than left to the balance harness alone.
"""

from __future__ import annotations

import pytest

from src.game.adjudicator import (
    ACQUISITION_COST_RATE,
    CAPITAL_RESERVE_RATE,
    Adjudicator,
    Bid,
    BidStatus,
    RoundState,
    TeamState,
    equity_required_for,
)
from src.game.manager import GameConfig, GameManager


class TestEquityRequired:
    def test_includes_closing_costs(self):
        # 60% LTV on $100M is $40M of equity, plus 2% deal costs = $42M.
        assert equity_required_for(100.0, 0.6) == pytest.approx(42.0)

    def test_is_monotonic_in_leverage(self):
        assert equity_required_for(100.0, 0.7) < equity_required_for(100.0, 0.5)

    def test_zero_for_non_positive_price(self):
        assert equity_required_for(0.0, 0.6) == 0.0

    def test_matches_the_rate_constant(self):
        assert equity_required_for(50.0, 0.5) == pytest.approx(
            50.0 * 0.5 + 50.0 * ACQUISITION_COST_RATE
        )


class TestBidValidationIncludesDealCosts:
    def _market(self, manager: GameManager):
        pid = next(iter(manager.current_properties))
        return pid, manager.current_properties[pid]

    def test_bid_is_rejected_when_cash_covers_equity_but_not_costs(self):
        """A bid the fund cannot actually close must be rejected up front."""
        gm = GameManager(GameConfig(seed=20240331, practice_round=False))
        gm.start_game()
        pid, prop = self._market(gm)
        team = gm.teams.get("A") or None
        gm.add_team("A", "A")
        team = gm.teams["A"]

        price = prop.asking_price
        ltv = 0.6
        equity = price * (1 - ltv)
        # Cash covers equity exactly, but not the 2% of closing costs on top.
        team.cash = equity
        status, _reason = gm.adjudicator.validate_bid(
            Bid("A", pid, price, ltv, 0, "t"), team, prop, RoundState.OPEN
        )
        assert status == BidStatus.INSUFFICIENT_EQUITY

        # With the closing costs funded, the same bid is valid.
        team.cash = equity + price * ACQUISITION_COST_RATE
        status, _reason = gm.adjudicator.validate_bid(
            Bid("A", pid, price, ltv, 0, "t"), team, prop, RoundState.OPEN
        )
        assert status == BidStatus.VALID


class TestAcquisitionCostsAreCharged:
    def _played_round(self, bid_price: float, ltv: float = 0.6):
        gm = GameManager(GameConfig(seed=20240331, practice_round=False, total_rounds=1))
        gm.add_team("A", "A")
        gm.start_game()
        pid, prop = next(iter(gm.current_properties.items()))
        gm.current_properties = {pid: prop}
        gm.submit_bid(Bid("A", pid, bid_price, ltv, 0, "t"))
        gm.lock_round()
        gm.resolve_round()
        return gm, pid

    def test_winning_costs_two_percent_of_the_price(self):
        gm = GameManager(GameConfig(seed=20240331, practice_round=False, total_rounds=1))
        gm.add_team("A", "A")
        gm.start_game()
        pid, prop = next(iter(gm.current_properties.items()))
        gm.current_properties = {pid: prop}
        price = prop.reserve_price * 1.02
        gm.submit_bid(Bid("A", pid, price, 0.6, 0, "t"))
        gm.lock_round()
        gm.resolve_round()

        team = gm.teams["A"]
        assert len(team.properties) == 1
        assert team.cumulative_acquisition_costs == pytest.approx(
            price * ACQUISITION_COST_RATE
        )
        assert team.cumulative_purchase_price == pytest.approx(price)

    def test_costs_are_not_financed(self):
        """Deal costs reduce cash; they must not appear in debt."""
        gm, _pid = self._played_round(30.0, ltv=0.5)
        team = gm.teams["A"]
        price = team.cumulative_purchase_price
        assert team.debt == pytest.approx(price * 0.5)
        # Cash is explained exactly by the fund's own ledgers: equity and deal
        # costs out, income in, reserves and interest out.
        assert team.cash == pytest.approx(
            100.0
            - price * 0.5
            - team.cumulative_acquisition_costs
            + team.cumulative_income
            - team.cumulative_reserves
            - team.cumulative_interest
        )

    def test_deal_costs_reduce_nav_versus_a_costless_world(self):
        gm, _ = self._played_round(30.0, ltv=0.5)
        team = gm.teams["A"]
        assert team.cumulative_acquisition_costs > 0
        # A purchase at the reserve still costs real money to execute, so a fund
        # that acquires is not automatically ahead of one that does nothing.
        assert team.nav < 100.0 + sum(
            h.current_value - h.purchase_price for h in team.properties.values()
        )


class TestCapitalReserves:
    def _reserve_team(self, ptype: str, value: float = 100.0) -> TeamState:
        from src.game.adjudicator import PropertyHolding

        team = TeamState(team_id="A", team_name="A", cash=100.0, equity_capital=100.0)
        team.properties["P"] = PropertyHolding(
            property_id="P",
            purchase_price=value,
            purchase_round=0,
            equity_invested=value * 0.4,
            debt_amount=value * 0.6,
            debt_rate=0.06,
            amortization_years=25,
            current_noi=6.0,
            current_value=value,
            property_type=ptype,
            submarket="Irvine",
        )
        return team

    def test_reserve_is_value_times_the_type_rate(self):
        adj = Adjudicator()
        for ptype, rate in CAPITAL_RESERVE_RATE.items():
            team = self._reserve_team(ptype, 100.0)
            adj.charge_capital_reserves(team)
            assert team.cumulative_reserves == pytest.approx(100.0 * rate), ptype

    def test_office_pays_more_than_industrial(self):
        adj = Adjudicator()
        office = self._reserve_team("Office", 100.0)
        industrial = self._reserve_team("Industrial", 100.0)
        adj.charge_capital_reserves(office)
        adj.charge_capital_reserves(industrial)
        assert office.cumulative_reserves > industrial.cumulative_reserves

    def test_reserves_scale_with_the_asset_not_the_loan(self):
        """Leverage multiplies the reserve, which is why it is charged on value."""
        adj = Adjudicator()
        levered = self._reserve_team("Office", 100.0)
        levered.debt = 60.0
        unlevered = self._reserve_team("Office", 100.0)
        unlevered.debt = 0.0
        adj.charge_capital_reserves(levered)
        adj.charge_capital_reserves(unlevered)
        assert levered.cumulative_reserves == unlevered.cumulative_reserves

    def test_no_properties_means_no_reserve(self):
        adj = Adjudicator()
        team = TeamState(team_id="A", team_name="A", cash=100.0, equity_capital=100.0)
        adj.charge_capital_reserves(team)
        assert team.cumulative_reserves == 0.0
        assert team.cash == pytest.approx(100.0)


class TestIdentityStillReconciles:
    def test_full_game_channels_sum_to_nav_change(self):
        from src.game.analytics import fund_channels

        gm = GameManager(GameConfig(seed=20240331, practice_round=False, total_rounds=2))
        gm.add_team("A", "A")
        gm.add_team("B", "B")
        gm.start_game()

        for _round in range(2):
            for pid, prop in gm.current_properties.items():
                if len(gm.teams["A"].properties) + len(gm.teams["B"].properties) % 2 == 0:
                    gm.submit_bid(
                        Bid("A", pid, prop.reserve_price * 1.02, 0.55, 0, "t")
                    )
                    gm.submit_bid(
                        Bid("B", pid, prop.reserve_price * 1.01, 0.60, 0, "t")
                    )
            gm.lock_round()
            gm.resolve_round()
            gm.advance_round()

        for team_id in ("A", "B"):
            c = fund_channels(gm, team_id)
            decomposed = (
                c.value_channel
                + c.noi_income
                - c.interest_paid
                - c.acquisition_costs
                - c.reserves
            )
            assert decomposed == pytest.approx(c.nav - 100.0, abs=1e-6), team_id

    def test_acquisition_costs_are_exposed_to_the_debrief(self):
        from src.game.analytics import fund_channels

        gm = GameManager(GameConfig(seed=20240331, practice_round=False, total_rounds=1))
        gm.add_team("A", "A")
        gm.start_game()
        pid, prop = next(iter(gm.current_properties.items()))
        gm.current_properties = {pid: prop}
        gm.submit_bid(Bid("A", pid, prop.reserve_price * 1.05, 0.6, 0, "t"))
        gm.lock_round()
        gm.resolve_round()

        c = fund_channels(gm, "A")
        assert c.acquisition_costs > 0
        assert c.reserves > 0  # held for one year, so reserves are charged

    def test_practice_charges_no_reserves(self):
        gm = GameManager(GameConfig(seed=20240331, practice_round=True))
        gm.add_team("A", "A")
        gm.start_game()
        pid, prop = next(iter(gm.current_properties.items()))
        gm.submit_bid(Bid("A", pid, prop.reserve_price * 1.02, 0.6, -1, "t"))
        gm.lock_round()
        gm.resolve_round()
        assert gm.teams["A"].cumulative_reserves == 0.0
        assert gm.teams["A"].cumulative_acquisition_costs == 0.0


class TestDeploymentIsNotADominanceStrategy:
    """
    The balance gate, as a regression test.

    The point is not that disciplined bidding always wins; it is that a property
    bought near the ask and fully levered does not beat the field on its own. If
    a future change re-introduces a free levered lunch, this fails.
    """

    def _play(self, seed: int, price_multiple: float, ltv_fraction: float) -> float:
        """Buy everything in the pool at ``price_multiple`` x ask, up to the
        property's own leverage limit scaled by ``ltv_fraction``."""
        gm = GameManager(GameConfig(seed=seed, practice_round=False, total_rounds=2,
                                    properties_per_round=4))
        gm.add_team("BULL", "Bull")
        gm.add_team("PASS", "Pass")
        gm.start_game()
        for _round in range(2):
            for pid, prop in gm.current_properties.items():
                price = prop.asking_price * price_multiple
                ltv = prop.max_ltv * ltv_fraction
                if equity_required_for(price, ltv) <= gm.teams["BULL"].cash:
                    gm.submit_bid(Bid("BULL", pid, price, ltv, gm.current_round, "t"))
            gm.lock_round()
            gm.resolve_round()
            gm.advance_round()
        return gm.teams["BULL"].nav

    def test_paying_a_premium_over_the_ask_is_punished_on_average(self):
        seeds = range(20240331, 20240331 + 12)
        premium = [self._play(s, 1.05, 1.0) for s in seeds]
        at_ask = [self._play(s, 1.00, 1.0) for s in seeds]
        assert sum(premium) / len(premium) < sum(at_ask) / len(at_ask)

    def test_max_leverage_at_the_ask_does_not_guarantee_beating_a_passive_fund(self):
        """Even the most aggressive deployment produces losses sometimes."""
        seeds = range(20240331, 20240331 + 12)
        navs = [self._play(s, 1.00, 1.0) for s in seeds]
        assert any(n < 100.0 for n in navs), "deployment never lost money — check"
        assert not all(n > 100.0 for n in navs)
