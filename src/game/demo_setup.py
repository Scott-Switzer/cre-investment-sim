"""
One place that builds the demonstration game.

Before this module existed, three callers each assembled their own demo game:

* ``app.py`` gave the human team the *Noisy* model and called it
  "Buy&Hold Capital";
* ``pages/professor_control.py`` added the human with **no model at all** and
  called it "Your Fund", so the live screen reported "No model predictions
  available";
* ``scripts/verify_demo_flow.py`` repeated the first version.

They drifted. A professor could start a game from the control panel and get a
different game from the one the verification script blessed.

This module is now the single source of truth for the demonstration roster:

    Buy&Hold Capital   the human seat — the real student model, loaded through
                       the public submission contract, so what the reviewer sees
                       is exactly what a student's upload produces
    Value Fund         good valuations, disciplined bids
    Growth Fund        optimistic NOI, aggressive bids
    Risk Fund          cautious downside view, lowest leverage

The human model is intentionally imperfect: a genuine out-of-time-trained model
with a stated 3% required margin and a 60% LTV cap. It is good enough to be
worth following and loose enough that overriding it is a real decision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.game.adjudicator import ModelPrediction
from src.game.manager import GameConfig, GameManager
from src.game.submission import (
    check_candidates_match_pool,
    to_model_predictions,
    validate_game_submission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = 20240331

HUMAN_TEAM_ID = "Buy&Hold Capital"
HUMAN_SUBMISSION = REPO_ROOT / "tests" / "fixtures" / "student_submission_realistic.csv"
CANDIDATES = REPO_ROOT / "student_packet" / "game_candidates.csv"

# (key in the demo-team generator, displayed team name)
BOT_ARMS = [
    ("Value Model", "Value Fund"),
    ("Growth Model", "Growth Fund"),
    ("Risk Model", "Risk Fund"),
]


def _predictions_from_frame(frame: pd.DataFrame, model_name: str) -> Dict[str, ModelPrediction]:
    out: Dict[str, ModelPrediction] = {}
    for _, row in frame.iterrows():
        pid = str(row["property_id"])
        cap = row.get("predicted_exit_cap")
        out[pid] = ModelPrediction(
            property_id=pid,
            predicted_fair_value=float(row["predicted_fair_value"]),
            predicted_noi_growth=float(row["predicted_noi_growth"]),
            probability_of_downside=(
                float(row["probability_of_downside"])
                if pd.notna(row.get("probability_of_downside"))
                else None
            ),
            max_bid=float(row["max_bid"]),
            target_ltv=float(row["target_ltv"]),
            model_name=model_name,
            confidence=(
                float(row["confidence"]) if pd.notna(row.get("confidence")) else None
            ),
            predicted_exit_cap=(float(cap) if cap is not None and pd.notna(cap) else None),
        )
    return out


def load_human_predictions(team_id: str = HUMAN_TEAM_ID) -> Dict[str, ModelPrediction]:
    """Load the preloaded human model through the public submission contract.

    Returns an empty dict if the fixture is missing, so the app still runs; the
    caller is expected to surface that rather than silently pretend.
    """
    if not HUMAN_SUBMISSION.exists():
        return {}
    df = pd.read_csv(HUMAN_SUBMISSION)
    result = validate_game_submission(df)
    if not result.ok:
        return {}
    return to_model_predictions(df, team_id=df["team_id"].iloc[0])


def pool_is_aligned(game_manager: GameManager) -> tuple[bool, str]:
    """Is the shipped packet describing the pool this game will offer?"""
    if not CANDIDATES.exists():
        return True, "no packet present"
    candidates = pd.read_csv(CANDIDATES)
    return check_candidates_match_pool(
        candidates,
        {pid: p.asking_price for pid, p in game_manager.all_properties.items()},
        {pid: p.current_noi for pid, p in game_manager.all_properties.items()},
    )


def build_demo_game(
    seed: int = DEFAULT_SEED,
    starting_equity: float = 100.0,
    total_rounds: int = 4,
    properties_per_round: int = 4,
    practice_round: bool = True,
    scenario: str = "Base Case",
    human_predictions: Optional[Dict[str, ModelPrediction]] = None,
) -> GameManager:
    """Build the standard demonstration game: one human seat, three bot funds."""
    from scripts.create_demo_teams import create_demo_teams

    config = GameConfig(
        seed=seed,
        starting_equity=starting_equity,
        total_rounds=total_rounds,
        properties_per_round=properties_per_round,
        practice_round=practice_round,
        scenario=scenario,
    )
    gm = GameManager(config)

    demo = create_demo_teams(seed=seed, count=120, save=False, verbose=False)
    for key, team_name in BOT_ARMS:
        frame = demo.get(key)
        if frame is None:
            continue
        gm.add_team(team_name, team_name, _predictions_from_frame(frame, key))

    human = human_predictions if human_predictions is not None else load_human_predictions()
    gm.add_team(HUMAN_TEAM_ID, HUMAN_TEAM_ID, human)

    ok, message = pool_is_aligned(gm)
    gm.log("demo game built", seed=seed, aligned=ok, detail=message)
    return gm
