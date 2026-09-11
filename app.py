"""
REAL 605 CRE Investment Committee Simulation — Streamlit app.

Two modes:
- TRY DEMO: unified game screen (sidebar hidden), 3 bot competitors
- NORMAL: sidebar navigation with prep/live/game pages
"""

from __future__ import annotations

import streamlit as st
from datetime import date

import pages

from src.utils.state import AppState, build_demo_state
from src.utils.config import load_app_config
from src.simulation.engine import SCENARIOS
from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import RoundState, Bid, ModelPrediction

st.set_page_config(
    page_title="REAL 605 CRE Simulation",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_CFG = load_app_config()
DECISION_DATE = date.fromisoformat(APP_CFG.get("app", {}).get("decision_date", "2024-03-31"))
AVAILABLE_CAPITAL = APP_CFG.get("app", {}).get("available_capital_mm", 150.0)


def get_state() -> AppState:
    if "app_state" not in st.session_state:
        st.session_state.app_state = build_demo_state(seed=20240331)
    return st.session_state.app_state


def restart_demo():
    for k in list(st.session_state.keys()):
        if k not in ("app_state",):
            del st.session_state[k]
    st.session_state.app_state = build_demo_state(seed=20240331)
    st.session_state.app_state.log("demo restarted")


# ── PAGE REGISTRY ────────────────────────────────────────────────────────
PREP_PAGES = {
    "home": st.Page(pages.home.show, title="Home", url_path="home"),
    "briefing": st.Page(pages.briefing.show, title="Briefing", url_path="briefing"),
    "data": st.Page(pages.data_catalog.show, title="Data Catalog", url_path="data"),
    "data-quality": st.Page(pages.data_quality.show, title="Data Quality Challenge", url_path="data-quality"),
    "market": st.Page(pages.market_explorer.show, title="Market Explorer", url_path="market"),
    "sql": st.Page(pages.sql_lab.show, title="SQL Lab", url_path="sql"),
    "valuation": st.Page(pages.valuation_lab.show, title="Valuation Lab", url_path="valuation"),
    "geo": st.Page(pages.geospatial.show, title="Geospatial View", url_path="geo"),
    "deals": st.Page(pages.deal_room.show, title="Deal Room", url_path="deals"),
    "decision": st.Page(pages.investment_decision.show, title="Investment Decision", url_path="decision"),
    "methodology": st.Page(pages.provenance.show, title="Provenance & Methodology", url_path="methodology"),
}

LIVE_GAME_PAGES = {
    "model-checkin": st.Page(pages.model_checkin.show, title="Model Check-In", url_path="model-checkin"),
    "strategy": st.Page(pages.strategy_card.show, title="Strategy Card", url_path="strategy"),
    "live-game": st.Page(pages.live_game.show, title="Live Game", url_path="live-game"),
    "leaderboard": st.Page(pages.leaderboard.show, title="Leaderboard", url_path="leaderboard"),
    "debrief": st.Page(pages.final_debrief.show, title="Final Debrief", url_path="debrief"),
}

PROFESSOR_PAGES = {
    "professor": st.Page(pages.professor_control.show, title="Professor Control", url_path="professor"),
}

PAGES = {**PREP_PAGES, **LIVE_GAME_PAGES, **PROFESSOR_PAGES}


# ── TRY DEMO MODE ────────────────────────────────────────────────────────
# When TRY DEMO is enabled: hide sidebar, render unified game screen.
# Otherwise: normal sidebar navigation.

try_demo = st.checkbox("🎮 TRY DEMO MODE", value=False,
                      help="Start a game with 3 bot competitors. No professor needed.")

if try_demo:
    # Hide sidebar during gameplay
    st.markdown("<style>[data-testid='stSidebar'] { display: none; } "
                "[data-testid='stSidebarHeader'] { display: none; } "
                "[data-testid='stSidebarNavigation'] { display: none; }</style>",
                unsafe_allow_html=True)

    gm: GameManager | None = st.session_state.get("game_manager")

    # ── PRE-GAME SCREEN ──────────────────────────────────────────────
    if gm is None:
        _render_try_demo_intro()

    # ── DURING GAME ──────────────────────────────────────────────────
    elif gm.game_complete:
        _render_try_demo_complete(gm)
    else:
        st.session_state["_in_try_demo"] = True
        pages.live_game.show()

# ── NORMAL MODE ──────────────────────────────────────────────────────────
else:
    st.title("REAL 605 CRE Investment Committee Simulation")
    st.caption("Chapman University · REAL 605 Real Estate Analytics · Prof. Tim Frenzel")

    st.sidebar.title("REAL 605 CRE Simulation")
    st.sidebar.caption("Semipsynthetic teaching app · real public data where possible")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Instructor Controls")
    demo = st.sidebar.checkbox("Demo mode", value=True)
    state = get_state()
    if demo:
        state.demo_mode = True
        state.instructor_mode = True

    st.sidebar.markdown("---")
    st.sidebar.subheader("Scenario")
    scenario = st.sidebar.selectbox("Market scenario", SCENARIOS, index=0,
                                    key="sidebar_scenario")
    state.current_scenario = scenario

    st.sidebar.markdown("---")
    st.sidebar.subheader("Game")
    if st.sidebar.button("Restart demo"):
        restart_demo()
        st.rerun()

    st.sidebar.caption(f"Decision date: {DECISION_DATE}")
    st.sidebar.caption(f"Available capital: ${AVAILABLE_CAPITAL:.0f}M")

    st.sidebar.markdown("---")
    pg = st.navigation(list(PAGES.values()), position="sidebar")
    pg.run()


# ── TRY DEMO HELPER FUNCTIONS ────────────────────────────────────────────

def _render_try_demo_intro():
    """Pre-game screen for TRY DEMO mode."""
    st.title("🏢 REAL 605 CRE Investment Game")
    st.markdown("""
### Buy & Hold Capital Partners

**Scenario:** Base Case · **Seed:** 20240331 · **Starting Equity:** $100M

You will play 4 rounds against 3 deterministic bot funds:
- **Value Fund** — accurate valuation, disciplined bids
- **Growth Fund** — optimistic forecasts, aggressive bidding
- **Risk Fund** — conservative downside estimates

**How it works:**
1. **Practice** — Learn the interface (non-scored)
2. **Rounds 1-4** — Bid on 4 CRE deals per round
3. **Leaderboard** — Ranked by NAV
4. **Debrief** — Model vs Manager vs Luck
""")

    if st.button("🚀 START PRACTICE ROUND", type="primary",
                  use_container_width=True, key="try_demo_start"):
        from scripts.create_demo_teams import create_demo_teams

        config = GameConfig(
            seed=20240331, starting_equity=100.0, total_rounds=4,
            properties_per_round=4, practice_round=True,
            scenario="Base Case",
        )
        gm = GameManager(config)
        gm.add_team("Buy&Hold Capital", "Buy&Hold Capital")

        from src.game.adjudicator import ModelPrediction

        demo_preds = create_demo_teams(seed=20240331, count=120)
        bot_names = ["Value Fund", "Growth Fund", "Risk Fund"]

        for i, (bot_name, pred_df) in enumerate(demo_preds.items()):
            if i >= 3:
                break
            mp = {}
            for _, row in pred_df.iterrows():
                mp[str(row["property_id"])] = ModelPrediction(
                    property_id=str(row["property_id"]),
                    predicted_fair_value=float(
                        row.get("predicted_fair_value") or
                        float(row["asking_price"]) * 1.02
                    ),
                    predicted_noi_growth=float(
                        row.get("predicted_noi_growth") or 0.02
                    ),
                    probability_of_downside=float(
                        row.get("probability_of_downside") or 0.2
                    ),
                    max_bid=float(
                        row.get("max_bid") or
                        float(row["asking_price"]) * 0.90
                    ),
                    target_ltv=float(row.get("target_ltv") or 0.60),
                    model_name=bot_name + " Model",
                    confidence=float(row.get("confidence") or 0.7),
                    predicted_exit_cap=float(
                        row.get("predicted_exit_cap") or 0.06
                    ),
                )
            gm.add_team(bot_name, bot_name, mp)

        gm.start_game()
        st.session_state["game_manager"] = gm
        st.session_state["current_team"] = "Buy&Hold Capital"
        st.session_state["demo_mode"] = True
        st.success("Game started! Your first round is practice.")
        st.rerun()


def _render_try_demo_complete(gm: GameManager):
    """Post-game screen for TRY DEMO mode."""
    st.title("🏆 GAME COMPLETE")

    leaderboard = gm.get_leaderboard()
    if leaderboard:
        st.subheader("Final Standings")
        for rank, entry in enumerate(leaderboard, 1):
            medal = ["🥇", "🥈", "🥉"][rank - 1] if rank <= 3 else f"#{rank}"
            st.write(
                f"{medal} **{entry['team_name']}** — "
                f"${entry['nav']:.2f}M NAV "
                f"({entry['cumulative_return']:.1%})"
            )

        st.markdown("---")
        st.subheader("Model vs Manager vs Luck")
        for team_id, team in gm.teams.items():
            overrides = getattr(team, "override_history", [])
            with st.expander(f"{team.team_name}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("NAV", f"${team.nav:.2f}M")
                c2.metric("Properties", len(team.properties))
                c3.metric("Overrides", len(overrides))
                if overrides:
                    import pandas as pd
                    st.dataframe(pd.DataFrame([{
                        "Property": o.property_id,
                        "Model": f"${o.model_max_bid:.2f}M",
                        "Actual": f"${o.actual_bid:.2f}M",
                        "Ovr": f"${o.bid_override:.2f}M",
                    } for o in overrides]),
                        use_container_width=True, hide_index=True)
    else:
        st.info("No results available.")

    if st.button("🔄 Play Again", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ("app_state", "try_demo_mode"):
                del st.session_state[k]
        st.rerun()
