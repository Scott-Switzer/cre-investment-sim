"""
Page registry for in-content navigation links.

Page modules can call pages.navigation.page("professor") to get the Page object
and render st.page_link(page_obj, ...).
"""

from __future__ import annotations

import pages

def _mod(key: str):
    if key == "home":
        import pages.home as m
        return m
    if key == "briefing":
        import pages.briefing as m
        return m
    if key == "data":
        import pages.data_catalog as m
        return m
    if key == "data-quality":
        import pages.data_quality as m
        return m
    if key == "market":
        import pages.market_explorer as m
        return m
    if key == "sql":
        import pages.sql_lab as m
        return m
    if key == "valuation":
        import pages.valuation_lab as m
        return m
    if key == "geo":
        import pages.geospatial as m
        return m
    if key == "deals":
        import pages.deal_room as m
        return m
    if key == "decision":
        import pages.investment_decision as m
        return m
    if key == "professor":
        import pages.professor_control as m
        return m
    if key == "results":
        import pages.results as m
        return m
    if key == "methodology":
        import pages.provenance as m
        return m
    if key == "datasets":
        import pages.datasets as m
        return m
    if key == "model-checkin":
        import pages.model_checkin as m
        return m
    if key == "strategy-card":
        import pages.strategy_card as m
        return m
    if key == "live-game":
        import pages.live_game as m
        return m
    if key == "leaderboard":
        import pages.leaderboard as m
        return m
    if key == "final-debrief":
        import pages.final_debrief as m
        return m
    raise KeyError(key)

PAGES = {
    "home": _mod("home"),
    "briefing": _mod("briefing"),
    "data": _mod("data"),
    "data-quality": _mod("data-quality"),
    "market": _mod("market"),
    "sql": _mod("sql"),
    "valuation": _mod("valuation"),
    "geo": _mod("geo"),
    "deals": _mod("deals"),
    "decision": _mod("decision"),
    "professor": _mod("professor"),
    "results": _mod("results"),
    "methodology": _mod("methodology"),
    # PREP mode
    "datasets": _mod("datasets"),
    "model-checkin": _mod("model-checkin"),
    "strategy-card": _mod("strategy-card"),
    # LIVE GAME mode
    "live-game": _mod("live-game"),
    "leaderboard": _mod("leaderboard"),
    "final-debrief": _mod("final-debrief"),
}

# Page groups drive the two top-level modes in the app shell.
PREP_PAGES = [
    "datasets",
    "model-checkin",
    "strategy-card",
    "briefing",
    "data",
    "data-quality",
    "market",
    "sql",
    "valuation",
    "geo",
    "deals",
    "decision",
    "methodology",
]

LIVE_GAME_PAGES = [
    "live-game",
    "leaderboard",
    "final-debrief",
    "results",
]

INSTRUCTOR_PAGES = [
    "professor",
]

_url_path_to_key = {
    "": "home",
    "briefing": "briefing",
    "data": "data",
    "data-quality": "data-quality",
    "market": "market",
    "sql": "sql",
    "valuation": "valuation",
    "geo": "geo",
    "deals": "deals",
    "decision": "decision",
    "professor": "professor",
    "results": "results",
    "methodology": "methodology",
    "datasets": "datasets",
    "model-checkin": "model-checkin",
    "strategy-card": "strategy-card",
    "live-game": "live-game",
    "leaderboard": "leaderboard",
    "final-debrief": "final-debrief",
}


def page(key: str):
    """Return the Page object for a stable key so page content can render st.page_link(page_obj)."""
    mod = PAGES[key]
    # Build a minimal Page object matching the one in app.py for st.page_link compatibility.
    import streamlit as st

    return st.Page(
        mod.show,
        title=mod.__dict__.get("__page_title__", key),
        url_path=_url_path_to_key.get(key, key),
    )


def all_page_files() -> dict[str, str]:
    """Map every registered navigation key to its source file, for tests."""
    return {
        "home": "app.py",
        "briefing": "pages/briefing.py",
        "data": "pages/data_catalog.py",
        "data-quality": "pages/data_quality.py",
        "market": "pages/market_explorer.py",
        "sql": "pages/sql_lab.py",
        "valuation": "pages/valuation_lab.py",
        "geo": "pages/geospatial.py",
        "deals": "pages/deal_room.py",
        "decision": "pages/investment_decision.py",
        "professor": "pages/professor_control.py",
        "results": "pages/results.py",
        "methodology": "pages/provenance.py",
        "datasets": "pages/datasets.py",
        "model-checkin": "pages/model_checkin.py",
        "strategy-card": "pages/strategy_card.py",
        "live-game": "pages/live_game.py",
        "leaderboard": "pages/leaderboard.py",
        "final-debrief": "pages/final_debrief.py",
    }
