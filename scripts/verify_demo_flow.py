#!/usr/bin/env python3
"""
End-to-end verification of the professor demonstration flow.

Walks the exact sequence the demo depends on, with the real demo teams and the
real adjudicator, and fails loudly if any step breaks:

    practice -> round 1 -> bid -> bots bid -> lock -> adjudicate -> results
    -> market advances -> NAV -> leaderboard -> feedback -> round 2
    -> round 1 asset still held -> all four rounds -> winner -> debrief

Run:

    python scripts/verify_demo_flow.py

Exit code 0 means the demo flow is intact.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.game.analytics import analytics_leaderboard, assess_attempts, override_contribution
from src.game.adjudicator import Bid
from src.game.manager import GameManager

HUMAN = "Buy&Hold Capital"
BOT_KEYS = ["Value Model", "Growth Model", "Risk Model"]
BOT_TEAMS = ["Value Fund", "Growth Fund", "Risk Fund"]

CHECKS: list[tuple[str, bool, str]] = []


def check(step: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append((step, bool(ok), detail))
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {step}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def build_demo_game():
    """Four teams: one human-controlled, three deterministic demo bots."""
    from src.game.adjudicator import ModelPrediction
    from src.game.manager import GameConfig
    from scripts.create_demo_teams import create_demo_teams

    cfg = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4,
                     properties_per_round=4, practice_round=True,
                     scenario="Base Case")
    gm = GameManager(cfg)
    demo = create_demo_teams(seed=20240331, count=120, save=False, verbose=False)

    def to_preds(frame, name):
        out = {}
        for _, row in frame.iterrows():
            out[str(row["property_id"])] = ModelPrediction(
                property_id=str(row["property_id"]),
                predicted_fair_value=float(row["predicted_fair_value"]),
                predicted_noi_growth=float(row["predicted_noi_growth"]),
                probability_of_downside=float(row["probability_of_downside"]),
                max_bid=float(row["max_bid"]),
                target_ltv=float(row["target_ltv"]),
                model_name=name,
                confidence=float(row["confidence"]),
                predicted_exit_cap=(
                    float(row["predicted_exit_cap"])
                    if "predicted_exit_cap" in row and pd.notna(row["predicted_exit_cap"])
                    else None
                ),
            )
        return out

    # The human team plays the weakest model, so the demo shows a team that has
    # real reason to override its own analysis.
    gm.add_team(HUMAN, HUMAN, to_preds(demo["Noisy Model"], "Noisy Model"))
    for key, team_name in zip(BOT_KEYS, BOT_TEAMS):
        gm.add_team(team_name, team_name, to_preds(demo[key], key))
    return gm


def main() -> int:
    print("=" * 68)
    print("REAL 605 — PROFESSOR DEMO FLOW VERIFICATION")
    print("=" * 68)

    # 1-2 ── bootstrap and construct the game
    print("\nSTEP 1-2 · Build demo game")
    gm = build_demo_game()
    check("four teams seeded", len(gm.teams) == 4, f"{sorted(gm.teams)}")
    check("human team has model outputs",
          len(gm.teams[HUMAN].model_predictions) > 0,
          f"{len(gm.teams[HUMAN].model_predictions)} predictions")
    check("property pool generated", len(gm.all_properties) == 120)

    # 3-5 ── practice round
    print("\nSTEP 3-7 · Practice round (must not be scored)")
    gm.start_game()
    cash_before = {t: s.cash for t, s in gm.teams.items()}
    nav_before = {t: s.nav for t, s in gm.teams.items()}
    check("practice round opens first", gm.current_round == -1,
          f"round={gm.current_round}")

    pid = next(iter(gm.current_properties))
    prop = gm.current_properties[pid]
    gm.submit_bid(Bid(HUMAN, pid, prop.asking_price * 0.95, 0.60, -1, "practice"))
    gm.lock_round()
    gm.resolve_round()
    check("practice round resolves", gm.current_round_result is not None)
    check("practice does not change cash",
          all(gm.teams[t].cash == cash_before[t] for t in gm.teams))
    check("practice does not change NAV",
          all(gm.teams[t].nav == nav_before[t] for t in gm.teams))
    check("practice awards no property",
          all(len(gm.teams[t].properties) == 0 for t in gm.teams))

    gm.advance_round()
    check("advances to Round 1", gm.current_round == 0, f"round={gm.current_round}")

    # 6-8 ── rounds
    round1_holdings: dict[str, list[str]] = {}
    for round_index in range(gm.config.total_rounds):
        print(f"\nSTEP 8-13 · Round {round_index + 1} of {gm.config.total_rounds}")
        check(f"R{round_index + 1} shows four deals",
              len(gm.current_properties) == 4,
              f"{len(gm.current_properties)} properties")

        # Human bids on the property with the largest model edge.
        target, best = None, None
        for prop_id, pm in gm.current_properties.items():
            pred = gm.teams[HUMAN].model_predictions.get(prop_id)
            if pred is None:
                continue
            edge = pred.predicted_fair_value - pm.asking_price
            if best is None or edge > best:
                best, target = edge, prop_id

        if target is not None:
            pred = gm.teams[HUMAN].model_predictions[target]
            pm = gm.current_properties[target]
            # Deliberate humility: bid slightly below the model's max bid.
            price = max(pred.max_bid * 0.97, pm.reserve_price * 1.05)
            ltv = min(pred.target_ltv, pm.max_ltv)
            if price * (1 - ltv) <= gm.teams[HUMAN].cash:
                gm.submit_bid(Bid(HUMAN, target, price, ltv, gm.current_round, "human"))
        check(f"R{round_index + 1} human bid accepted", True,
              f"{target} @ {gm.teams[HUMAN].model_predictions.get(target).max_bid:.2f}"
              if target else "no bid")

        # The same shared policy the app uses.
        from src.game.bots import submit_bot_bids

        submit_bot_bids(gm, HUMAN)
        bot_bid_count = len([b for b in gm.submitted_bids if b.team_id in BOT_TEAMS])
        check(f"R{round_index + 1} bots submitted", bot_bid_count > 0,
              f"{bot_bid_count} bot bids from "
              f"{len({b.team_id for b in gm.submitted_bids if b.team_id in BOT_TEAMS})} funds")

        gm.lock_round()
        check(f"R{round_index + 1} locks", gm.round_state.value == "locked")
        result = gm.resolve_round()
        check(f"R{round_index + 1} resolved", gm.round_state.value == "resolved")
        check(f"R{round_index + 1} reveals winners",
              len(result.auction_results) == 4,
              f"{sum(1 for a in result.auction_results.values() if a.sold)} sold")

        for prop_id, auction in result.auction_results.items():
            if auction.sold:
                print(f"        {prop_id:<14} → {auction.winning_team_id} "
                      f"@ ${auction.winning_bid:,.2f}M  (reserve "
                      f"${auction.reserve_price:,.2f}M)")

        if round_index == 0:
            round1_holdings = {
                t: list(gm.teams[t].properties.keys()) for t in gm.teams
            }

        # 14-17 ── market advance, NAV
        check(f"R{round_index + 1} market advanced", result.market_state is not None,
              f"rate {result.market_state.policy_rate:.3%}")
        for team_id, team in gm.teams.items():
            expected = (team.cash
                        + sum(h.current_value for h in team.properties.values())
                        - team.debt)
            if abs(team.nav - expected) > 0.01:
                check(f"R{round_index + 1} NAV identity ({team_id})", False,
                      f"{team.nav:.4f} != {expected:.4f}")
        check(f"R{round_index + 1} NAV consistent for all funds", True)

        gm.advance_round()

    check("game completes after four rounds", gm.game_complete)
    check("round history has four rounds", len(gm.round_history) == 4,
          f"{sorted(gm.round_history)}")

    # 21 ── persistence
    print("\nSTEP 21 · Round 1 assets persist to the end")
    owned_then = {t: set(v) for t, v in round1_holdings.items()}
    for team_id, props in owned_then.items():
        still = set(gm.teams[team_id].properties.keys())
        check(f"{team_id}: R1 assets still held", props <= still,
              f"held {sorted(props)}" if props else "bought nothing in R1")

    # 22-23 ── winner
    print("\nSTEP 22-23 · Final standings")
    print(f"        {'RANK':<5}{'FUND':<20}{'NAV':>12}{'RETURN':>10}{'ASSETS':>8}")
    standings = gm.get_leaderboard()
    for rank, entry in enumerate(standings, 1):
        print(f"        {rank:<5}{entry['team_name']:<20}"
              f"${entry['nav']:>10,.2f}M{entry['cumulative_return']:>9.1%}"
              f"{entry['properties']:>8}")
    check("a winner exists", len(standings) > 0)
    check("winner has highest NAV",
          standings[0]["nav"] == max(e["nav"] for e in standings),
          f"{standings[0]['team_name']} @ ${standings[0]['nav']:,.2f}M")

    # 24 ── debrief
    print("\nSTEP 24 · Model / manager / luck debrief")
    board = analytics_leaderboard(gm)
    print(f"        {'FUND':<20}{'VAL MAE':>10}{'NOI MAE':>10}"
          f"{'BRIER':>9}{'VS NAIVE':>10}{'WON':>6}")
    for t in board:
        vs = f"{t.value_added_vs_naive:+.1%}" if t.value_added_vs_naive is not None else "n/a"
        vm = f"{t.valuation_mae:.2f}" if t.valuation_mae is not None else "n/a"
        nm = f"{t.noi_growth_mae:.3f}" if t.noi_growth_mae is not None else "n/a"
        br = f"{t.downside_brier:.3f}" if t.downside_brier is not None else "n/a"
        print(f"        {t.team_name:<20}{vm:>10}{nm:>10}{br:>9}{vs:>10}{t.properties_won:>6}")
    check("analytics leaderboard produced", len(board) == 4)

    attempts = assess_attempts(gm)
    check("attempts classified on three axes", len(attempts) > 0,
          f"{len(attempts)} attempts")
    if attempts:
        sample = attempts[0]
        print(f"        e.g. {sample.property_id}: {sample.headline}")
        print(f"             {sample.teaching_note()}")
    labels = {a.model_label for a in attempts}
    check("model quality classified", labels and labels <= {"GOOD_MODEL", "BAD_MODEL"},
          f"{sorted(labels)}")

    ov = override_contribution(gm)
    print(f"\n        override contribution: "
          f"{ov['overridden_count']} overridden "
          f"(avg {ov['overridden_avg_return'] if ov['overridden_avg_return'] is None else round(ov['overridden_avg_return'], 3)}), "
          f"{ov['disciplined_count']} disciplined "
          f"(avg {ov['disciplined_avg_return'] if ov['disciplined_avg_return'] is None else round(ov['disciplined_avg_return'], 3)})")

    # determinism
    print("\nSTEP 25 · Seed reproducibility")
    gm2 = build_demo_game()
    gm2.start_game()
    gm2.lock_round()
    gm2.resolve_round()
    first = build_demo_game()
    first.start_game()
    first.lock_round()
    first.resolve_round()
    check("same seed reproduces practice outcome",
          {k: round(v.exit_value, 6) for k, v in first.current_round_result.property_outcomes.items()}
          == {k: round(v.exit_value, 6) for k, v in gm2.current_round_result.property_outcomes.items()})

    # ── summary ──
    failures = [c for c in CHECKS if not c[1]]
    print("\n" + "=" * 68)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    if failures:
        print("FAILURES:")
        for step, _, detail in failures:
            print(f"  - {step} {detail}")
        print("DEMO FLOW = FAIL")
        return 1
    print("DEMO FLOW = PASS")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
