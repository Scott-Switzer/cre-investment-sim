import math
import pytest

from src.scoring.metrics import (
    brier_score,
    mae,
    mape,
    forecast_value_error,
    forecast_quality_score,
    outcome_quality_score,
    decision_quality_score,
    risk_discipline_score,
    expected_levered_return_from_world,
    process_score,
    scorecard,
)
from src.scoring.weights import load_weights


class TestForecastMetrics:
    def test_mae(self):
        assert mae(10.0, 12.0) == 2.0

    def test_mape(self):
        assert mape(100.0, 110.0) == 0.10
        assert mape(0.0, 0.0) == 0.0
        assert mape(0.0, 10.0) == 1.0  # capped

    def test_mape_cap(self):
        assert mape(1.0, 10.0, cap=0.5) == 0.5

    def test_brier_perfect(self):
        assert brier_score(1.0, 1) == 0.0
        assert brier_score(0.0, 0) == 0.0

    def test_brier_worst(self):
        assert brier_score(1.0, 0) == 1.0
        assert brier_score(0.0, 1) == 1.0

    def test_brier_uninformative(self):
        assert brier_score(None, 1) == 0.25
        assert brier_score(0.5, 1) == 0.25


class TestDecisionQuality:
    def test_pass_rewards_bad_deal(self):
        # Base Case office: noi growth 0.01, cap delta 0.0
        s = decision_quality_score(
            decision="PASS", bid=49.0, ltv=0.0,
            current_noi=3.43, current_cap=0.07,
            debt_rate=0.0675, amortization_years=25,
            world_noi_growth=0.01, world_cap_delta=0.0,
            required_return=0.08, min_dscr=1.2, max_ltv=0.6,
        )
        # expected unlevered return for this office deal is ~8.07% > 8% hurdle => PASS not rewarded
        assert s < 80.0

    def test_pass_rewards_good_avoidance(self):
        # A clearly bad deal: negative expected unlevered return
        s = decision_quality_score(
            decision="PASS", bid=100.0, ltv=0.0,
            current_noi=2.0, current_cap=0.07,
            debt_rate=0.06, amortization_years=25,
            world_noi_growth=-0.10, world_cap_delta=0.02,
            required_return=0.08, min_dscr=1.2, max_ltv=0.7,
        )
        assert s >= 80.0

    def test_buy_expected_return_drives_score(self):
        # Base Case industrial: noi growth -0.01, cap delta +0.001 => weak expected return
        s = decision_quality_score(
            decision="BUY", bid=52.0, ltv=0.60,
            current_noi=3.016, current_cap=0.058,
            debt_rate=0.0635, amortization_years=25,
            world_noi_growth=-0.01, world_cap_delta=0.001,
            required_return=0.08, min_dscr=1.2, max_ltv=0.7,
        )
        exp = expected_levered_return_from_world(
            3.016, 0.058, 0.0635, 25, 52.0, 0.60, -0.01, 0.001,
        )
        assert math.isnan(exp) is False
        # weak expected return => lower decision score
        assert s < 70.0


class TestRiskDiscipline:
    def test_inside_constraints(self):
        s = risk_discipline_score(dscr=1.5, ltv=0.6, max_ltv=0.7, min_dscr=1.2)
        assert s == 100.0

    def test_dscr_below_floor(self):
        s = risk_discipline_score(dscr=1.0, ltv=0.6, max_ltv=0.7, min_dscr=1.2)
        assert s < 100.0

    def test_ltv_over_limit(self):
        s = risk_discipline_score(dscr=1.5, ltv=0.8, max_ltv=0.7, min_dscr=1.2)
        assert s < 100.0


class TestForecastQuality:
    def test_perfect_forecasts(self):
        s = forecast_quality_score(
            actual_value=50.0, predicted_value=50.0,
            actual_noi=3.0, predicted_noi=3.0,
            actual_cap=0.06, predicted_cap=0.06,
        )
        assert s == 100.0

    def test_bad_value_forecast(self):
        s = forecast_quality_score(
            actual_value=50.0, predicted_value=75.0,
            actual_noi=3.0, predicted_noi=3.0,
            actual_cap=0.06, predicted_cap=0.06,
        )
        assert s < 100.0


class TestOutcomeQuality:
    def test_exceeds_hurdle(self):
        s = outcome_quality_score(actual_levered_return=0.28, required_return=0.08)
        assert s >= 100.0

    def test_just_at_buffer_top(self):
        s = outcome_quality_score(actual_levered_return=0.28, required_return=0.08)
        assert s == 100.0

    def test_at_buffer_bottom(self):
        s = outcome_quality_score(actual_levered_return=-0.12, required_return=0.08)
        assert s == 0.0

    def test_below_hurdle(self):
        s = outcome_quality_score(actual_levered_return=0.0, required_return=0.08)
        assert s < 50.0

    def test_pass_no_outcome(self):
        s = outcome_quality_score(actual_levered_return=None, required_return=0.08)
        assert s == 50.0


class TestProcess:
    def test_no_leakage(self):
        assert process_score(used_future_data=False, leakage_trap_hit=False) == 100.0

    def test_future_data_used(self):
        assert process_score(used_future_data=True) == 40.0

    def test_leakage_trap_hit(self):
        assert process_score(leakage_trap_hit=True) == 50.0


class TestWeightsLoad:
    def test_default_weights(self):
        w = load_weights()
        assert abs(sum(w["weights"].values()) - 1.0) < 1e-9
        assert w["weights"]["financial"] == 0.35


class TestScorecardEndToEnd:
    def test_buy_scorecard(self):
        sc = scorecard(
            round_index=0,
            property_id="OC-IND-01",
            decision="BUY",
            bid=52.0, ltv=0.60,
            noi_growth_forecast=0.02, exit_cap_forecast=0.058, confidence=0.6,
            probability_of_loss=0.25,
            thesis="test",
            actual_noi_growth=-0.01, actual_cap_delta=0.001,
            actual_exit_noi=2.98584, actual_exit_cap=0.059, actual_exit_value=50.60745762711864,
            actual_levered_return=-0.03, actual_unlevered_return=0.03064,
            predicted_value=53.04, predicted_noi=3.07632,
            world_noi_growth=-0.01, world_cap_delta=0.001,
            current_noi=3.016, current_cap=0.058, debt_rate=0.0635, amortization_years=25,
            required_return=0.08, min_dscr=1.2, max_ltv=0.7,
            used_future_data=False, leakage_trap_hit=False,
        )
        assert sc.decision == "BUY"
        assert 0 <= sc.total_score <= 100
        assert sc.details["brier_loss"] is not None
