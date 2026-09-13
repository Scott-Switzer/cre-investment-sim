"""
Tests for the student model output contract and the rules it feeds.

Two concerns:

1. ``src.game.submission`` must reject malformed submissions and accept valid
   ones, and it must never leak prediction accuracy back to the player.
2. The adjudicator's round feedback must describe exactly what it applied, and
   the two leaderboards / override records must be computable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.game.adjudicator import Bid, ModelPrediction, RoundState, realized_year_outcome
from src.game.manager import (
    CLASSROOM_TIMINGS,
    GameConfig,
    GameManager,
    game_config_for_timing,
)
from src.game.submission import (
    REQUIRED_COLUMNS,
    load_submission,
    to_model_predictions,
    validate_game_submission,
)


def valid_frame(property_ids: list[str], team_id: str = "Team A") -> pd.DataFrame:
    rows = []
    for i, pid in enumerate(property_ids):
        rows.append(
            {
                "team_id": team_id,
                "property_id": pid,
                "model_name": "baseline",
                "predicted_fair_value": 20.0 + i,
                "predicted_noi_growth": 0.03,
                "probability_of_downside": 0.20,
                "max_bid": 18.0 + i,
                "target_ltv": 0.60,
                "confidence": 0.7,
            }
        )
    return pd.DataFrame(rows)


class TestSubmissionValidation:
    def test_valid_submission_accepted(self):
        ids = ["P1", "P2", "P3"]
        result = validate_game_submission(valid_frame(ids), ids)
        assert result.ok, result.errors
        assert result.properties_covered == 3

    def test_missing_required_column_rejected(self):
        df = valid_frame(["P1"]).drop(columns=["max_bid"])
        result = validate_game_submission(df, ["P1"])
        assert not result.ok
        assert any("max_bid" in e for e in result.errors)

    def test_unknown_property_id_rejected(self):
        result = validate_game_submission(valid_frame(["P1", "NOPE"]), ["P1"])
        assert not result.ok
        assert result.unknown_property_ids == ["NOPE"]
        assert any("unknown property_id" in e for e in result.errors)

    def test_duplicate_team_property_rejected(self):
        df = pd.concat([valid_frame(["P1"]), valid_frame(["P1"])], ignore_index=True)
        result = validate_game_submission(df, ["P1"])
        assert not result.ok
        assert any("Duplicate" in e for e in result.errors)

    def test_same_property_for_different_teams_is_allowed(self):
        df = pd.concat(
            [valid_frame(["P1"], "Team A"), valid_frame(["P1"], "Team B")],
            ignore_index=True,
        )
        result = validate_game_submission(df, ["P1"])
        assert result.ok, result.errors
        assert sorted(result.teams) == ["Team A", "Team B"]

    def test_probability_out_of_range_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "probability_of_downside"] = 1.5
        result = validate_game_submission(df, ["P1"])
        assert not result.ok
        assert any("probability_of_downside" in e for e in result.errors)

    def test_negative_probability_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "probability_of_downside"] = -0.1
        assert not validate_game_submission(df, ["P1"]).ok

    def test_ltv_above_cap_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "target_ltv"] = 0.99
        assert not validate_game_submission(df, ["P1"]).ok

    def test_zero_ltv_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "target_ltv"] = 0.0
        assert not validate_game_submission(df, ["P1"]).ok

    def test_non_positive_fair_value_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "predicted_fair_value"] = 0.0
        assert not validate_game_submission(df, ["P1"]).ok

    def test_non_positive_max_bid_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "max_bid"] = 0.0
        assert not validate_game_submission(df, ["P1"]).ok

    def test_extreme_noi_growth_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "predicted_noi_growth"] = 3.0
        assert not validate_game_submission(df, ["P1"]).ok

    def test_non_numeric_column_rejected(self):
        df = valid_frame(["P1"])
        df["predicted_fair_value"] = df["predicted_fair_value"].astype(object)
        df.loc[0, "predicted_fair_value"] = "lots"
        assert not validate_game_submission(df, ["P1"]).ok

    def test_nulls_rejected(self):
        df = valid_frame(["P1"])
        df.loc[0, "max_bid"] = np.nan
        assert not validate_game_submission(df, ["P1"]).ok

    def test_bidding_above_own_fair_value_warns_but_passes(self):
        df = valid_frame(["P1"])
        df.loc[0, "max_bid"] = df.loc[0, "predicted_fair_value"] * 1.2
        result = validate_game_submission(df, ["P1"])
        assert result.ok
        assert any("above your own predicted_fair_value" in w for w in result.warnings)

    def test_validation_never_reports_accuracy(self):
        """The validator must not hint at whether predictions are good."""
        result = validate_game_submission(valid_frame(["P1"]), ["P1"])
        text = (result.summary() + " ".join(result.warnings)).lower()
        for forbidden in ["accuracy", "error", "mae", "correct", "wrong"]:
            assert forbidden not in text

    def test_stats_are_structural_only(self):
        result = validate_game_submission(valid_frame(["P1", "P2"]), ["P1", "P2"])
        assert set(result.stats) <= {
            "rows", "teams", "avg_predicted_fair_value", "avg_max_bid",
            "avg_target_ltv", "avg_probability_of_downside", "avg_noi_growth",
        }

    def test_real_packet_template_validates(self):
        template_path = REPO_ROOT / "student_packet" / "prediction_submission_template.csv"
        candidates_path = REPO_ROOT / "student_packet" / "game_candidates.csv"
        if not template_path.exists() or not candidates_path.exists():
            pytest.skip("student packet not built")
        template = pd.read_csv(template_path)
        candidates = pd.read_csv(candidates_path)
        # Fill the template with plausible values; the shipped one has zeros.
        template["predicted_fair_value"] = candidates["asking_price"].to_numpy()
        template["predicted_noi_growth"] = 0.03
        template["probability_of_downside"] = 0.2
        template["max_bid"] = candidates["asking_price"].to_numpy() * 0.95
        template["target_ltv"] = 0.6
        template["team_id"] = "Team A"
        template["model_name"] = "Team A model"
        result = validate_game_submission(template, candidates["property_id"])
        assert result.ok, result.errors


class TestSubmissionConversion:
    def test_converts_to_model_predictions(self):
        preds = to_model_predictions(valid_frame(["P1", "P2"]), team_id="Team A")
        assert set(preds) == {"P1", "P2"}
        assert isinstance(preds["P1"], ModelPrediction)
        assert preds["P1"].predicted_fair_value == pytest.approx(20.0)

    def test_privacy_filters_to_one_team(self):
        df = pd.concat(
            [valid_frame(["P1"], "Team A"), valid_frame(["P1"], "Team B")],
            ignore_index=True,
        )
        preds = to_model_predictions(df, team_id="Team B")
        assert preds["P1"].predicted_fair_value == pytest.approx(20.0)
        # Team A used the same values here, so prove filtering by row count instead.
        only_a = to_model_predictions(df, team_id="Team A")
        assert len(only_a) == 1

    def test_other_team_ids_are_excluded(self):
        df = pd.concat(
            [
                valid_frame(["P1"], "Team A"),
                valid_frame(["P2"], "Team B"),
            ],
            ignore_index=True,
        )
        preds = to_model_predictions(df, team_id="Team A")
        assert set(preds) == {"P1"}


class TestRoundFeedbackConsistency:
    """What a team is told happened must be what the engine actually applied."""

    def test_holding_equals_reported_outcome(self):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=2))
        gm.add_team("A", "A")
        gm.start_game()
        for pid, prop in gm.current_properties.items():
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.60, 0, "t"))
        gm.lock_round()
        result = gm.resolve_round()

        for pid, holding in gm.teams["A"].properties.items():
            outcome = result.property_outcomes[pid]
            assert holding.current_noi == pytest.approx(outcome.exit_noi)
            assert holding.current_value == pytest.approx(outcome.exit_value)

    def test_multi_round_portfolio_persists_and_compounds(self):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=3))
        gm.add_team("A", "A")
        gm.start_game()
        bought = []
        for pid, prop in gm.current_properties.items():
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.60, 0, "t"))
            bought.append(pid)
        gm.lock_round()
        gm.resolve_round()
        noi_after_r1 = {p: gm.teams["A"].properties[p].current_noi for p in bought}

        gm.advance_round()
        gm.lock_round()
        gm.resolve_round()

        for pid in bought:
            assert pid in gm.teams["A"].properties, "round 1 asset vanished"
            assert gm.teams["A"].properties[pid].current_noi != noi_after_r1[pid], (
                "holding did not evolve in the second year"
            )

    def test_practice_round_is_not_scored(self):
        gm = GameManager(GameConfig(practice_round=True))
        gm.add_team("A", "A")
        gm.start_game()
        assert gm.current_round == -1
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, -1, "t"))
        gm.lock_round()
        result = gm.resolve_round()

        assert gm.teams["A"].cash == pytest.approx(100.0)
        assert gm.teams["A"].nav == pytest.approx(100.0)
        assert len(gm.teams["A"].properties) == 0
        for auction in result.auction_results.values():
            assert not auction.sold

    def test_realized_year_outcome_is_deterministic(self):
        a = realized_year_outcome("P1", "Industrial", 1.0, 0.05, 0.055, 42, 0)
        b = realized_year_outcome("P1", "Industrial", 1.0, 0.05, 0.055, 42, 0)
        assert a == b

    def test_tight_vacancy_grows_noi_faster_on_average(self):
        tight = [
            realized_year_outcome(f"P{i}", "Industrial", 1.0, 0.03, 0.055, 7, 0)["noi_growth"]
            for i in range(200)
        ]
        loose = [
            realized_year_outcome(f"P{i}", "Industrial", 1.0, 0.15, 0.055, 7, 0)["noi_growth"]
            for i in range(200)
        ]
        assert np.mean(tight) > np.mean(loose)


class TestSealedBidRules:
    def _game_with_teams(self, teams=("A", "B")):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=1))
        for t in teams:
            gm.add_team(t, t)
        gm.start_game()
        return gm

    def test_highest_valid_bid_wins_and_pays_its_price(self):
        gm = self._game_with_teams()
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        reserve = prop.reserve_price
        high = min(prop.asking_price * 0.99, reserve * 1.5)
        gm.submit_bid(Bid("A", pid, high * 0.9, 0.5, 0, "t"))
        gm.submit_bid(Bid("B", pid, high, 0.5, 0, "t"))
        gm.lock_round()
        result = gm.resolve_round()

        auction = result.auction_results[pid]
        if auction.sold:
            assert auction.winning_team_id == "B"
            assert auction.winning_bid == pytest.approx(high)

    def test_bid_below_reserve_does_not_sell(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        gm.submit_bid(Bid("A", pid, prop.reserve_price * 0.5, 0.5, 0, "t"))
        gm.lock_round()
        result = gm.resolve_round()
        assert not result.auction_results[pid].sold

    def test_insufficient_equity_bid_rejected(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        # Equity required far exceeds the $100M starting capital.
        with pytest.raises(ValueError):
            gm.submit_bid(Bid("A", pid, 1_000_000.0, 0.10, 0, "t"))

    def test_ltv_above_property_max_rejected(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        if prop.max_ltv >= 0.99:
            pytest.skip("property allows very high LTV")
        with pytest.raises(ValueError):
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.5, 0.99, 0, "t"))

    def test_zero_bid_rejected(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        with pytest.raises(ValueError):
            gm.submit_bid(Bid("A", pid, 0.0, 0.5, 0, "t"))

    def test_duplicate_bid_for_same_property_rejected(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        gm.submit_bid(Bid("A", pid, prop.asking_price * 0.9, 0.5, 0, "t"))
        with pytest.raises(RuntimeError):
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.95, 0.5, 0, "t"))

    def test_late_submission_after_lock_rejected(self):
        gm = self._game_with_teams(("A",))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        gm.lock_round()
        with pytest.raises(RuntimeError, match="not open"):
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.9, 0.5, 0, "t"))

    def test_cannot_resolve_before_lock(self):
        gm = self._game_with_teams(("A",))
        with pytest.raises(RuntimeError, match="locked"):
            gm.resolve_round()

    def test_lower_ltv_wins_an_exact_tie(self):
        gm = self._game_with_teams(("A", "B"))
        pid = list(gm.current_properties)[0]
        prop = gm.current_properties[pid]
        price = max(prop.reserve_price * 1.2, prop.asking_price * 0.9)
        gm.submit_bid(Bid("A", pid, price, 0.70, 0, "t"))
        gm.submit_bid(Bid("B", pid, price, 0.40, 0, "t"))
        gm.lock_round()
        auction = gm.resolve_round().auction_results[pid]
        if auction.sold:
            assert auction.winning_team_id == "B", "higher-equity bid should win the tie"


class TestOverrideTracking:
    def test_override_recorded_when_bid_exceeds_model(self):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=1))
        pid = list(gm.all_properties)[0]
        prop = gm.all_properties[pid]
        gm.add_team(
            "A", "A",
            {pid: ModelPrediction(pid, prop.asking_price * 0.8, 0.02, 0.2,
                                  prop.asking_price * 0.8, 0.5, "m")},
        )
        gm.start_game()
        # Ensure the property is in this round; otherwise re-target.
        if pid not in gm.current_properties:
            pid = list(gm.current_properties)[0]
            prop = gm.current_properties[pid]
            gm.teams["A"].model_predictions = {
                pid: ModelPrediction(pid, prop.asking_price * 0.8, 0.02, 0.2,
                                     prop.asking_price * 0.8, 0.5, "m")
            }
        bid_price = max(prop.reserve_price * 1.2, prop.asking_price * 0.95)
        gm.submit_bid(Bid("A", pid, bid_price, 0.6, 0, "t"))
        gm.lock_round()
        result = gm.resolve_round()

        if result.auction_results[pid].sold:
            history = gm.teams["A"].override_history
            assert history, "override was not recorded"
            record = history[-1]
            assert record.bid_override == pytest.approx(
                bid_price - prop.asking_price * 0.8
            )

    def test_override_is_recorded_not_punished(self):
        """Bidding above your model must not be blocked, only logged."""
        gm = GameManager(GameConfig(practice_round=False, total_rounds=1))
        pid = list(gm.all_properties)[0]
        prop = gm.all_properties[pid]
        gm.add_team(
            "A", "A",
            {pid: ModelPrediction(pid, prop.asking_price * 0.5, 0.02, 0.2,
                                  prop.asking_price * 0.5, 0.5, "m")},
        )
        gm.start_game()
        target = pid if pid in gm.current_properties else list(gm.current_properties)[0]
        target_prop = gm.current_properties[target]
        if target not in gm.teams["A"].model_predictions:
            gm.teams["A"].model_predictions[target] = ModelPrediction(
                target, target_prop.asking_price * 0.5, 0.02, 0.2,
                target_prop.asking_price * 0.5, 0.5, "m",
            )
        # A large override should be accepted by validation.
        assert gm.submit_bid(
            Bid("A", target, target_prop.asking_price * 0.9, 0.6, 0, "t")
        )


class TestLeaderboards:
    def test_game_leaderboard_ranks_by_nav(self):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=1))
        gm.add_team("A", "A")
        gm.add_team("B", "B")
        board = gm.get_leaderboard()
        navs = [e["nav"] for e in board]
        assert navs == sorted(navs, reverse=True)

    def test_nav_identity_holds(self):
        gm = GameManager(GameConfig(practice_round=False, total_rounds=1))
        gm.add_team("A", "A")
        gm.start_game()
        for pid, prop in gm.current_properties.items():
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.99, 0.6, 0, "t"))
        gm.lock_round()
        gm.resolve_round()
        team = gm.teams["A"]
        expected = team.cash + sum(h.current_value for h in team.properties.values()) - team.debt
        assert team.nav == pytest.approx(expected, abs=0.01)


class TestClassroomTimingPresets:
    def test_both_presets_exist(self):
        assert set(CLASSROOM_TIMINGS) == {"QUICK CLASS", "EXTENDED CLASS"}

    def test_quick_class_is_four_rounds(self):
        assert CLASSROOM_TIMINGS["QUICK CLASS"].total_rounds == 4

    def test_extended_class_is_longer(self):
        ext = CLASSROOM_TIMINGS["EXTENDED CLASS"]
        quick = CLASSROOM_TIMINGS["QUICK CLASS"]
        assert ext.total_rounds > quick.total_rounds
        assert ext.total_minutes > quick.total_minutes

    def test_quick_class_fits_a_class_period(self):
        assert CLASSROOM_TIMINGS["QUICK CLASS"].total_minutes <= 90

    def test_config_for_timing_sets_round_count(self):
        assert game_config_for_timing("QUICK CLASS").total_rounds == 4
        assert game_config_for_timing("EXTENDED CLASS").total_rounds == 6

    def test_extended_preset_can_play_all_rounds(self):
        cfg = game_config_for_timing("EXTENDED CLASS")
        gm = GameManager(cfg)
        gm.add_team("A", "A")
        gm.start_game()

        # The practice round opens first and only shows one property.
        assert gm.current_round == -1
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

        for round_index in range(cfg.total_rounds):
            assert gm.round_state == RoundState.OPEN
            assert gm.current_round == round_index
            assert len(gm.current_properties) == 4
            gm.lock_round()
            gm.resolve_round()
            gm.advance_round()
        assert gm.game_complete

    def test_unknown_preset_raises(self):
        with pytest.raises(KeyError):
            game_config_for_timing("NOPE")
