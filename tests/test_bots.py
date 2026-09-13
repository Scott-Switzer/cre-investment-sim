"""
Demo bot policy tests.

Bots are not privileged. Every bid they produce must satisfy exactly the same
constraints the adjudicator enforces on a human team — most importantly the
asset's own maximum LTV, which earlier caused every aggressive bid to be
silently rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.game.adjudicator import Bid, ModelPrediction
from src.game.bots import (
    LTV_CAP_RISK,
    LTV_CAP_VALUE,
    bot_strategy,
    is_bot,
    submit_bot_bids,
)
from src.game.manager import GameConfig, GameManager


def make_pred(
    fair: float = 100.0,
    max_bid: float = 98.0,
    growth: float = 0.03,
    downside: float = 0.2,
    ltv: float = 0.60,
) -> ModelPrediction:
    return ModelPrediction(
        property_id="P1",
        predicted_fair_value=fair,
        predicted_noi_growth=growth,
        probability_of_downside=downside,
        max_bid=max_bid,
        target_ltv=ltv,
        model_name="test",
    )


class TestArchetypeBehaviour:
    def test_all_archetypes_are_recognised(self):
        pred = make_pred()
        for team in ["Value Fund", "Growth Fund", "Risk Fund", "Noisy Model"]:
            plan = bot_strategy(team, pred, 95.0, 0.70)
            assert "should_bid" in plan and "bid_price" in plan and "ltv" in plan

    def test_value_fund_bids_below_its_own_ceiling(self):
        plan = bot_strategy("Value Fund", make_pred(max_bid=98.0), 95.0, 0.70)
        assert plan["should_bid"]
        assert plan["bid_price"] <= 98.0

    def test_growth_fund_bids_higher_than_value(self):
        pred = make_pred(max_bid=100.0)
        value = bot_strategy("Value Fund", pred, 95.0, 0.70)
        growth = bot_strategy("Growth Fund", pred, 95.0, 0.70)
        assert growth["bid_price"] >= value["bid_price"]

    def test_risk_fund_uses_lower_leverage(self):
        pred = make_pred(ltv=0.65)
        risk = bot_strategy("Risk Fund", pred, 90.0, 0.70)
        value = bot_strategy("Value Fund", pred, 90.0, 0.70)
        assert risk["ltv"] <= LTV_CAP_RISK
        assert risk["ltv"] < value["ltv"]

    def test_risk_fund_passes_on_high_downside(self):
        pred = make_pred(downside=0.80)
        plan = bot_strategy("Risk Fund", pred, 90.0, 0.70)
        assert not plan["should_bid"]

    def test_growth_fund_passes_when_model_says_overpriced(self):
        # Fair value far below the ask: no edge, so no bid.
        pred = make_pred(fair=80.0, max_bid=78.0)
        assert not bot_strategy("Growth Fund", pred, 100.0, 0.70)["should_bid"]

    def test_no_edge_means_no_bid(self):
        pred = make_pred(fair=100.0, max_bid=99.0)
        assert not bot_strategy("Value Fund", pred, 120.0, 0.70)["should_bid"]


class TestRuleCompliance:
    """Bots must respect the same constraints the adjudicator applies."""

    @pytest.mark.parametrize("max_ltv", [0.55, 0.60, 0.65, 0.70, 0.75])
    @pytest.mark.parametrize("team", ["Value Fund", "Growth Fund", "Risk Fund", "Noisy Model"])
    def test_ltv_never_exceeds_property_max(self, team, max_ltv):
        plan = bot_strategy(team, make_pred(ltv=0.70), 95.0, max_ltv)
        if plan["should_bid"]:
            assert plan["ltv"] <= max_ltv + 1e-9, (
                f"{team} produced LTV {plan['ltv']} above asset cap {max_ltv}"
            )

    @pytest.mark.parametrize("team", ["Value Fund", "Growth Fund", "Risk Fund", "Noisy Model"])
    def test_ltv_is_always_positive(self, team):
        plan = bot_strategy(team, make_pred(ltv=0.10), 95.0, 0.70)
        if plan["should_bid"]:
            assert plan["ltv"] > 0

    def test_mock_like_property_does_not_crash(self):
        """A stub with a non-numeric max_ltv must not leak into the LTV."""

        class StubProp:
            asking_price = 95.0
            max_ltv = object()

        plan = bot_strategy("Growth Fund", make_pred(), StubProp.asking_price,
                            StubProp.max_ltv)
        assert plan["should_bid"]
        assert isinstance(plan["ltv"], float)
        assert 0 < plan["ltv"] <= 0.75

    def test_unknown_archetype_passes_without_edge(self):
        pred = make_pred(fair=90.0)
        assert not bot_strategy("Mystery Fund", pred, 100.0, 0.70)["should_bid"]


class TestEngineIntegration:
    def _game(self) -> GameManager:
        gm = GameManager(GameConfig(practice_round=False, total_rounds=2))
        for team in ["Human Fund", "Value Fund", "Growth Fund", "Risk Fund"]:
            gm.add_team(team, team)
        gm.start_game()
        return gm

    def _seed_predictions(self, gm: GameManager) -> None:
        for team_id, team in gm.teams.items():
            preds = {}
            for prop_id, prop in gm.current_properties.items():
                # Every bot's model thinks the asset is worth its asking price.
                preds[prop_id] = ModelPrediction(
                    property_id=prop_id,
                    predicted_fair_value=prop.asking_price * 1.08,
                    predicted_noi_growth=0.03,
                    probability_of_downside=0.15,
                    max_bid=prop.asking_price * 1.05,
                    target_ltv=0.62,
                    model_name="test",
                )
            team.model_predictions = preds

    def test_human_team_is_never_automated(self):
        assert not is_bot("Human Fund", "Human Fund")
        assert is_bot("Value Fund", "Human Fund")

    def test_submit_bot_bids_excludes_human(self):
        gm = self._game()
        self._seed_predictions(gm)
        submit_bot_bids(gm, "Human Fund")
        assert gm.submitted_bids, "bots submitted nothing"
        assert all(b.team_id != "Human Fund" for b in gm.submitted_bids)

    def test_every_submitted_bot_bid_is_accepted_by_validation(self):
        """A bot bid reaching the book must already be a legal bid."""
        gm = self._game()
        self._seed_predictions(gm)
        submit_bot_bids(gm, "Human Fund")
        for bid in gm.submitted_bids:
            prop = gm.current_properties[bid.property_id]
            assert bid.bid_price > 0
            assert 0 < bid.ltv <= prop.max_ltv + 1e-9
            equity = bid.bid_price * (1 - bid.ltv)
            assert equity <= gm.teams[bid.team_id].cash + 1e-9

    def test_bots_cannot_overspend(self):
        gm = self._game()
        for team_id, team in gm.teams.items():
            if team_id == "Human Fund":
                continue
            team.model_predictions = {
                pid: ModelPrediction(pid, prop.asking_price * 10, 0.03, 0.1,
                                     prop.asking_price * 10, 0.70, "test")
                for pid, prop in gm.current_properties.items()
            }
        submit_bot_bids(gm, "Human Fund")
        for bid in gm.submitted_bids:
            team = gm.teams[bid.team_id]
            assert bid.bid_price * (1 - bid.ltv) <= team.cash + 1e-9

    def test_bots_do_not_bid_without_predictions(self):
        gm = self._game()
        submit_bot_bids(gm, "Human Fund")
        assert gm.submitted_bids == []

    def test_at_least_two_archetypes_transact_in_a_demo_seed(self):
        """Regression: conservative bots used to never clear the reserve."""
        from scripts.verify_demo_flow import build_demo_game

        gm = build_demo_game()
        gm.start_game()
        # finish the practice round
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()
        submit_bot_bids(gm, "Buy&Hold Capital")
        bidders = {b.team_id for b in gm.submitted_bids}
        assert len(bidders) >= 2, f"only {bidders} bid in round 1"
