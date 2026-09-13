"""
Student game packet tests.

The packet only works if the data a student models is the data the game plays
with. These tests pin that contract.

Run ``python scripts/build_student_game_packet.py`` first (or let the ``packet``
fixture build it).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.game.adjudicator import BASE_CAP_RATE
from src.game.manager import GameConfig, GameManager

PACKET_DIR = REPO_ROOT / "student_packet"


@pytest.fixture(scope="module")
def packet() -> dict[str, pd.DataFrame]:
    """Build the packet if it is missing, then load it."""
    if not (PACKET_DIR / "game_candidates.csv").exists():
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_student_game_packet.py")],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
        )
    return {
        "candidates": pd.read_csv(PACKET_DIR / "game_candidates.csv"),
        "historical": pd.read_csv(PACKET_DIR / "historical_training.csv"),
        "dictionary": pd.read_csv(PACKET_DIR / "data_dictionary.csv"),
        "template": pd.read_csv(PACKET_DIR / "prediction_submission_template.csv"),
    }


@pytest.fixture(scope="module")
def game() -> GameManager:
    return GameManager(GameConfig(practice_round=False))


class TestPacketStructure:
    def test_all_files_exist(self):
        for name in [
            "game_candidates.csv",
            "historical_training.csv",
            "data_dictionary.csv",
            "prediction_submission_template.csv",
            "GAME_RULES.md",
        ]:
            assert (PACKET_DIR / name).exists(), f"{name} missing from packet"

    def test_historical_row_count_in_target_range(self, packet):
        n = len(packet["historical"])
        assert 1500 <= n <= 3000, f"historical rows {n} outside 1500-3000"

    def test_candidate_count_in_target_range(self, packet):
        n = len(packet["candidates"])
        assert 80 <= n <= 120, f"candidate count {n} outside 80-120"

    def test_dictionary_documents_every_candidate_column(self, packet):
        documented = set(packet["dictionary"]["column"])
        missing = [c for c in packet["candidates"].columns if c not in documented]
        assert not missing, f"undocumented candidate columns: {missing}"

    def test_dictionary_documents_every_historical_column(self, packet):
        documented = set(packet["dictionary"]["column"])
        missing = [c for c in packet["historical"].columns if c not in documented]
        assert not missing, f"undocumented historical columns: {missing}"


class TestPacketGameAlignment:
    """The single most important property of the packet."""

    def test_candidate_ids_equal_game_property_pool(self, packet, game):
        assert set(packet["candidates"]["property_id"]) == set(game.all_properties.keys())

    def test_candidate_asking_prices_match_game(self, packet, game):
        cand = packet["candidates"].set_index("property_id")
        for pid, prop in game.all_properties.items():
            assert cand.loc[pid, "asking_price"] == pytest.approx(prop.asking_price)

    def test_candidate_noi_matches_game(self, packet, game):
        cand = packet["candidates"].set_index("property_id")
        for pid, prop in game.all_properties.items():
            assert cand.loc[pid, "noi"] == pytest.approx(prop.current_noi)

    def test_candidate_building_size_matches_game(self, packet, game):
        """Regression: the manager used to default every building to 100k SF."""
        cand = packet["candidates"].set_index("property_id")
        for pid, prop in game.all_properties.items():
            assert cand.loc[pid, "building_sf"] == pytest.approx(prop.building_sf)
        sizes = {p.building_sf for p in game.all_properties.values()}
        assert len(sizes) > 1, "every property reported the same building size"

    def test_candidate_year_built_matches_game(self, packet, game):
        cand = packet["candidates"].set_index("property_id")
        for pid, prop in game.all_properties.items():
            assert int(cand.loc[pid, "year_built"]) == prop.year_built

    def test_candidate_max_ltv_matches_game(self, packet, game):
        cand = packet["candidates"].set_index("property_id")
        for pid, prop in game.all_properties.items():
            assert cand.loc[pid, "max_ltv"] == pytest.approx(prop.max_ltv)


class TestNoFutureLeakage:
    """Candidates must not expose anything that only exists after play."""

    def test_candidates_have_no_outcome_columns(self, packet):
        forbidden = [c for c in packet["candidates"].columns if c.startswith("next_year")]
        forbidden += [c for c in packet["candidates"].columns if "realized" in c]
        assert not forbidden, f"candidates leak outcomes: {forbidden}"

    def test_candidates_have_no_reserve_price(self, packet):
        assert "reserve_price" not in packet["candidates"].columns

    def test_historical_has_no_reserve_price(self, packet):
        assert "reserve_price" not in packet["historical"].columns

    def test_candidates_share_feature_schema_with_historical(self, packet):
        hist_only = set(packet["historical"].columns) - set(packet["candidates"].columns)
        # Only the vintage date and the outcome targets may differ.
        allowed = {"date", "transaction_cap_rate", "transaction_price",
                   "noi_growth_realized", "next_year_noi", "next_year_cap_rate",
                   "next_year_value"}
        assert hist_only <= allowed, f"unexpected historical-only columns: {hist_only - allowed}"


class TestHistoricalLearnability:
    """If the training data is noise, the whole exercise is pointless."""

    def test_cap_rate_reflects_noi_over_price(self, packet):
        h = packet["historical"]
        implied = h["noi"] / h["transaction_price"]
        assert np.allclose(implied, h["transaction_cap_rate"], atol=1e-3)

    def test_realized_outcomes_vary(self, packet):
        h = packet["historical"]
        assert h["next_year_value"].nunique() > 100
        assert h["noi_growth_realized"].std() > 0.001

    def test_noi_growth_respects_declared_bounds(self, packet):
        g = packet["historical"]["noi_growth_realized"]
        assert g.min() >= -0.10 - 1e-6
        assert g.max() <= 0.15 + 1e-6

    def test_a_simple_model_beats_the_naive_baseline(self, packet):
        """The packet must be learnable, and the relationship must transfer."""
        from sklearn.linear_model import LinearRegression

        h = packet["historical"]
        feats = ["noi", "going_in_cap", "occupancy", "property_quality",
                 "capex_need", "walt", "opex_ratio"]
        model = LinearRegression().fit(h[feats].to_numpy(), h["next_year_value"].to_numpy())
        pred = model.predict(h[feats].to_numpy())
        model_mae = np.abs(pred - h["next_year_value"]).mean()
        naive_mae = np.abs(h["next_year_value"] - h["next_year_value"].mean()).mean()
        assert model_mae < naive_mae * 0.5, (
            f"model MAE {model_mae:.3f} not meaningfully better than naive {naive_mae:.3f}"
        )

    def test_training_targets_use_the_games_own_cap_baselines(self, packet):
        """Realized cap rates must be centred on the adjudicator's constants."""
        h = packet["historical"]
        for ptype, base in BASE_CAP_RATE.items():
            subset = h[h["property_type"] == ptype]
            assert subset["next_year_cap_rate"].mean() == pytest.approx(base, abs=0.01)


class TestSubmissionTemplate:
    def test_template_has_one_row_per_candidate(self, packet):
        assert len(packet["template"]) == len(packet["candidates"])

    def test_template_ids_match_candidates(self, packet):
        assert set(packet["template"]["property_id"]) == set(packet["candidates"]["property_id"])

    def test_template_satisfies_the_game_contract_columns(self, packet):
        from src.game.submission import REQUIRED_COLUMNS

        for col in REQUIRED_COLUMNS:
            assert col in packet["template"].columns, f"template missing {col}"


class TestDeterminism:
    def test_rebuilding_produces_identical_candidates(self, packet, tmp_path):
        script = REPO_ROOT / "scripts" / "build_student_game_packet.py"
        subprocess.run(
            [sys.executable, str(script), "--out", str(tmp_path)],
            check=True, capture_output=True, cwd=REPO_ROOT,
        )
        rebuilt = pd.read_csv(tmp_path / "game_candidates.csv")
        pd.testing.assert_frame_equal(
            rebuilt, packet["candidates"], check_dtype=False
        )

    def test_rebuilding_produces_identical_historical(self, packet, tmp_path):
        script = REPO_ROOT / "scripts" / "build_student_game_packet.py"
        subprocess.run(
            [sys.executable, str(script), "--out", str(tmp_path)],
            check=True, capture_output=True, cwd=REPO_ROOT,
        )
        rebuilt = pd.read_csv(tmp_path / "historical_training.csv")
        pd.testing.assert_frame_equal(
            rebuilt, packet["historical"], check_dtype=False
        )
