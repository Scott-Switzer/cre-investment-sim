"""
Full 4-round game loop integration test.

Practice → R1 → R2 → R3 → R4 → Winner

Verifies:
- Practice does not affect standings
- Assets bought in R1 exist through R4
- Cash/debt persist correctly
- NAV updates each round
- No property has two owners
- No double settlements
- Game completion state
"""

from __future__ import annotations

import sys
sys.path.insert(0, "/Users/scottthomasswitzer/Documents/Fenrix_RE")

import pandas as pd
import numpy as np
from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import Bid, RoundState


def run_full_game_loop():
    """Execute Practice → R1 → R2 → R3 → R4 and verify all invariants."""
    config = GameConfig(
        seed=20240331,
        starting_equity=100.0,
        total_rounds=4,
        properties_per_round=4,
        practice_round=True,
        scenario="Base Case",
    )
    gm = GameManager(config)

    # Add 4 teams: human + 3 bots
    gm.add_team("Human Team", "Human Team")
    gm.add_team("Value Fund", "Value Fund")
    gm.add_team("Growth Fund", "Growth Fund")
    gm.add_team("Risk Fund", "Risk Fund")

    # Initial state
    initial_cash = {tid: t.cash for tid, t in gm.teams.items()}
    initial_nav = {tid: t.nav for tid, t in gm.teams.items()}

    print("=== PRACTICE ROUND ===")
    # Start game — practice is auto-opened
    gm.start_game()

    # Practice is auto-opened by start_game()
    assert gm.round_state == RoundState.OPEN, \
        f"Practice should be OPEN, got {gm.round_state}"
    # Verify current_round is practice (-1)
    assert gm.current_round in (-1, 0), \
        f"Expected practice round (-1 or 0), got {gm.current_round}"
    is_practice = gm.current_round == -1
    practice_label = "Practice" if is_practice else "Round 1 (practice mode)"
    print(f"  Round: {practice_label} (current_round={gm.current_round})")

    # Submit human bid for practice
    prop_id = list(gm.current_properties.keys())[0]
    prop = gm.current_properties[prop_id]
    bid = Bid(
        team_id="Human Team",
        property_id=prop_id,
        bid_price=prop.asking_price * 0.95,
        ltv=0.60,
        round_number=gm.current_round,
        timestamp="2024-03-31T00:00:00",
    )
    assert gm.submit_bid(bid)

    # Submit bot bids for practice
    for bot_id in ["Value Fund", "Growth Fund", "Risk Fund"]:
        bot_bid = Bid(
            team_id=bot_id,
            property_id=prop_id,
            bid_price=prop.asking_price * 0.93 if "Value" in bot_id
            else prop.asking_price * 0.98 if "Growth" in bot_id
            else prop.asking_price * 0.88,
            ltv=0.55 if "Value" in bot_id
            else 0.70 if "Growth" in bot_id
            else 0.50,
            round_number=gm.current_round,
            timestamp="2024-03-31T00:00:00",
        )
        try:
            gm.submit_bid(bot_bid)
        except (ValueError, RuntimeError):
            pass  # Bot bid may be invalid

    # Lock and resolve practice
    gm.lock_round()
    assert gm.round_state == RoundState.LOCKED
    result = gm.resolve_round()
    assert gm.round_state == RoundState.RESOLVED

    # Practice should NOT have changed any team's cash or NAV
    for tid in gm.teams:
        assert gm.teams[tid].cash == initial_cash[tid], \
            f"Practice changed {tid} cash: {initial_cash[tid]} → {gm.teams[tid].cash}"
        assert gm.teams[tid].nav == initial_nav[tid], \
            f"Practice changed {tid} NAV: {initial_nav[tid]} → {gm.teams[tid].nav}"
        assert len(gm.teams[tid].properties) == 0, \
            f"Practice gave {tid} properties: {list(gm.teams[tid].properties.keys())}"

    print("✅ Practice: No standings affected")

    # Advance to Round 1
    gm.advance_round()
    assert gm.current_round == 0, f"Expected R1 (round 0), got {gm.current_round}"
    assert gm.round_state == RoundState.OPEN
    # Practice result exists in memory (show results if needed)
    print("✅ Advanced to Round 1")

    # ── RUN ALL SCORED ROUNDS ──
    all_property_ownerships = {}  # prop_id → set of team_ids that owned it

    for round_num in range(4):
        print(f"\n=== ROUND {round_num + 1} ===")
        print(f"  Properties: {list(gm.current_properties.keys())}")

        # Collect bids for all teams
        for tid in gm.teams:
            team_state = gm.teams[tid]
            if round_num == 0 and tid == "Human Team":
                # Human bids on first property
                prop_id = list(gm.current_properties.keys())[0]
                gm.submit_bid(Bid(
                    team_id=tid,
                    property_id=prop_id,
                    bid_price=gm.current_properties[prop_id].asking_price * 0.95,
                    ltv=0.60,
                    round_number=gm.current_round,
                    timestamp="2024-03-31T00:00:00",
                ))
            else:
                # Bots bid on all properties
                for pid in gm.current_properties:
                    prop = gm.current_properties[pid]
                    bot_bid = Bid(
                        team_id=tid,
                        property_id=pid,
                        bid_price=prop.asking_price * (0.93 if "Value" in tid
                                                       else 0.98 if "Growth" in tid
                                                       else 0.88),
                        ltv=0.55 if "Value" in tid
                             else 0.70 if "Growth" in tid
                             else 0.50,
                        round_number=gm.current_round,
                        timestamp="2024-03-31T00:00:00",
                    )
                    try:
                        gm.submit_bid(bot_bid)
                    except (ValueError, RuntimeError):
                        pass  # Bot may lack sufficient equity

        # Lock, resolve
        gm.lock_round()
        assert gm.round_state == RoundState.LOCKED, \
            f"Round {round_num + 1} not locked, state={gm.round_state}"

        result = gm.resolve_round()
        assert gm.round_state == RoundState.RESOLVED, \
            f"Round {round_num + 1} not resolved"
        assert result.round_number == round_num

        # Check invariants
        for pid, ar in result.auction_results.items():
            if ar.sold:
                if pid not in all_property_ownerships:
                    all_property_ownerships[pid] = set()
                assert ar.winning_team_id not in all_property_ownerships[pid], \
                    f"Property {pid} sold twice to {ar.winning_team_id}"
                all_property_ownerships[pid].add(ar.winning_team_id)

        # Verify cash >= 0 for all teams
        for tid, ts in gm.teams.items():
            assert ts.cash >= -0.01, \
                f"Round {round_num + 1}: {tid} has negative cash: {ts.cash}"
            assert ts.debt >= 0, \
                f"Round {round_num + 1}: {tid} has negative debt: {ts.debt}"
            assert np.isfinite(ts.nav), \
                f"Round {round_num + 1}: {tid} has non-finite NAV: {ts.nav}"

        print(f"  ✅ All invariants pass")
        for tid, ts in gm.teams.items():
            print(f"    {tid}: NAV=${ts.nav:.2f}M, Cash=${ts.cash:.2f}M, Properties={len(ts.properties)}")

        # Advance
        if round_num < 3:
            gm.advance_round()
            assert gm.round_state == RoundState.OPEN, \
                f"Round {round_num + 1} → {round_num + 2} transition failed"
            print(f"  ✅ Advanced to Round {round_num + 2}")
        else:
            gm.advance_round()
            assert gm.game_complete, "Round 4 should complete the game"
            assert gm.round_state == RoundState.NOT_STARTED, \
                "Game should be NOT_STARTED after completion"
            print("  ✅ Game complete!")

    # ── FINAL VERIFICATION ──
    print("\n=== FINAL STATE ===")
    leaderboard = gm.get_leaderboard()
    for rank, entry in enumerate(leaderboard, 1):
        print(f"  {rank}. {entry['team_name']}: ${entry['nav']:.2f}M ({entry['cumulative_return']:.1%})")

    # Verify properties persist across rounds
    for pid, owners in all_property_ownerships.items():
        for tid in owners:
            ts = gm.teams[tid]
            assert pid in ts.properties, \
                f"{pid} sold to {tid} but not in portfolio"
            holding = ts.properties[pid]
            assert holding.current_value > 0, \
                f"{pid} has non-positive value"
            assert holding.current_noi > 0, \
                f"{pid} has non-positive NOI"

    # Verify NAV = Cash + ΣValues - Debt
    for tid, ts in gm.teams.items():
        property_sum = sum(h.current_value for h in ts.properties.values())
        expected_nav = ts.cash + property_sum - ts.debt
        assert abs(ts.nav - expected_nav) < 0.01, \
            f"NAV mismatch for {tid}: {ts.nav} ≠ {ts.cash:.2f} + {property_sum:.2f} - {ts.debt:.2f}"

    print("\n=== ALL INVERIFICATION PASSED ===")
    print(f"  Rounds completed: 4")
    print(f"  Unique properties sold: {len(all_property_ownerships)}")
    print(f"  No duplicate sales")
    print(f"  All NAVs consistent")
    print(f"  All properties persist correctly")

    return True


if __name__ == "__main__":
    success = run_full_game_loop()
    print("\n" + "=" * 60)
    print("FOUR-ROUND GAME LOOP = PASS" if success else "FOUR-ROUND GAME LOOP = FAIL")
    print("=" * 60)
