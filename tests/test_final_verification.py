#!/usr/bin/env python
"""Comprehensive final verification of the complete game loop MVP."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import Bid

tests = {}

# ─── 1. Practice round doesn't affect standings ─────────────────────────
print("=== 1. PRACTICE ROUND ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
prop = list(gm.current_properties.keys())[0]
prop_obj = gm.current_properties[prop]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=prop_obj.asking_price * 0.5,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
result = gm.resolve_round()
tests["practice_round"] = "PASS" if gm.teams["Team1"].cash == 100.0 else "FAIL"
print(f"  cash after practice: {gm.teams['Team1'].cash}")
print(f"  properties after practice: {len(gm.teams['Team1'].properties)}")
print(f"  Result: {tests['practice_round']}")

# ─── 2. Round 1 → Round 2 transition ────────────────────────────────────
print("\n=== 2. ROUND 1 → ROUND 2 ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=10.0, ltv=0.5,
    round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()  # To Round 1
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=10.0, ltv=0.5,
    round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()  # To Round 2
tests["round_1_to_2"] = "PASS" if gm.current_round == 1 else "FAIL"
print(f"  current_round after 2 advances: {gm.current_round}")
print(f"  Result: {tests['round_1_to_2']}")

# ─── 3. Portfolio persistence across rounds ─────────────────────────────
print("\n=== 3. PORTFOLIO PERSISTENCE ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
# Practice - submit bid won't result in winning (no properties awarded)
prop = list(gm.current_properties.keys())[0]
prop_obj = gm.current_properties[prop]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=prop_obj.asking_price * 0.95,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
# Advance to Round 1 - no properties yet (practice doesn't award)
gm.advance_round()
# Now buy a property in Round 1
prop = list(gm.current_properties.keys())[0]
prop_obj = gm.current_properties[prop]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=prop_obj.asking_price * 0.95,  # High bid to win
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
p1 = list(gm.teams["Team1"].properties.keys())[0]
print(f"  Property won in Round 1: {p1}")
gm.advance_round()  # To Round 2
# Check property still exists after advancing to Round 2
tests["portfolio_persistence"] = "PASS" if p1 in gm.teams["Team1"].properties else "FAIL"
print(f"  Property {p1} still in portfolio after Round 2 advance: {p1 in gm.teams['Team1'].properties}")
print(f"  Result: {tests['portfolio_persistence']}")

# ─── 4. Complete 4-round game loop ──────────────────────────────────────
print("\n=== 4. COMPLETE 4-ROUND GAME LOOP ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()

# Practice
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=10.0, ltv=0.5,
    round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()  # To Round 1

# 4 scored rounds
for rnum in range(4):
    for pid in list(gm.current_properties.keys())[:2]:
        p_obj = gm.current_properties[pid]
        try:
            gm.submit_bid(Bid(
                team_id="Team1", property_id=pid,
                bid_price=p_obj.asking_price * 0.95,
                ltv=0.60,
                round_number=gm.current_round,
                timestamp="2024-03-31T10:00:00",
            ))
        except:
            pass
    gm.lock_round()
    gm.resolve_round()
    if rnum < 3:
        gm.advance_round()
    else:
        gm.advance_round()

tests["full_game_loop"] = "PASS" if gm.game_complete else "FAIL"
print(f"  game_complete: {gm.game_complete}")
print(f"  current_round: {gm.current_round}")
print(f"  Result: {tests['full_game_loop']}")

# ─── 5. Final leaderboard ordering ──────────────────────────────────────
print("\n=== 5. LEADERBOARD ORDERING ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("TeamA", "Team A")
gm.add_team("TeamB", "Team B")
gm.add_team("TeamC", "Team C")
gm.start_game()

# Practice
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="TeamA", property_id=prop,
    bid_price=gm.current_properties[prop].asking_price * 0.95,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()

# Round 1 - TeamA buys, TeamB and TeamC pass
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="TeamA", property_id=prop,
    bid_price=gm.current_properties[prop].asking_price * 0.95,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()

# Round 2 - TeamB buys
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="TeamB", property_id=prop,
    bid_price=gm.current_properties[prop].asking_price * 0.95,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()

# Round 3 - TeamC buys
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="TeamC", property_id=prop,
    bid_price=gm.current_properties[prop].asking_price * 0.95,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
gm.resolve_round()
gm.advance_round()

# Final standings
leaderboard = gm.get_leaderboard()
# TeamA should be #1 (2 properties), TeamB #2 (1), TeamC #3 (1)
tests["leaderboard_ordering"] = "PASS" if leaderboard[0]["team_id"] == "TeamA" else "FAIL"
print(f"  Leaderboard:")
for entry in leaderboard:
    print(f"    {entry['team_id']}: NAV=${entry['nav']:.2f}M, Properties={entry['properties']}")
print(f"  Result: {tests['leaderboard_ordering']}")

# ─── 6. Duplicate bid prevention ────────────────────────────────────────
print("\n=== 6. DUPLICATE BID PREVENTION ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
prop = list(gm.current_properties.keys())[0]
try:
    gm.submit_bid(Bid(
        team_id="Team1", property_id=prop,
        bid_price=10.0, ltv=0.5,
        round_number=gm.current_round,
        timestamp="2024-03-31T10:00:00",
    ))
    gm.submit_bid(Bid(
        team_id="Team1", property_id=prop,
        bid_price=10.0, ltv=0.5,
        round_number=gm.current_round,
        timestamp="2024-03-31T10:00:01",  # Different timestamp
    ))
    tests["duplicate_bid"] = "FAIL"
    print(f"  Duplicate bid was allowed!")
except RuntimeError:
    tests["duplicate_bid"] = "PASS"
    print(f"  Duplicate bid correctly rejected")
print(f"  Result: {tests['duplicate_bid']}")

# ─── 7. Late submission after lock ──────────────────────────────────────
print("\n=== 7. LATE SUBMISSION ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
prop = list(gm.current_properties.keys())[0]
gm.submit_bid(Bid(
    team_id="Team1", property_id=prop,
    bid_price=10.0, ltv=0.5,
    round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
gm.lock_round()
try:
    gm.submit_bid(Bid(
        team_id="Team1", property_id=prop,
        bid_price=10.0, ltv=0.5,
        round_number=gm.current_round,
        timestamp="2024-03-31T10:00:00",
    ))
    tests["late_submission"] = "FAIL"
    print(f"  Late bid was allowed!")
except RuntimeError:
    tests["late_submission"] = "PASS"
    print(f"  Late bid correctly rejected")
print(f"  Result: {tests['late_submission']}")

# ─── 8. Invalid LTV rejection ───────────────────────────────────────────
print("\n=== 8. INVALID LTV ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("Team1", "Team 1")
gm.start_game()
prop = list(gm.current_properties.keys())[0]
prop_obj = gm.current_properties[prop]
try:
    gm.submit_bid(Bid(
        team_id="Team1", property_id=prop,
        bid_price=prop_obj.asking_price,
        ltv=prop_obj.max_ltv + 0.1,  # Above max
        round_number=gm.current_round,
        timestamp="2024-03-31T10:00:00",
    ))
    tests["invalid_ltv"] = "FAIL"
    print(f"  Invalid LTV was allowed!")
except ValueError:
    tests["invalid_ltv"] = "PASS"
    print(f"  Invalid LTV correctly rejected")
print(f"  Result: {tests['invalid_ltv']}")

# ─── Summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VERIFICATION SUMMARY")
print("=" * 60)
for name, result in tests.items():
    status = "PASS" if result == "PASS" else "FAIL"
    print(f"  {name}: {status}")
passed = sum(1 for v in tests.values() if v == "PASS")
total = len(tests)
print(f"\n  {passed}/{total} passed")
print("=" * 60)
