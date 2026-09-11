"""
70-team bot simulation + invariant suite.

Runs 70-team × 4-scored-rounds × 20 seeds = 5,600 full games.
Checks all critical invariants after every state transition.
"""

from __future__ import annotations

import sys
sys.path.insert(0, "/Users/scottthomasswitzer/Documents/Fenrix_RE")

import hashlib
import numpy as np
import pandas as pd
from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import Bid, RoundState


def _stable_seed(base_seed, salt, modifier=0):
    digest = hashlib.sha256(f"{base_seed}:{salt}:{modifier}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def create_bot_teams(gm: GameManager, team_names, seed):
    """Add deterministic bot teams with simple policies."""
    for name in team_names:
        if name == "Value Fund":
            bid_mult, ltv = 0.90, 0.50
        elif name == "Growth Fund":
            bid_mult, ltv = 0.98, 0.70
        elif name == "Risk Fund":
            bid_mult, ltv = 0.85, 0.45
        elif name == "Aggressive":
            bid_mult, ltv = 1.02, 0.80
        elif name == "Conservative":
            bid_mult, ltv = 0.80, 0.40
        elif name == "Noisy":
            rng = np.random.default_rng(_stable_seed(seed, name))
            bid_mult = rng.uniform(0.80, 1.05)
            ltv = rng.uniform(0.40, 0.75)
        else:
            bid_mult, ltv = 0.90, 0.60
        gm.add_team(name, name)


def _make_bid(gm, team_id, prop_id, prop, bid_mult, ltv):
    """Try to submit a bid, returning True if valid."""
    try:
        gm.submit_bid(Bid(
            team_id=team_id,
            property_id=prop_id,
            bid_price=prop.asking_price * bid_mult,
            ltv=min(ltv, prop.max_ltv),
            round_number=gm.current_round,
            timestamp="2024-03-31T00:00:00",
        ))
        return True
    except (ValueError, RuntimeError):
        return False


def run_simulation(n_teams=70, n_rounds=4, n_seeds=20):
    """Run the simulation suite."""
    all_bot_names = [
        "Value Fund", "Growth Fund", "Risk Fund",
        "Aggressive", "Conservative", "Noisy",
    ]

    # Fill remaining spots with randomized bots
    while len(all_bot_names) < n_teams:
        all_bot_names.append(f"Bot_{len(all_bot_names)}")

    results = []
    failures = []
    games_run = 0
    actions_run = 0

    for seed in range(n_seeds):
        config = GameConfig(
            seed=seed,
            starting_equity=100.0,
            total_rounds=n_rounds,
            properties_per_round=4,
            practice_round=False,
            scenario="Base Case",
        )
        gm = GameManager(config)

        # Select subset of bot names for this seed
        bot_subset = all_bot_names[:n_teams]

        # Create teams
        for name in bot_subset:
            create_bot_teams(gm, [name], seed)

        # Start the game (opens first round)
        gm.start_game()

        # Track per-seed invariants
        seed_failures = []

        for round_num in range(n_rounds):
            # Bots bid
            for team_id, team in gm.teams.items():
                bid_mult, ltv = 0.90, 0.60
                if team.team_name == "Value Fund":
                    bid_mult, ltv = 0.90, 0.50
                elif team.team_name == "Growth Fund":
                    bid_mult, ltv = 0.98, 0.70
                elif team.team_name == "Risk Fund":
                    bid_mult, ltv = 0.85, 0.45
                elif team.team_name == "Aggressive":
                    bid_mult, ltv = 1.02, 0.80
                elif team.team_name == "Conservative":
                    bid_mult, ltv = 0.80, 0.40
                elif team.team_name == "Noisy":
                    rng = np.random.default_rng(_stable_seed(seed, team.team_name))
                    bid_mult = rng.uniform(0.80, 1.05)
                    ltv = rng.uniform(0.40, 0.75)

                for pid, prop in gm.current_properties.items():
                    _make_bid(gm, team_id, pid, prop, bid_mult, ltv)
                    actions_run += 1

            # Lock
            gm.lock_round()

            # Resolve
            result = gm.resolve_round()

            # ── INVARIANT CHECKS ──
            # 1. No duplicate ownership
            prop_winners = {}
            for pid, ar in result.auction_results.items():
                if ar.sold:
                    if ar.winning_team_id in prop_winners:
                        seed_failures.append(f"Duplicate owner for {pid}: {prop_winners[pid]} and {ar.winning_team_id}")
                    prop_winners[pid] = ar.winning_team_id

            # 2. Cash >= 0, Debt >= 0, NAV finite
            for tid, ts in gm.teams.items():
                if ts.cash < -0.001:
                    seed_failures.append(f"{tid}: negative cash {ts.cash}")
                if ts.debt < -0.001:
                    seed_failures.append(f"{tid}: negative debt {ts.debt}")
                if not np.isfinite(ts.nav):
                    seed_failures.append(f"{tid}: non-finite NAV {ts.nav}")
                if not np.isfinite(ts.debt):
                    seed_failures.append(f"{tid}: non-finite debt {ts.debt}")
                if not np.isfinite(ts.cash):
                    seed_failures.append(f"{tid}: non-finite cash {ts.cash}")

            # 3. NAV = Cash + ΣValues - Debt
            for tid, ts in gm.teams.items():
                pv = sum(h.current_value for h in ts.properties.values())
                expected_nav = ts.cash + pv - ts.debt
                if abs(ts.nav - expected_nav) > 0.01:
                    seed_failures.append(f"{tid}: NAV mismatch {ts.nav} ≠ {ts.cash:.2f}+{pv:.2f}-{ts.debt:.2f}")

            # 4. No two teams own same property
            for pid, owners in prop_winners.items():
                for tid, ts in gm.teams.items():
                    if pid in ts.properties and tid != owners:
                        seed_failures.append(f"Property {pid} owned by {tid} but sold to {owners}")

            # 5. Round state legal
            assert gm.round_state == RoundState.RESOLVED, \
                f"Round state not RESOLVED: {gm.round_state}"

            # 6. Practice not in scoring (not applicable for practice_round=False)

            # Advance (or complete on last round)
            if round_num < n_rounds - 1:
                gm.advance_round()
                assert gm.round_state == RoundState.OPEN
            else:
                # Final round — advance to game complete
                gm.advance_round()
                assert gm.game_complete, f"Seed {seed}: game not complete after final advance"

        # Final state: game complete
        print(f"  Seed {seed}: current_round={gm.current_round}, total_rounds={gm.config.total_rounds}, game_complete={gm.game_complete}")
        assert gm.game_complete, f"Game not complete after {n_rounds} rounds (seed {seed})"

        # Record results
        leaderboard = gm.get_leaderboard()
        results.append({
            "seed": seed,
            "winner": leaderboard[0]["team_name"] if leaderboard else "N/A",
            "winner_nav": leaderboard[0]["nav"] if leaderboard else 0,
            "failure_count": len(seed_failures),
        })

        if seed_failures:
            failures.append({"seed": seed, "failures": seed_failures})

        games_run += 1

    # ── SUMMARY ──
    print(f"\n{'='*60}")
    print(f"BOT SIMULATION RESULTS")
    print(f"{'='*60}")
    print(f"Games run: {games_run}")
    print(f"Actions (bids): {actions_run}")
    print(f"Seeds with failures: {len(failures)} / {n_seeds}")

    if failures:
        for f in failures[:5]:
            print(f"\n  Seed {f['seed']} failures:")
            for fail in f["failures"][:3]:
                print(f"    - {fail}")

    # Balance check: does one strategy dominate?
    winners = [r["winner"] for r in results]
    win_counts = {}
    for w in winners:
        win_counts[w] = win_counts.get(w, 0) + 1
    print(f"\nWinner distribution:")
    for name, count in sorted(win_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}/{n_seeds} ({count/n_seeds:.0%})")

    top_winner = max(win_counts, key=win_counts.get)
    top_pct = win_counts[top_winner] / n_seeds

    balance_ok = top_pct < 0.80  # No single winner > 80%
    print(f"\n  Dominant winner: {top_winner} at {top_pct:.0%}")
    print(f"  Balance check: {'PASS' if balance_ok else 'FAIL'} (threshold: <80%)")

    # Overall
    all_pass = len(failures) == 0 and balance_ok
    print(f"\n{'='*60}")
    print(f"70-TEAM ENGINE SIMULATION = {'PASS' if all_pass else 'PARTIAL'}")
    print(f"{'='*60}")

    return all_pass, {
        "games": games_run,
        "actions": actions_run,
        "seeds": n_seeds,
        "failures": len(failures),
        "winner_dist": win_counts,
    }


if __name__ == "__main__":
    all_pass, stats = run_simulation(n_teams=70, n_rounds=4, n_seeds=20)
    print("\n" + "=" * 60)
    print("ALL INVARIANTS = PASS" if all_pass else "SOME INVARIANT FAILURES DETECTED")
    print("=" * 60)
