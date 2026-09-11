"""
Pages registry.

Each Streamlit page module exposes a `show()` function.
This __init__ imports them explicitly so `app.py` can reference `pages.<name>.show`.
"""

from __future__ import annotations

from pages import (
    home,
    briefing,
    data_catalog,
    data_quality,
    market_explorer,
    sql_lab,
    valuation_lab,
    geospatial,
    deal_room,
    investment_decision,
    professor_control,
    results,
    provenance,
    model_checkin,
    strategy_card,
    live_game,
    leaderboard,
    final_debrief,
)

__all__ = [
    "home",
    "briefing",
    "data_catalog",
    "data_quality",
    "market_explorer",
    "sql_lab",
    "valuation_lab",
    "geospatial",
    "deal_room",
    "investment_decision",
    "professor_control",
    "results",
    "provenance",
    "model_checkin",
    "strategy_card",
    "live_game",
    "leaderboard",
    "final_debrief",
]
