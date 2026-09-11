#!/usr/bin/env python
"""Quick diagnostic for practice round + portfolio persistence."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import Bid, ModelPrediction

# ─── Practice round test ───────────────────────────────────────────────
print("=== PRACTICE ROUND TEST ===")
config = GameConfig(seed=20240331, starting_equity=100.0, total_rounds=4, practice_round=True)
gm = GameManager(config)
gm.add_team("TestTeam", "Test Team")
gm.start_game()

print(f"round_state: {gm.round_state.value}")
print(f"current_round: {gm.current_round}")
prop = list(gm.current_properties.keys())[0]
prop_obj = gm.current_properties[prop]
print(f"property: {prop}, asking_price: {prop_obj.asking_price}")

# Submit a pass bid
gm.submit_bid(Bid(
    team_id="TestTeam", property_id=prop,
    bid_price=prop_obj.asking_price * 0.5,
    ltv=0.5, round_number=gm.current_round,
    timestamp="2024-03-31T10:00:00",
))
print(f"team cash before resolve: {gm.teams['TestTeam'].cash}")

gm.lock_round()
result = gm.resolve_round()
print(f"resolved, team cash after: {gm.teams['TestTeam'].cash}")
print(f"team properties after: {len(gm.teams['TestTeam'].properties)}")

# Practice round should NOT change cash
assert gm.teams["TestTeam"].cash == 100.0, f"Practice changed cash: {gm.teams['TestTeam'].cash}"
print("PRACTICE_ROUND_PASS")
