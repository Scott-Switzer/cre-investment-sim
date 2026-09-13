"""
Tests for the model / manager / luck debrief and the honesty guards around it.

The important claims being locked down:

* decision quality is judged **ex ante**, so overriding your own model is not an
  automatic bad mark;
* exceeding your own ceiling and paying above the asking price *is* flagged;
* every one of the named teaching cases is reachable by the classifier;
* a model built against a different property pool is refused rather than
  silently scored as if it were merely inaccurate.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import pytest

from src.game.adjudicator import Bid, ModelPrediction
from src.game.analytics import (
    AttemptAssessment,
    analytics_leaderboard,
    assess_attempts,
    debrief_answers,
    fund_channels,
    override_contribution,
)
from src.game.manager import GameConfig, GameManager
from src.game.submission import (
    check_candidates_match_pool,
    to_model_predictions,
    validate_game_submission,
)

PACKET = REPO_ROOT / "student_packet"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "student_submission_realistic.csv"


def attempt(**kw) -> AttemptAssessment:
    """A won, disciplined attempt by default; override any axis via kwargs."""
    base = dict(
        team_id="T", property_id="P1", round_number=0,
        model_label="GOOD_MODEL", decision_label="GOOD_DECISION",
        outcome_label="GOOD_OUTCOME", override_label="FOLLOWED", won=True,
    )
    base.update(kw)
    return AttemptAssessment(**base)


class TestCaseClassification:
    def test_followed_model_is_its_own_case(self):
        assert attempt().case_label == "MODEL GOOD + FOLLOWED MODEL"

    def test_good_model_overridden_up_and_overpaying_is_a_bad_override(self):
        a = attempt(override_label="OVERRODE_UP", decision_label="BAD_DECISION",
                    outcome_label="BAD_OUTCOME", bid_override=4.0, won=True)
        assert a.case_label == "MODEL GOOD + BAD OVERRIDE"

    def test_bad_model_with_a_justified_deviation_is_a_good_override(self):
        a = attempt(model_label="BAD_MODEL", override_label="OVERRODE_DOWN",
                    decision_label="GOOD_DECISION", bid_override=-3.0, won=True)
        assert a.case_label == "MODEL WRONG + GOOD OVERRIDE"

    def test_good_decision_with_a_bad_realized_year(self):
        a = attempt(outcome_label="BAD_OUTCOME", realized_return=-0.06)
        assert a.case_label == "GOOD DECISION + BAD REALIZED OUTCOME"

    def test_bad_decision_that_still_made_money_is_luck(self):
        a = attempt(decision_label="BAD_DECISION", override_label="OVERRODE_UP",
                    outcome_label="GOOD_OUTCOME", realized_return=0.04)
        assert a.case_label == "BAD DECISION + LUCKY REALIZED OUTCOME"

    def test_passing_leaves_no_realized_outcome_and_no_case(self):
        a = attempt(override_label="NO_BID", outcome_label="NO_POSITION", won=False)
        # A pass must never be reported as a realized outcome or a teaching case.
        assert a.outcome_label == "NO_POSITION"
        assert a.case_labels == []
        assert a.case_label is None

    def test_one_attempt_can_satisfy_several_cases(self):
        """An overpaid-but-profitable buy is both a bad override and luck."""
        a = attempt(decision_label="BAD_DECISION", override_label="OVERRODE_UP",
                    outcome_label="GOOD_OUTCOME", realized_return=0.04)
        assert "BAD DECISION + LUCKY REALIZED OUTCOME" in a.case_labels
        assert "MODEL GOOD + BAD OVERRIDE" in a.case_labels
        # The sharpest lesson leads.
        assert a.case_label == "BAD DECISION + LUCKY REALIZED OUTCOME"

    def test_teaching_note_never_punishes_an_override_by_definition(self):
        """Disagreeing with your model is allowed; the note must say so."""
        disciplined_override = attempt(
            override_label="OVERRODE_UP", decision_label="GOOD_DECISION",
            bid_override=1.0, won=True,
        )
        note = disciplined_override.teaching_note().lower()
        assert "recorded as a deliberate override" in note
        assert "depends on the model" in note


class TestDecisionQualityIsExAnte:
    def _game_with_one_bid(self, bid_factor: float):
        gm = GameManager(GameConfig(seed=20240331, total_rounds=4))
        gm.add_team("T", "T")
        gm.start_game()
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

        pid = next(iter(gm.current_properties))
        prop = gm.current_properties[pid]
        gm.teams["T"].model_predictions[pid] = ModelPrediction(
            property_id=pid, predicted_fair_value=prop.asking_price,
            predicted_noi_growth=0.02, probability_of_downside=0.2,
            max_bid=prop.asking_price * 0.95, target_ltv=0.6, model_name="m",
        )
        gm.submit_bid(Bid("T", pid, prop.asking_price * bid_factor, 0.6, 0, "t"))
        gm.lock_round()
        gm.resolve_round()
        return gm, pid

    def test_bidding_above_the_ask_is_a_bad_decision_ex_ante(self):
        gm, _ = self._game_with_one_bid(1.10)
        attempts = assess_attempts(gm)
        assert attempts, "expected an attempt for the bid"
        assert attempts[0].decision_label == "BAD_DECISION"

    def test_bidding_below_the_ask_is_a_good_decision_ex_ante(self):
        gm, _ = self._game_with_one_bid(0.95)
        attempts = assess_attempts(gm)
        assert attempts
        assert attempts[0].decision_label == "GOOD_DECISION"

    def test_override_direction_recorded(self):
        gm, _ = self._game_with_one_bid(1.10)
        a = assess_attempts(gm)[0]
        assert a.override_label == "OVERRODE_UP"
        assert a.bid_override is not None and a.bid_override > 0
        assert a.ltv_override is not None


class TestDebrief:
    def _played_game(self):
        gm = GameManager(GameConfig(seed=20240331, total_rounds=4))
        for name in ("A", "B"):
            gm.add_team(name, name)
        gm.start_game()
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()
        for _ in range(4):
            pid = next(iter(gm.current_properties))
            prop = gm.current_properties[pid]
            gm.teams["A"].model_predictions[pid] = ModelPrediction(
                property_id=pid, predicted_fair_value=prop.asking_price,
                predicted_noi_growth=0.02, probability_of_downside=0.2,
                max_bid=prop.asking_price * 0.95, target_ltv=0.6, model_name="m",
            )
            gm.submit_bid(Bid("A", pid, prop.asking_price * 0.94, 0.6, gm.current_round, "t"))
            gm.lock_round()
            gm.resolve_round()
            gm.advance_round()
        return gm

    def test_ten_questions_are_answered(self):
        d = debrief_answers(self._played_game())
        assert len(d.answers) == 10
        for a in d.answers:
            assert a.answer.strip()
            assert a.question.strip()

    def test_questions_are_numbered_one_to_ten(self):
        d = debrief_answers(self._played_game())
        assert [a.number for a in d.answers] == list(range(1, 11))

    def test_every_question_is_the_one_the_course_asks(self):
        d = debrief_answers(self._played_game())
        text = " ".join(a.question.lower() for a in d.answers)
        for topic in ("won the game", "best model", "same team", "overrode",
                      "help or hurt", "leverage", "lucky", "conclude"):
            assert topic in text, f"missing debrief topic: {topic}"

    def test_channels_reconcile_with_nav(self):
        gm = self._played_game()
        for c in debrief_answers(gm).channels:
            assert (
                c.value_channel + c.noi_income - c.interest_paid
                - c.acquisition_costs - c.reserves
            ) == pytest.approx(c.nav - gm.config.starting_equity, abs=1e-6)

    def test_override_summary_present(self):
        d = debrief_answers(self._played_game())
        assert "overridden_count" in d.override_summary
        assert "disciplined_count" in d.override_summary

    def test_analytics_board_is_independent_of_winning(self):
        gm = self._played_game()
        board = analytics_leaderboard(gm)
        assert len(board) == 2
        # Sorted by valuation error, NOT by NAV: the analytics board must not
        # simply restate the game leaderboard.
        scored = [t.valuation_mae for t in board if t.valuation_mae is not None]
        assert scored == sorted(scored)


class TestStudentFixture:
    def test_fixture_exists_and_is_valid(self):
        assert FIXTURE.exists(), "run scripts/build_realistic_student_submission.py"
        df = pd.read_csv(FIXTURE)
        candidates = pd.read_csv(PACKET / "game_candidates.csv")
        result = validate_game_submission(
            df, valid_property_ids=candidates["property_id"].astype(str).tolist()
        )
        assert result.ok, result.errors
        assert result.properties_covered == len(candidates)

    def test_fixture_policy_is_internally_consistent(self):
        df = pd.read_csv(FIXTURE)
        assert (df["max_bid"] <= df["predicted_fair_value"]).all()
        assert (df["target_ltv"] <= 0.95).all()
        assert df["property_id"].is_unique

    def test_fixture_converts_to_predictions_for_one_team_only(self):
        df = pd.read_csv(FIXTURE)
        preds = to_model_predictions(df, team_id="some other fund")
        assert preds == {}
        own = to_model_predictions(df, team_id=df["team_id"].iloc[0])
        assert len(own) == len(df)


class TestPoolAlignmentGuard:
    def test_shipped_packet_matches_the_default_game_pool(self):
        from src.game.manager import GameConfig, GameManager

        gm = GameManager(GameConfig(seed=20240331))
        candidates = pd.read_csv(PACKET / "game_candidates.csv")
        ok, msg = check_candidates_match_pool(
            candidates,
            {pid: p.asking_price for pid, p in gm.all_properties.items()},
            {pid: p.current_noi for pid, p in gm.all_properties.items()},
        )
        assert ok, msg

    def test_a_different_seed_is_refused(self):
        """Same ids, different buildings — this must fail loudly."""
        from src.game.manager import GameConfig, GameManager

        gm = GameManager(GameConfig(seed=20240413))
        candidates = pd.read_csv(PACKET / "game_candidates.csv")
        ok, msg = check_candidates_match_pool(
            candidates,
            {pid: p.asking_price for pid, p in gm.all_properties.items()},
            {pid: p.current_noi for pid, p in gm.all_properties.items()},
        )
        assert not ok
        assert "different" in msg.lower() or "mismatch" in msg.lower()

    def test_unknown_ids_are_rejected_by_the_contract(self):
        df = pd.read_csv(FIXTURE).head(5).copy()
        df["property_id"] = "NOT-A-REAL-ID"
        result = validate_game_submission(
            df, valid_property_ids=["OC-INDU-01"]
        )
        assert not result.ok
        assert result.unknown_property_ids == ["NOT-A-REAL-ID"]
