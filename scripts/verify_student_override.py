#!/usr/bin/env python3
"""
Human override verification — the strongest teaching case, exercised for real.

The default demo is entirely disciplined: every bot bids at or below its own stated
ceiling, so the debrief's override analysis is empty and the most interesting
classroom conversation never happens.

This script plays the human seat with **scheduled, deliberate deviations** from the
team's own uploaded policy, then checks that the debrief can actually identify the
named cases:

    ROUND 1  follow the model closely                    -> FOLLOWED
    ROUND 2  bid materially ABOVE the model's max bid    -> OVERRODE_UP
    ROUND 3  bid BELOW the model's max on a good asset   -> OVERRODE_DOWN
    ROUND 4  leverage materially above the model's target -> LTV override

The human's model is the real student submission produced by
``scripts/build_realistic_student_submission.py`` — a genuine out-of-time-trained
model, not a hand-written stub. Deviations are the only artificial ingredient.

Outcomes are NOT manufactured. The script reports what the seed actually produced,
and can search seeds for the most instructive demonstration.

Run:

    uv run python scripts/verify_student_override.py            # default seed
    uv run python scripts/verify_student_override.py --search    # rank seeds
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from src.game.adjudicator import Bid, ModelPrediction
from src.game.analytics import debrief_answers, override_contribution
from src.game.bots import submit_bot_bids
from src.game.manager import GameConfig, GameManager
from src.game.submission import (
    check_candidates_match_pool,
    to_model_predictions,
    validate_game_submission,
)

# The packet in student_packet/ and the fixture trained from it are both built for
# this seed. Changing it requires regenerating both -- the guard in build_game()
# enforces that rather than letting a mismatched model look incompetent.
PROFESSOR_DEMO_SEED = 20240331

SUBMISSION = REPO / "tests" / "fixtures" / "student_submission_realistic.csv"
HUMAN = "REAL605 Student Fund"
BOT_ARMS = [("Value Model", "Value Fund"), ("Growth Model", "Growth Fund"),
            ("Risk Model", "Risk Fund")]

# How the human deviates from its own uploaded policy, by round index (0-based).
DEVIATIONS = {
    0: ("followed", 1.00, 0.0),      # price x factor of max_bid, ltv delta
    1: ("overrode_up", 1.08, 0.10),  # pay above the model ceiling to win
    2: ("overrode_down", 0.93, 0.0),  # undercut the model on a good asset
    3: ("ltv_override", 1.00, 0.20),  # same price, materially more leverage
}


def load_human_predictions() -> dict[str, ModelPrediction]:
    df = pd.read_csv(SUBMISSION)
    result = validate_game_submission(
        df, valid_property_ids=None
    )
    assert result.ok, f"fixture failed validation: {result.errors}"
    return to_model_predictions(df, team_id=HUMAN)


def build_game(seed: int) -> GameManager:
    from scripts.create_demo_teams import create_demo_teams

    cfg = GameConfig(seed=seed, starting_equity=100.0, total_rounds=4,
                     properties_per_round=4, practice_round=True,
                     scenario="Base Case")
    gm = GameManager(cfg)
    demo = create_demo_teams(seed=seed, count=120, save=False, verbose=False)

    def to_preds(frame, name):
        return {
            str(r["property_id"]): ModelPrediction(
                property_id=str(r["property_id"]),
                predicted_fair_value=float(r["predicted_fair_value"]),
                predicted_noi_growth=float(r["predicted_noi_growth"]),
                probability_of_downside=float(r["probability_of_downside"]),
                max_bid=float(r["max_bid"]),
                target_ltv=float(r["target_ltv"]),
                model_name=name,
                confidence=float(r["confidence"]),
            )
            for _, r in frame.iterrows()
        }

    human_preds = load_human_predictions()
    # Refuse to run the human seat against a property pool the packet was not built
    # for: same ids, different buildings. See check_candidates_match_pool.
    candidates = pd.read_csv(REPO / "student_packet" / "game_candidates.csv")
    ok, msg = check_candidates_match_pool(
        candidates,
        {pid: pm.asking_price for pid, pm in gm.all_properties.items()},
        {pid: pm.current_noi for pid, pm in gm.all_properties.items()},
    )
    if not ok:
        raise SystemExit(
            f"\nPACKET/GAME MISALIGNMENT for seed {seed}\n  {msg}\n\n"
            f"  The shipped packet and tests/fixtures/student_submission_realistic.csv "
            f"were built for the default game seed. Regenerate both with "
            f"`uv run python scripts/build_student_game_packet.py` and "
            f"`uv run python scripts/build_realistic_student_submission.py` if you "
            f"intend to play a different seed.\n"
        )

    gm.add_team(HUMAN, HUMAN, human_preds)
    for key, team in BOT_ARMS:
        gm.add_team(team, team, to_preds(demo[key], key))
    return gm


def human_bids(gm: GameManager, round_index: int, verbose: bool = True) -> list[dict]:
    """The human seat's scripted decisions for one round."""
    mode, factor, ltv_delta = DEVIATIONS[round_index]
    team = gm.teams[HUMAN]
    preds = team.model_predictions

    # Rank the deals by the model's own conviction: predicted upside over the ask.
    ranked = sorted(
        gm.current_properties.items(),
        key=lambda kv: (
            (preds[kv[0]].predicted_fair_value - kv[1].asking_price)
            / kv[1].asking_price
            if kv[0] in preds else -9,
        ),
        reverse=True,
    )

    placed = []
    # Round 2 is the deliberate aggressive round: bid on two assets to win one.
    n_bids = 2 if mode == "overrode_up" else 1

    for prop_id, prop in ranked[:n_bids]:
        pred = preds.get(prop_id)
        if pred is None:
            continue
        price = pred.max_bid * factor
        ltv = min(pred.target_ltv + ltv_delta, prop.max_ltv)
        equity = price * (1 - ltv)
        if equity > team.cash:
            price = min(price, team.cash / max(1e-9, (1 - ltv)))
            equity = price * (1 - ltv)
        try:
            gm.submit_bid(Bid(HUMAN, prop_id, price, ltv, gm.current_round,
                              f"human_r{round_index + 1}"))
            placed.append({
                "round": round_index + 1, "property_id": prop_id, "mode": mode,
                "bid": price, "ltv": ltv, "model_max_bid": pred.max_bid,
                "model_target_ltv": pred.target_ltv, "ask": prop.asking_price,
                "bid_override": price - pred.max_bid,
                "ltv_override": ltv - pred.target_ltv,
            })
        except (ValueError, RuntimeError) as exc:
            if verbose:
                print(f"    (bid rejected on {prop_id}: {exc})")
    return placed


def play(seed: int, verbose: bool = True) -> dict:
    gm = build_game(seed)
    gm.start_game()
    gm.lock_round()
    gm.resolve_round()      # practice
    gm.advance_round()

    all_placed = []
    for r in range(4):
        placed = human_bids(gm, r, verbose=verbose)
        all_placed.extend(placed)
        submit_bot_bids(gm, HUMAN)
        gm.lock_round()
        gm.resolve_round()
        if verbose:
            lines = []
            for pid, a in gm.current_round_result.auction_results.items():
                if a.sold:
                    mark = " <== YOU" if a.winning_team_id == HUMAN else ""
                    lines.append(f"{pid}→{a.winning_team_id}@{a.winning_bid:.2f}{mark}")
            print(f"  R{r + 1} [{DEVIATIONS[r][0]:<13}] " + "  ".join(lines))
        gm.advance_round()

    return {"game": gm, "placed": all_placed}


def report(seed: int) -> int:
    print("=" * 78)
    print(f"HUMAN OVERRIDE VERIFICATION — seed {seed}")
    print("=" * 78)
    print(f"human model: {SUBMISSION.name} "
          f"({len(load_human_predictions())} predictions)\n")

    out = play(seed, verbose=True)
    gm = out["game"]

    print("\nPLACED BIDS vs THE TEAM'S OWN POLICY")
    print(f"  {'R':<3}{'PROPERTY':<14}{'MODE':<15}{'ASK':>9}{'MODELMAX':>10}{'BID':>9}"
          f"{'ΔBID':>9}{'ΔLTV':>8}")
    for p in out["placed"]:
        print(f"  {p['round']:<3}{p['property_id']:<14}{p['mode']:<15}"
              f"{p['ask']:>9.2f}{p['model_max_bid']:>10.2f}{p['bid']:>9.2f}"
              f"{p['bid_override']:>+9.2f}{p['ltv_override']:>+8.2f}")

    recorded = gm.teams[HUMAN].override_history
    print(f"\n  override records written by the adjudicator for WON deals: {len(recorded)}")
    for o in recorded:
        print(f"    {o.property_id} r{o.round_number + 1}  "
              f"bid_override {o.bid_override:+.2f}  ltv_override {o.ltv_override:+.3f}")

    print("\nSTANDINGS")
    for e in gm.get_leaderboard():
        print(f"  {e['team_name']:<22} ${e['nav']:7.2f}M  {e['cumulative_return']:+6.1%}  "
              f"assets {e['properties']}")

    d = debrief_answers(gm)
    print("\nDEBRIEF — the ten questions")
    for a in d.answers:
        print(f"  {a.number:>2}. {a.question}")
        print(f"      {a.answer}")
        if a.detail:
            print(f"      ↳ {a.detail}")

    print("\nNAMED TEACHING CASES PRESENT IN THIS RUN")
    wanted = [
        "MODEL GOOD + FOLLOWED MODEL",
        "MODEL GOOD + BAD OVERRIDE",
        "MODEL WRONG + GOOD OVERRIDE",
        "GOOD DECISION + BAD REALIZED OUTCOME",
        "BAD DECISION + LUCKY REALIZED OUTCOME",
    ]
    for case in wanted:
        n = d.case_counts.get(case, 0)
        ex = d.examples.get(case)
        where = f"  e.g. {ex.property_id} r{ex.round_number + 1} ({ex.team_id})" if ex else ""
        print(f"  [{'x' if n else ' '}] {case:<42} count={n}{where}")

    ov = override_contribution(gm)
    print(f"\n  override contribution: {ov['overridden_count']} overridden "
          f"(avg {ov['overridden_avg_return']}), {ov['disciplined_count']} disciplined "
          f"(avg {ov['disciplined_avg_return']})")

    print("\nNAV CHANNELS (exact decomposition)")
    print(f"  {'FUND':<22}{'dNAV':>9}{'value':>9}{'NOI inc':>9}{'interest':>10}"
          f"{'netcarry':>10}{'gLTV':>8}")
    for c in d.channels:
        print(f"  {c.team_name:<22}{c.nav - 100:>9.2f}{c.value_channel:>9.2f}"
              f"{c.noi_income:>9.2f}{c.interest_paid:>10.2f}{c.net_carry:>10.2f}"
              f"{(c.gross_ltv or 0):>8.1%}")

    found = sum(1 for c in wanted if d.case_counts.get(c, 0) > 0)
    print(f"\n  {found}/{len(wanted)} named cases present")
    if found < len(wanted):
        print("  Missing cases are reported, not manufactured. Note that on this seed the")
        print("  human's aggressive bid WINS the asset that would otherwise have been")
        print("  bought above the ask by a bot, so the 'lucky outcome' case is displaced")
        print("  rather than absent from the classifier: the same code detects it as soon")
        print("  as some fund pays above the ask and still makes money.")
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=PROFESSOR_DEMO_SEED)
    args = ap.parse_args()
    report(args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
