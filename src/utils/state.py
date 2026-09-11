"""
Application state container.

Keeps the game, database, and UI config together for the Streamlit session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional
import uuid

from src.simulation.engine import Game, PropertyCase, StudentDecision
from src.data.duckdb import DuckDBBackend


@dataclass
class AppState:
    game: Optional[Game] = None
    db: Optional[DuckDBBackend] = None
    demo_mode: bool = True
    instructor_mode: bool = False
    started: bool = False
    round_index: int = 0
    current_scenario: Optional[str] = None
    decision_date: date = date(2024, 3, 31)
    available_capital_mm: float = 150.0
    locked: bool = False
    revealed: bool = False
    last_decision_id: Optional[str] = None
    audit_log: list = field(default_factory=list)
    _state: Dict[str, Any] = field(default_factory=dict)

    def log(self, message: str, **kwargs):
        self.audit_log.append({"timestamp": str(date.today()), "message": message, **kwargs})

    def save(self, key: str, value):
        self._state[key] = value

    def get(self, key: str, default=None):
        return self._state.get(key, default)


def get_state() -> AppState:
    """Convenience getter for the app state kept in the Streamlit session."""
    import streamlit as st
    if "app_state" not in st.session_state:
        st.session_state.app_state = build_demo_state(seed=20240331)
    return st.session_state.app_state


def build_demo_state(seed: int = 20240331, db_path: Optional[str] = None) -> AppState:
    """Build a state preloaded with a ready-to-demo game and database."""
    from src.data.duckdb import build_analytical_database
    from src.simulation.engine import create_game
    db = build_analytical_database(db_path=db_path, seed=seed, count=30)
    game = create_game(seed=seed, count=30)
    state = AppState(game=game, db=db, demo_mode=True)
    state.log("demo state built", seed=seed, property_count=30)
    return state


def restart_demo():
    """Reset app state to fresh demo defaults."""
    import streamlit as st
    keys_to_remove = [
        k for k in st.session_state
        if not k.startswith("_") and k not in ("_demo_teams_loaded",)
    ]
    for k in keys_to_remove:
        del st.session_state[k]
    st.session_state.app_state = build_demo_state()
    st.session_state._demo_teams_loaded = False
    st.session_state.game_manager = None
    st.session_state.game_started = False
    st.session_state.game_complete = False
    st.session_state.demo_mode = True
    st.session_state.current_team = "Your Fund"
