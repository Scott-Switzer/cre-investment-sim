"""
REAL 605 CRE Investment Committee Simulation — Institutional Edition
"""
from __future__ import annotations

import streamlit as st
import time
from datetime import date
from typing import Dict
import pages
from src.utils.state import AppState, build_demo_state
from src.utils.config import load_app_config
from src.simulation.engine import SCENARIOS
from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import RoundState, Bid, ModelPrediction


# ── INSTITUTIONAL CRE STYLE — projector-optimized ──
CRE_CSS = """
<style>
/* Reset and base */
:root {
    --navy: #1a365d;
    --navy-light: #2c5282;
    --charcoal: #2d3748;
    --gray-700: #4a5568;
    --gray-500: #718096;
    --gray-400: #a0aec0;
    --gray-300: #cbd5e0;
    --gray-200: #e2e8f0;
    --gray-100: #edf2f7;
    --gray-50: #f7fafc;
    --white: #ffffff;
    --green: #276749;
    --green-bg: #f0fff4;
    --red: #9b2c2c;
    --red-bg: #fff5f5;
    --amber: #975a16;
    --amber-bg: #fffff0;
    --blue: #2b6cb0;
    --blue-bg: #ebf8ff;
}

.stApp {
    background: var(--gray-50);
    color: var(--charcoal);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

.stApp > header {
    background: var(--white) !important;
    border-bottom: 2px solid var(--navy) !important;
}

/* Page header */
.page-header {
    padding: 16px 0 12px 0;
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: 20px;
}
.page-header h1 {
    font-size: 1.6em;
    font-weight: 700;
    color: var(--navy);
    margin: 0 0 2px 0;
    letter-spacing: -0.02em;
}
.page-header p {
    font-size: 0.9em;
    color: var(--gray-500);
    margin: 0;
}

/* Status bar */
.status-bar {
    display: flex;
    gap: 16px;
    padding: 10px 14px;
    background: var(--navy);
    color: var(--white);
    border-radius: 4px;
    margin-bottom: 20px;
    font-size: 0.85em;
    flex-wrap: wrap;
}
.status-bar .status-item {
    display: flex;
    align-items: center;
    gap: 6px;
}
.status-bar .status-label {
    color: #a0aec0;
    text-transform: uppercase;
    font-size: 0.75em;
    letter-spacing: 0.05em;
}
.status-bar .status-value {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* Section headers */
.section-header {
    font-size: 1em;
    font-weight: 700;
    color: var(--navy);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 2px solid var(--navy);
    padding-bottom: 4px;
    margin: 24px 0 12px 0;
}
.subsection-header {
    font-size: 0.85em;
    font-weight: 600;
    color: var(--charcoal);
    margin: 16px 0 6px 0;
}

/* Model locked badge */
.model-locked {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    background: var(--green-bg);
    color: var(--green);
    border: 1px solid var(--green);
    border-radius: 3px;
    font-size: 0.75em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 8px 0;
}

/* Info panels */
.info-panel {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    padding: 14px;
    margin: 8px 0;
}
.info-panel.market { border-left: 3px solid var(--gray-500); }
.info-panel.model { border-left: 3px solid var(--blue); }
.info-panel.decision { border-left: 3px solid var(--navy); }

.info-panel h4 {
    font-size: 0.7em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--gray-500);
    margin: 0 0 8px 0;
}
.info-panel.model h4 { color: var(--blue); }
.info-panel.decision h4 { color: var(--navy); }

/* Data grid */
.data-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid var(--gray-100);
    font-size: 0.85em;
}
.data-row:last-child { border-bottom: none; }
.data-label { color: var(--gray-700); }
.data-value { font-weight: 600; font-variant-numeric: tabular-nums; }
.data-value.positive { color: var(--green); }
.data-value.negative { color: var(--red); }
.data-value.neutral { color: var(--charcoal); }

/* Strategy brief */
.strategy-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin: 12px 0;
}
.strategy-card {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    padding: 12px;
}
.strategy-card h4 {
    font-size: 0.7em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--gray-500);
    margin: 0 0 6px 0;
}
.strategy-card .value {
    font-size: 1.4em;
    font-weight: 700;
    color: var(--navy);
}
.strategy-card .detail {
    font-size: 0.8em;
    color: var(--gray-500);
    margin-top: 2px;
}

/* Deal board table */
.deal-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8em;
    margin: 8px 0;
}
.deal-table th {
    background: var(--gray-100);
    color: var(--charcoal);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.7em;
    letter-spacing: 0.04em;
    padding: 8px 6px;
    border: 1px solid var(--gray-300);
    text-align: center;
}
.deal-table td {
    padding: 8px 6px;
    border: 1px solid var(--gray-200);
    text-align: center;
    font-variant-numeric: tabular-nums;
}
.deal-table .property-name {
    text-align: left;
    font-weight: 600;
    color: var(--navy);
    min-width: 160px;
}
.deal-table .section-market { background: var(--gray-50); }
.deal-table .section-model { background: #ebf8ff; }
.deal-table .section-decision { background: var(--gray-50); }

/* Capital panel */
.capital-panel {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    padding: 14px;
}
.capital-item {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid var(--gray-100);
    font-size: 0.85em;
}
.capital-item:last-child { border-bottom: none; }
.capital-item .label { color: var(--gray-500); }
.capital-item .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.capital-item .value.warning { color: var(--amber); }
.capital-item .value.danger { color: var(--red); }

/* Buttons */
.stButton > button {
    background: var(--navy) !important;
    color: var(--white) !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    text-transform: none !important;
    letter-spacing: normal !important;
    font-size: 0.9em !important;
}
.stButton > button:hover {
    background: var(--navy-light) !important;
}
.stButton > button[data-testid="stBaseButton-secondary"] {
    background: var(--gray-200) !important;
    color: var(--charcoal) !important;
}

/* Metrics */
.stMetric > div > div:first-child {
    color: var(--gray-500) !important;
    font-size: 0.8em !important;
}
.stMetric > div > div:nth-child(2) {
    color: var(--charcoal) !important;
    font-size: 1.2em !important;
}

/* Tables */
.stDataFrame {
    border: 1px solid var(--gray-200) !important;
    border-radius: 4px !important;
}
.stDataFrame > div:first-child {
    border: none !important;
}

/* Leaderboard */
.leaderboard-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
}
.leaderboard-table th {
    background: var(--navy);
    color: var(--white);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.7em;
    letter-spacing: 0.04em;
    padding: 8px 10px;
    border: none;
    text-align: center;
}
.leaderboard-table th:first-child { text-align: center; width: 50px; }
.leaderboard-table td {
    padding: 10px;
    border-bottom: 1px solid var(--gray-200);
    text-align: center;
    font-variant-numeric: tabular-nums;
}
.leaderboard-table td:first-child { font-weight: 700; }
.leaderboard-table tr:nth-child(even) { background: var(--gray-50); }
.leaderboard-table tr:nth-child(1) { background: #fefce8; }
.leaderboard-table tr:nth-child(1) td { font-weight: 700; }

/* Debrief sections */
.debrief-section {
    margin: 16px 0;
}
.debrief-section h4 {
    font-size: 0.85em;
    font-weight: 700;
    color: var(--navy);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin: 0 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--gray-200);
}

/* Reflection */
.reflection-box {
    background: var(--gray-100);
    border: 1px solid var(--gray-300);
    border-radius: 4px;
    padding: 16px;
    margin: 16px 0;
}

/* Interpretation */
.interpretation {
    background: var(--blue-bg);
    border: 1px solid #90cdf4;
    border-radius: 4px;
    padding: 12px;
    margin: 12px 0;
    font-size: 0.85em;
    color: var(--blue);
}

/* Decision ticket */
.decision-ticket {
    background: var(--white);
    border: 2px solid var(--navy);
    border-radius: 4px;
    padding: 14px;
    margin: 8px 0;
}
.decision-ticket .ticket-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 0.85em;
}
.decision-ticket .ticket-label { color: var(--gray-500); }
.decision-ticket .ticket-value { font-weight: 600; }

/* Market summary */
.market-summary {
    background: var(--gray-100);
    border-left: 3px solid var(--gray-500);
    padding: 12px;
    margin: 12px 0;
    font-size: 0.9em;
    color: var(--charcoal);
    border-radius: 0 4px 4px 0;
}

/* Override indicator */
.override-positive { color: var(--green); }
.override-negative { color: var(--red); }

/* Round badge */
.round-badge {
    display: inline-block;
    background: var(--navy);
    color: var(--white);
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.7em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--white) !important;
    border-right: 1px solid var(--gray-200);
}

/* Expander */
.stExpander {
    border: 1px solid var(--gray-200);
    border-radius: 4px;
}
</style>
"""

# ── APP CONFIG ──
st.set_page_config(
    page_title="CRE Investment Committee",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CRE_CSS, unsafe_allow_html=True)

APP_CFG = load_app_config()
DECISION_DATE = date.fromisoformat(APP_CFG.get("app", {}).get("decision_date", "2024-03-31"))
AVAILABLE_CAPITAL = APP_CFG.get("app", {}).get("available_capital_mm", 150.0)

# ── SESSION STATE ──
if "game_manager" not in st.session_state:
    st.session_state.game_manager = None
if "current_team" not in st.session_state:
    st.session_state.current_team = None
if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "game_complete" not in st.session_state:
    st.session_state.game_complete = False
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = False
if "model_locked" not in st.session_state:
    st.session_state.model_locked = False
if "model_timestamp" not in st.session_state:
    st.session_state.model_timestamp = None
if "strategy" not in st.session_state:
    st.session_state.strategy = {
        "min_edge": 0.03,
        "max_ltv": 0.70,
        "max_equity_single": 0.30,
        "diversification": "none",
    }
if "round_reflection" not in st.session_state:
    st.session_state.round_reflection = {}
if "practice_complete" not in st.session_state:
    st.session_state.practice_complete = False
if "round_decision" not in st.session_state:
    st.session_state.round_decision = {}
if "capital_panel_state" not in st.session_state:
    st.session_state.capital_panel_state = {}

# ── HELPERS ──
def create_game_teams() -> GameManager:
    """Build the standard demo game.

    Delegates to src.game.demo_setup so the app shell, the professor control
    panel and scripts/verify_demo_flow.py cannot drift apart. The human seat now
    carries the real preloaded student model (loaded through the public
    submission contract) rather than the throwaway Noisy Model stub, so what a
    reviewer sees is what a student's own upload produces.
    """
    from src.game.demo_setup import build_demo_game

    return build_demo_game()


def get_team_data(gm: GameManager, team_name: str):
    """Get team state and model predictions."""
    team_state = gm.teams.get(team_name)
    predictions = team_state.model_predictions if team_state else {}
    return team_state, predictions


def fmt_currency(val: float, precision: int = 1) -> str:
    return f"${val:,.{precision}f}M"


def fmt_pct(val: float) -> str:
    return f"{val:.1%}"


def fmt_delta(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:.1f}M"


def round_interpretation(prop_name: str, your_bid: float, model_max: float,
                          market_value: float, won: bool) -> str:
    """Deterministic interpretation of round outcome."""
    parts = []
    if won:
        override = your_bid - model_max
        if abs(override) < 0.5:
            parts.append(f"You followed your model closely on {prop_name}.")
        elif override > 0:
            parts.append(f"You paid {fmt_delta(override)} above your model's max bid on {prop_name}.")
        else:
            parts.append(f"You beat your model's bid by {fmt_delta(override)} on {prop_name}.")

        if market_value and your_bid > market_value:
            parts.append(f"The market valued the property at {fmt_currency(market_value)}, below your bid of {fmt_currency(your_bid)}.")
        elif market_value:
            parts.append(f"The market valued the property at {fmt_currency(market_value)}, above your bid of {fmt_currency(your_bid)}.")
    else:
        parts.append(f"You did not win {prop_name}.")
        if market_value:
            parts.append(f"The market valued it at {fmt_currency(market_value)}.")

    return ". ".join(parts) + "."


# Demo-bot policies live in src/game/bots.py so the app, the verification script
# and the tests all run the same strategy. These wrappers keep the historical
# call signature used across the app and the test suite.
from src.game.bots import submit_bot_bids as _submit_bot_bids_impl


HUMAN_TEAM_ID = "Buy&Hold Capital"


def _submit_bot_bids(gm: GameManager, predictions: Dict = None) -> int:
    """Submit deterministic bot bids for every non-human team.

    ``predictions`` is accepted for backward compatibility and ignored: each bot
    bids from its own stored model predictions so that no team can be handed
    another team's model.
    """
    return _submit_bot_bids_impl(gm, HUMAN_TEAM_ID)


def _bot_strategy(team_id: str, pred: ModelPrediction, prop) -> dict:
    """Bid policy for a demo bot. See :mod:`src.game.bots`."""
    from src.game.bots import bot_strategy

    return bot_strategy(
        team_id, pred, prop.asking_price, getattr(prop, "max_ltv", None)
    )


# ── MAIN APP LOGIC ──

# Not started
if not st.session_state.game_started:
    st.markdown("""
    <div class="page-header">
        <h1>CRE Investment Committee</h1>
        <p>REAL 605 · Chapman University · Prof. Tim Frenzel</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        '**Build the best real estate portfolio through four rounds of strategic investing.** '
        'Analyze properties against your model, allocate capital efficiently, '
        'and outperform competing fund managers.'
    )

    st.markdown('<div class="section-header">1 · Prep — build your model before class</div>',
                unsafe_allow_html=True)
    st.markdown(
        'This app does **not** build the model for you. Download the data, build your model '
        'externally with whatever tool you like, and bring your predictions in. Your model is '
        'the analytical engine; this app is the decision environment.'
    )
    prep_cols = st.columns(3)
    with prep_cols[0]:
        st.page_link("pages/datasets.py", label="Dataset Downloads",
                     use_container_width=True)
    with prep_cols[1]:
        st.page_link("pages/model_checkin.py", label="Model Check-In",
                     use_container_width=True)
    with prep_cols[2]:
        st.page_link("pages/strategy_card.py", label="Strategy Card",
                     use_container_width=True)

    with st.expander("Analytics labs — course preparation tools (not part of the timed game)"):
        st.caption(
            "These pages exist to support REAL 605 coursework. They are deliberately "
            "separate from live gameplay so nobody has to navigate eleven analytical "
            "pages while the clock is running."
        )
        lab_cols = st.columns(4)
        labs = [
            ("pages/home.py", "Home"),
            ("pages/briefing.py", "Briefing"),
            ("pages/data_catalog.py", "Data Catalog"),
            ("pages/data_quality.py", "Data Quality"),
            ("pages/market_explorer.py", "Market Explorer"),
            ("pages/sql_lab.py", "SQL Lab"),
            ("pages/valuation_lab.py", "Valuation Lab"),
            ("pages/geospatial.py", "Geospatial View"),
            ("pages/deal_room.py", "Deal Room"),
            ("pages/investment_decision.py", "Investment Decision"),
            ("pages/leaderboard.py", "Analytics Leaderboard"),
            ("pages/final_debrief.py", "Final Debrief"),
            ("pages/provenance.py", "Provenance"),
        ]
        for i, (path, label) in enumerate(labs):
            with lab_cols[i % 4]:
                st.page_link(path, label=label, use_container_width=True)

    st.markdown('<div class="section-header">2 · Live Game — compete for capital</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="subsection-header">Strategy Brief</div>', unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        st.markdown('<div class="strategy-card">'
                    '<h4>Starting Equity</h4>'
                    '<div class="value">$100.0M</div>'
                    '</div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown('<div class="strategy-card">'
                    '<h4>Competition</h4>'
                    '<div class="value">3 Funds</div>'
                    '<div class="detail">Value Fund, Growth Fund, Risk Fund</div>'
                    '</div>', unsafe_allow_html=True)
    with cols[2]:
        st.markdown('<div class="strategy-card">'
                    '<h4>Rounds</h4>'
                    '<div class="value">4 + Practice</div>'
                    '<div class="detail">Rank by final NAV</div>'
                    '</div>', unsafe_allow_html=True)

    st.markdown('<div class="subsection-header">Investment Policy</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        edge_pct = st.number_input(
            "Minimum model edge to bid (%)",
            min_value=0.0, max_value=20.0,
            value=3.0, step=0.5, format="%0.1f", key="strat_edge_pct")
        edge = edge_pct / 100.0
    with c2:
        ltv_pct = st.number_input(
            "Maximum LTV (%)",
            min_value=0.0, max_value=90.0,
            value=70.0, step=5.0, format="%0.0f", key="strat_ltv_pct")
        max_ltv = ltv_pct / 100.0
    with c3:
        max_eq = st.number_input(
            "Max equity in one property (%)",
            min_value=0.0, max_value=100.0,
            value=30.0, step=5.0, format="%0.0f", key="strat_eq_pct")
        max_eq = max_eq / 100.0
    with c4:
        divers = st.selectbox("Diversification", ["None", "Max 1 per type", "Max 1 per submarket"],
                               index=0, key="strat_div")
    st.session_state.strategy = {
        "min_edge": edge, "max_ltv": max_ltv,
        "max_equity_single": max_eq, "diversification": divers,
    }

    st.markdown('<div class="section-header">3 · Professor / Classroom Mode</div>',
                unsafe_allow_html=True)
    st.caption(
        "Instructor entry point: start and control rounds, open and lock bidding, "
        "resolve the market, reveal standings, and open the final debrief. "
        "Everything here works with on-screen controls — no terminal."
    )
    instr_cols = st.columns(3)
    with instr_cols[0]:
        st.page_link("pages/professor_control.py", label="Professor Control",
                     use_container_width=True)
    with instr_cols[1]:
        st.page_link("pages/leaderboard.py", label="Leaderboard",
                     use_container_width=True)
    with instr_cols[2]:
        st.page_link("pages/final_debrief.py", label="Final Debrief",
                     use_container_width=True)

    st.markdown("---")
    st.markdown('<div class="subsection-header">TRY DEMO</div>', unsafe_allow_html=True)
    st.caption(
        "No account, no upload, no instructor: a model is preloaded for you. "
        "You are **Buy&Hold Capital**, up against Value Fund, Growth Fund and "
        "Risk Fund. Start with the practice round, then play four scored years."
    )
    if st.button("BEGIN PRACTICE ROUND", use_container_width=True, type="primary"):
        from src.game.demo_setup import HUMAN_TEAM_ID, pool_is_aligned

        gm = create_game_teams()
        gm.start_game()
        aligned, message = pool_is_aligned(gm)
        if not aligned:
            st.warning(f"Data packet does not match this game's property pool: {message}")

        st.session_state.game_manager = gm
        st.session_state.current_team = HUMAN_TEAM_ID
        st.session_state.game_started = True
        st.session_state.model_locked = True
        st.session_state.model_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.practice_complete = False
        st.session_state.demo_mode = True
        st.rerun()

# Started but no GM
elif st.session_state.game_started and not st.session_state.game_manager:
    st.error("Game state lost. Please restart.")
    if st.button("RESTART"):
        st.session_state.game_started = False
        st.rerun()

# In game
else:
    gm: GameManager = st.session_state.game_manager
    team_name = st.session_state.current_team or "Buy&Hold Capital"
    team_state, predictions = get_team_data(gm, team_name)

    # Game complete
    if gm.game_complete:
        st.markdown("""
        <div class="page-header">
            <h1>Game Complete</h1>
            <p>Final results and analysis</p>
        </div>
        """, unsafe_allow_html=True)

        leaderboard = gm.get_leaderboard()
        if leaderboard:
            st.markdown('<div class="section-header">Final Standings</div>', unsafe_allow_html=True)
            st.markdown("""
            <table class="leaderboard-table">
                <tr>
                    <th>Rank</th><th>Fund</th><th>NAV</th><th>Return</th>
                    <th>Properties</th><th>Cash</th><th>Debt</th>
                </tr>
            """, unsafe_allow_html=True)
            for i, entry in enumerate(leaderboard):
                st.markdown(
                    f"<tr>"
                    f"<td>{i+1}</td>"
                    f"<td>{entry['team_name']}</td>"
                    f"<td>${entry['nav']:.2f}M</td>"
                    f"<td>{entry['cumulative_return']:.1%}</td>"
                    f"<td>{entry['properties']}</td>"
                    f"<td>${entry['cash']:.2f}M</td>"
                    f"<td>${entry['debt']:.2f}M</td>"
                    f"</tr>", unsafe_allow_html=True)
            st.markdown("</table>", unsafe_allow_html=True)

        if st.button("PLAY AGAIN", use_container_width=True):
            st.session_state.game_manager = None
            st.session_state.game_started = False
            st.session_state.game_complete = False
            st.rerun()

    # Practice intro
    elif not st.session_state.practice_complete and (gm.round_state == RoundState.NOT_STARTED or gm.round_state == RoundState.OPEN and gm.current_round == -1):
        st.markdown("""
        <div class="page-header">
            <h1>Practice Round</h1>
            <p>Guided introduction to the deal board</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="model-locked">&#10003; Model locked at ' +
                    st.session_state.model_timestamp + '</div>', unsafe_allow_html=True)

        prop_list = list(gm.current_properties.items())
        if not prop_list:
            gm.start_game()
            prop_list = list(gm.current_properties.items())

        if prop_list:
            practice_prop_id, practice_prop = prop_list[0]
            pred = predictions.get(practice_prop_id)

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                st.markdown('<div class="info-panel market">'
                            '<h4>Market Data</h4>'
                            '<div class="data-row"><span class="data-label">Asking</span><span class="data-value">'
                            f'{fmt_currency(practice_prop.asking_price)}</span></div>'
                            '<div class="data-row"><span class="data-label">Cap Rate</span><span class="data-value">'
                            f'{fmt_pct(practice_prop.current_cap)}</span></div>'
                            '<div class="data-row"><span class="data-label">Occupancy</span><span class="data-value">'
                            f'{fmt_pct(practice_prop.occupancy)}</span></div>'
                            '</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="info-panel model">'
                            '<h4>Your Model</h4>'
                            '<div class="data-row"><span class="data-label">Fair Value</span><span class="data-value">'
                            f'{fmt_currency(pred.predicted_fair_value) if pred else "N/A"}</span></div>'
                            '<div class="data-row"><span class="data-label">Model Edge</span><span class="data-value '
                            f"{'positive' if pred and pred.predicted_fair_value > practice_prop.asking_price else 'negative'}\">"
                            f'{fmt_delta(pred.predicted_fair_value - practice_prop.asking_price) if pred else "N/A"}</span></div>'
                            '<div class="data-row"><span class="data-label">Max Bid</span><span class="data-value">'
                            f'{fmt_currency(pred.max_bid) if pred else "N/A"}</span></div>'
                            '<div class="data-row"><span class="data-label">Target LTV</span><span class="data-value">'
                            f'{fmt_pct(pred.target_ltv) if pred else "N/A"}</span></div>'
                            '</div>', unsafe_allow_html=True)
            with col3:
                st.markdown('<div class="info-panel decision">'
                            '<h4>Your Decision</h4>', unsafe_allow_html=True)
                decision = st.radio("PASS or BID?", ["PASS", "BID"],
                                     horizontal=True, key="prac_dec")
                if decision == "BID":
                    bid_val = st.number_input("Bid ($M)", min_value=0.0,
                                              max_value=practice_prop.asking_price * 1.2,
                                              value=float(practice_prop.asking_price * 0.95) if pred else 0.0,
                                              step=0.5, format="%.1f", key="prac_bid")
                    ltv_val = st.number_input("LTV", min_value=0.0, max_value=practice_prop.max_ltv,
                                               value=pred.target_ltv if pred else 0.60, step=0.05,
                                               format="%.2f", key="prac_ltv")
                    eq_req = bid_val * (1 - ltv_val)
                    st.markdown(f'<div class="data-row"><span class="data-label">Equity Required</span><span class="data-value">{fmt_currency(eq_req)}</span></div>',
                                unsafe_allow_html=True)
                    if pred:
                        override = bid_val - pred.max_bid
                        ov_class = "positive" if override > 0 else "negative"
                        st.markdown(f'<div class="data-row"><span class="data-label">Override vs Model</span><span class="data-value {ov_class}">{fmt_delta(override)}</span></div>',
                                    unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="data-row"><span class="data-value">PASS</span></div></div>',
                                unsafe_allow_html=True)

            if st.button("SUBMIT PRACTICE DECISION", use_container_width=True, type="primary"):
                if decision == "BID":
                    bid = Bid(team_id=team_name, property_id=practice_prop_id,
                              bid_price=bid_val, ltv=ltv_val, round_number=gm.current_round,
                              timestamp=time.strftime("%Y-%m-%d %H:%M:%S"), confidence=0.8)
                    try:
                        gm.submit_bid(bid)
                    except ValueError as e:
                        st.error(str(e))
                        st.rerun()
                # Lock the round before resolving (required by GameManager)
                try:
                    gm.lock_round()
                except RuntimeError as e:
                    st.error(f"Lock failed: {e}")
                    st.rerun()
                try:
                    gm.resolve_round()
                    st.session_state.practice_complete = True
                    st.session_state.round_decision = {"submitted": True}
                    st.rerun()
                except Exception as e:
                    st.error(f"Resolve failed: {e}")

    # Practice results
    elif st.session_state.practice_complete and gm.round_state == RoundState.RESOLVED:
        st.markdown("""
        <div class="page-header">
            <h1>Practice Complete</h1>
            <p>This round does not affect standings</p>
        </div>
        """, unsafe_allow_html=True)

        result = gm.current_round_result
        if result and result.auction_results:
            for prop_id, auction in result.auction_results.items():
                prop = gm.current_properties.get(prop_id)
                if prop:
                    st.markdown(f'<div class="section-header">{prop.property_name}</div>', unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        if auction.sold:
                            if auction.winning_team_id == team_name:
                                st.success(f"Won for {fmt_currency(auction.winning_bid)}")
                            else:
                                st.info(f"Sold to {auction.winning_team_id} for {fmt_currency(auction.winning_bid)}")
                        else:
                            st.warning(f"Not sold (reserve: {fmt_currency(auction.reserve_price)})")
                    with col2:
                        pred = predictions.get(prop_id)
                        if pred:
                            st.markdown(f"Model fair value: <strong>{fmt_currency(pred.predicted_fair_value)}</strong>",
                                        unsafe_allow_html=True)

        if st.button("START ROUND 1", use_container_width=True, type="primary"):
            gm.advance_round()
            st.session_state.round_decision = {}
            st.rerun()

    # Round market brief
    elif gm.round_state == RoundState.NOT_STARTED and gm.current_round >= 0:
        st.markdown("""
        <div class="page-header">
            <h1>Round {} Market Brief</h1>
            <p>Current market conditions</p>
        </div>
        """.format(gm.current_round + 1), unsafe_allow_html=True)

        st.markdown('<div class="model-locked">&#10003; Model locked at ' +
                    st.session_state.model_timestamp + '</div>', unsafe_allow_html=True)

        ms = getattr(gm, 'current_market_state', None)
        if ms:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("10Y Treasury", fmt_pct(ms.get('policy_rate', 0.04)))
            c2.metric("Employment Growth", fmt_pct(ms.get('employment_growth', 0.02)))
            c3.metric("Vacancy", fmt_pct(ms.get('vacancy', 0.08)))
            c4.metric("Rent Growth", fmt_pct(ms.get('rent_growth', 0.03)))

            summary = ms.get('summary', '')
            if summary:
                st.markdown(f'<div class="market-summary">{summary}</div>', unsafe_allow_html=True)

        if st.button("VIEW DEALS", use_container_width=True, type="primary"):
            st.session_state.round_decision = {}
            st.rerun()

    # Deal board (open for bidding)
    elif gm.round_state == RoundState.OPEN and gm.current_round >= 0:
        st.markdown("""
        <div class="page-header">
            <h1>Round {} — Deal Board</h1>
            <p>Submit investment decisions for this round</p>
        </div>
        """.format(gm.current_round + 1), unsafe_allow_html=True)

        st.markdown('<div class="model-locked">&#10003; Model locked at ' +
                    st.session_state.model_timestamp + '</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-header">Deals Available</div>', unsafe_allow_html=True)

        properties = gm.current_properties
        if not properties:
            st.warning("No properties available this round.")
        else:
            # Build deal table
            st.markdown('<table class="deal-table">', unsafe_allow_html=True)

            # Headers
            st.markdown("<tr><th>Property</th></tr>")
            st.markdown('<tr><th>Market</th><th>Asking</th><th>Cap</th><th>Occup</th></tr>')
            st.markdown('<tr><th>Model</th><th>FV</th><th>Edge</th><th>Max Bid</th><th>D/Side</th><th>Target LTV</th></tr>')
            st.markdown('<tr><th>Decision</th><th>Bid</th><th>LTV</th><th>Override</th></tr>')
            st.markdown("</table>", unsafe_allow_html=True)

            # Rows
            for prop_id, prop in properties.items():
                pred = predictions.get(prop_id)
                saved = st.session_state.round_decision.get(prop_id, {})
                dec = saved.get("decision", "PASS")
                bid = saved.get("bid", 0.0)
                ltv = saved.get("ltv", 0.60)

                edge = pred.predicted_fair_value - prop.asking_price if pred else 0.0
                override = bid - pred.max_bid if pred and bid > 0 else 0.0

                st.markdown(
                    f"<tr>"
                    f"<td class='property-name'>{prop.property_name}</td>"
                    f"<td class='section-market'>{fmt_currency(prop.asking_price)}</td>"
                    f"<td class='section-market'>{fmt_pct(prop.current_cap)}</td>"
                    f"<td class='section-market'>{fmt_pct(prop.occupancy)}</td>"
                    f"<td class='section-model'>{fmt_currency(pred.predicted_fair_value) if pred else 'N/A'}</td>"
                    f"<td class='section-model'><span class='{'positive' if edge > 0 else 'negative'}'>{fmt_delta(edge)}</span></td>"
                    f"<td class='section-model'>{fmt_currency(pred.max_bid) if pred else 'N/A'}</td>"
                    f"<td class='section-model'>{fmt_pct(pred.probability_of_downside) if pred else 'N/A'}</td>"
                    f"<td class='section-model'>{fmt_pct(pred.target_ltv) if pred else 'N/A'}</td>"
                    f"<td class='section-decision'><strong>{dec}</strong></td>"
                    f"<td class='section-decision'>{fmt_currency(bid) if bid > 0 else '&mdash;'}</td>"
                    f"<td class='section-decision'>{fmt_pct(ltv)}</td>"
                    f"<td class='section-decision'><span class='{'override-positive' if override > 0 else 'override-negative'}'>{fmt_delta(override)}</span></td>"
                    f"</tr>",
                    unsafe_allow_html=True
                )

            # Capital allocation controls
            st.markdown('<div class="section-header">Capital Allocation</div>', unsafe_allow_html=True)

            cap_cols = st.columns([2, 1])
            with cap_cols[0]:
                for prop_id, prop in properties.items():
                    pred = predictions.get(prop_id)
                    saved = st.session_state.round_decision.get(prop_id, {})

                    st.markdown(f'<div class="subsection-header">{prop.property_name}</div>', unsafe_allow_html=True)
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        dec = st.radio("Decision", ["PASS", "BID"],
                                       key=f"dec_{prop_id}",
                                       index=0 if not saved.get("decision") or saved["decision"] == "PASS" else 1,
                                       horizontal=True)
                    with c2:
                        if dec == "BID":
                            b = st.number_input("Bid ($M)", min_value=0.0,
                                                max_value=prop.asking_price * 1.2,
                                                value=float(st.session_state.round_decision.get(prop_id, {}).get("bid",
                                                pred.max_bid if pred else prop.asking_price * 0.95)),
                                                step=0.5, format="%.1f", key=f"bid_{prop_id}")
                            l = st.number_input("LTV", min_value=0.0, max_value=prop.max_ltv,
                                                value=float(st.session_state.round_decision.get(prop_id, {}).get("ltv",
                                                pred.target_ltv if pred else 0.60)),
                                                step=0.05, format="%.2f", key=f"ltv_{prop_id}")
                            eq = b * (1 - l)
                            if pred:
                                ov = b - pred.max_bid
                                st.caption(f"Override: {fmt_delta(ov)}")

                    if dec == "PASS":
                        st.session_state.round_decision[prop_id] = {"decision": "PASS"}
                    else:
                        st.session_state.round_decision[prop_id] = {
                            "decision": "BID", "bid": b, "ltv": l
                        }

            with cap_cols[1]:
                st.markdown('<div class="capital-panel">', unsafe_allow_html=True)
                st.markdown('<h4 style="font-size:0.75em;text-transform:uppercase;letter-spacing:0.04em;color:#718096;margin:0 0 10px 0;">Capital Status</h4>', unsafe_allow_html=True)

                total_equity = 0
                for pid, sd in st.session_state.round_decision.items():
                    if sd.get("decision") == "BID":
                        bid_v = sd.get("bid", 0)
                        ltv_v = sd.get("ltv", 0.6)
                        total_equity += bid_v * (1 - ltv_v)

                remaining_cash = (team_state.cash if team_state else 100.0) - total_equity
                port_ltv = (team_state.debt / (team_state.nav if team_state.nav > 0 else 100.0)) if team_state else 0.0

                st.markdown(f'<div class="capital-item"><span class="label">Available Cash</span><span class="value">{fmt_currency(team_state.cash if team_state else 100.0)}</span></div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="capital-item"><span class="label">Required Equity</span><span class="value">{fmt_currency(total_equity)}</span></div>',
                            unsafe_allow_html=True)
                eq_class = "danger" if remaining_cash < 0 else "warning" if remaining_cash < total_equity * 0.2 else ""
                st.markdown(f'<div class="capital-item"><span class="label">Remaining</span><span class="value {eq_class}">{fmt_currency(remaining_cash)}</span></div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="capital-item"><span class="label">Portfolio LTV</span><span class="value">{fmt_pct(port_ltv)}</span></div>',
                            unsafe_allow_html=True)

                prop_count = len(team_state.properties) if team_state else 0
                st.markdown(f'<div class="capital-item"><span class="label">Properties Owned</span><span class="value">{prop_count}</span></div>',
                            unsafe_allow_html=True)

                if remaining_cash < 0:
                    st.markdown('<div style="color:#9b2c2c;font-size:0.8em;margin-top:8px;">&#9888; Capital exceeded</div>',
                                unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

        if st.button("REVIEW & SUBMIT ROUND", use_container_width=True, type="primary"):
            # 1. Submit human bids from the decision table
            for prop_id, sd in st.session_state.round_decision.items():
                if sd.get("decision") == "BID":
                    bid = Bid(
                        team_id=team_name,
                        property_id=prop_id,
                        bid_price=sd["bid"],
                        ltv=sd["ltv"],
                        round_number=gm.current_round,
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        confidence=0.8,
                    )
                    try:
                        gm.submit_bid(bid)
                    except (ValueError, RuntimeError) as e:
                        st.error(f"Bid error for {prop_id}: {e}")
                        st.rerun()

            # 2. Submit deterministic bot bids for all competing funds
            _submit_bot_bids(gm, predictions)

            # 3. Lock the round (required before resolve)
            try:
                gm.lock_round()
            except RuntimeError as e:
                st.error(f"Lock failed: {e}")
                st.rerun()

            st.rerun()

    # Waiting / market closed
    elif gm.round_state == RoundState.LOCKED:
        st.markdown("""
        <div class="page-header">
            <h1>Round {} — Decisions Locked</h1>
            <p>Your decisions have been submitted</p>
        </div>
        """.format(gm.current_round + 1), unsafe_allow_html=True)

        st.markdown('<div class="section-header">Your Decisions</div>', unsafe_allow_html=True)

        for prop_id, sd in st.session_state.round_decision.items():
            prop = gm.current_properties.get(prop_id)
            pred = predictions.get(prop_id)
            if prop:
                st.markdown(f'<div class="decision-ticket">', unsafe_allow_html=True)
                st.markdown(f'<div class="ticket-row"><span class="ticket-label">{prop.property_name}</span></div>')
                if sd.get("decision") == "BID":
                    st.markdown(f'<div class="ticket-row"><span class="ticket-label">Bid</span><span class="ticket-value">{fmt_currency(sd["bid"])}</span></div>')
                    st.markdown(f'<div class="ticket-row"><span class="ticket-label">LTV</span><span class="ticket-value">{fmt_pct(sd["ltv"])}</span></div>')
                    if pred:
                        st.markdown(f'<div class="ticket-row"><span class="ticket-label">Model Max</span><span class="ticket-value">{fmt_currency(pred.max_bid)}</span></div>')
                        ov_class = "override-positive" if sd["bid"] - pred.max_bid > 0 else "override-negative"
                        st.markdown(f'<div class="ticket-row"><span class="ticket-label">Override</span><span class="ticket-value {ov_class}">{fmt_delta(sd["bid"]-pred.max_bid)}</span></div>')
                else:
                    st.markdown(f'<div class="ticket-row"><span class="ticket-label">PASS</span></div>')
                st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.demo_mode:
            if st.button("REVEAL MARKET RESULTS", use_container_width=True, type="primary"):
                try:
                    gm.resolve_round()
                    st.rerun()
                except Exception as e:
                    st.error(f"Resolve failed: {e}")
        else:
            st.info("Waiting for professor to close market and reveal results.")

    # Round results
    elif gm.round_state == RoundState.RESOLVED:
        st.markdown("""
        <div class="page-header">
            <h1>Round {} Results</h1>
            <p>Auction and investment outcomes</p>
        </div>
        """.format(gm.current_round + 1), unsafe_allow_html=True)

        result = gm.current_round_result
        if result:
            for prop_id, auction in result.auction_results.items():
                prop = gm.current_properties.get(prop_id)
                pred = predictions.get(prop_id) if prop else None
                if not prop:
                    continue

                st.markdown(f'<div class="section-header">{prop.property_name}</div>', unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown('<h4 style="margin:0 0 8px 0;font-size:0.8em;text-transform:uppercase;color:#4a5568;">Auction Result</h4>', unsafe_allow_html=True)
                    your_bid = st.session_state.round_decision.get(prop_id, {}).get("bid", 0)
                    st.markdown(f'Your bid: <strong>{fmt_currency(your_bid)}</strong>', unsafe_allow_html=True)
                    if pred:
                        st.markdown(f'Model max: <strong>{fmt_currency(pred.max_bid)}</strong>', unsafe_allow_html=True)
                    winning_bid_text = fmt_currency(auction.winning_bid) if auction.winning_bid is not None else "No Sale"
                    st.markdown(f'Winning bid: <strong>{winning_bid_text}</strong>', unsafe_allow_html=True)
                    won = auction.winning_team_id == team_name
                    if won:
                        st.markdown(f'Result: <strong style="color:#276749">Won</strong>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'Result: <strong style="color:#9b2c2c">{auction.reason if auction.reason else "Lost"}</strong>', unsafe_allow_html=True)

                with c2:
                    st.markdown('<h4 style="margin:0 0 8px 0;font-size:0.8em;text-transform:uppercase;color:#4a5568;">Market Result</h4>', unsafe_allow_html=True)
                    if pred:
                        st.markdown(f'Model FV: <strong>{fmt_currency(pred.predicted_fair_value)}</strong>', unsafe_allow_html=True)
                    outcome = result.property_outcomes.get(prop_id)
                    mkt_val = outcome.exit_value if outcome else None
                    if not auction.sold:
                        st.markdown(f'Outcome: <strong style="color:#9b2c2c">No Sale — {auction.reason}</strong>', unsafe_allow_html=True)
                    if mkt_val:
                        st.markdown(f'Current value: <strong>{fmt_currency(mkt_val)}</strong>', unsafe_allow_html=True)
                        if auction.sold and auction.winning_bid:
                            ret = (mkt_val - auction.winning_bid) / auction.winning_bid
                            ret_class = 'color:#276749' if ret >= 0 else 'color:#9b2c2c'
                            st.markdown(f'Trade return: <strong style="{ret_class}">{fmt_pct(ret)}</strong>', unsafe_allow_html=True)

                # Interpretation
                interp = round_interpretation(
                    prop.property_name,
                    your_bid,
                    pred.max_bid if pred else 0,
                    mkt_val if mkt_val else None,
                    won
                )
                st.markdown(f'<div class="interpretation">{interp}</div>', unsafe_allow_html=True)

        # Portfolio update
        st.markdown('<div class="section-header">Portfolio Update</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        if team_state:
            c1.metric("NAV", f"${team_state.nav:.2f}M")
            c2.metric("Cash", f"${team_state.cash:.2f}M")
            c3.metric("Debt", f"${team_state.debt:.2f}M")
            c4.metric("LTV", f"{fmt_pct(team_state.debt / team_state.nav if team_state.nav > 0 else 0)}")
            c5.metric("Properties", len(team_state.properties))
            prev_nav = st.session_state.capital_panel_state.get("prev_nav", team_state.nav)
            nav_chg = team_state.nav - prev_nav
            nav_color = '#276749' if nav_chg >= 0 else '#9b2c2c'
            nav_arrow = 'up' if nav_chg >= 0 else 'down'
            c6.metric(
                "NAV Change",
                f"${nav_chg:+.1f}M",
                delta=f"{nav_chg:+.1f}M",
                delta_color='normal' if nav_chg >= 0 else 'inverse',
            )

        if team_state.properties:
            st.markdown('<div class="subsection-header">Holdings</div>', unsafe_allow_html=True)
            for pid, holding in team_state.properties.items():
                st.markdown(
                    f'<div class="data-row"><span class="data-label">{pid}</span>'
                    f'<span class="data-value">Purchased: {fmt_currency(holding.purchase_price)}</span></div>'
                    f'<div class="data-row"><span class="data-label"></span>'
                    f'<span class="data-value">Value: {fmt_currency(holding.current_value)}</span></div>',
                    unsafe_allow_html=True)
            st.session_state.capital_panel_state["prev_nav"] = team_state.nav

        # Portfolio table
        if team_state.properties:
            import pandas as pd
            portfolio_df = pd.DataFrame([
                {
                    "Property": h.property_id,
                    "Purchase": f"${h.purchase_price:.2f}M",
                    "Value": f"${h.current_value:.2f}M",
                    "NOI": f"${h.current_noi:.2f}M",
                    "Type": h.property_type,
                    "Submarket": h.submarket,
                }
                for h in team_state.properties.values()
            ])
            st.dataframe(portfolio_df, use_container_width=True, hide_index=True)

        # Reflection question
        st.markdown('<div class="reflection-box">', unsafe_allow_html=True)
        st.markdown('<h4 style="margin:0 0 8px 0;font-size:0.9em;">Round Reflection</h4>')
        st.markdown('<p style="font-size:0.85em;color:#4a5568;">What will you change next round?</p>', unsafe_allow_html=True)
        reflection = st.radio(
            "",
            ["Trust model more", "Trust model less", "Bid more aggressively",
             "Bid less aggressively", "Use less leverage", "Use more leverage", "No change"],
            horizontal=True, key=f"reflection_r{gm.current_round}"
        )
        st.session_state.round_reflection[gm.current_round] = reflection
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button(f"CONTINUE TO ROUND {gm.current_round + 2}" if gm.current_round + 1 < gm.config.total_rounds else "CONTINUE TO FINAL RESULTS",
                      use_container_width=True, type="primary"):
            try:
                gm.advance_round()
                st.session_state.round_decision = {}
                st.session_state.capital_panel_state["prev_nav"] = team_state.nav
                if gm.current_round >= gm.config.total_rounds - 1 and gm.round_state != RoundState.NOT_STARTED:
                    pass
                st.rerun()
            except RuntimeError as e:
                if "complete" in str(e).lower():
                    gm.game_complete = True
                    st.session_state.game_complete = True
                    st.rerun()
                else:
                    st.error(str(e))

    else:
        st.info("Game in progress. Return to the main page for status.")

# ── HIDE SIDEBAR DURING GAME ──
if st.session_state.game_started:
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

# ── SIDEBAR (pre-game only) ──
with st.sidebar:
    st.markdown('<div class="page-header" style="border-bottom:1px solid #e2e8f0;margin-bottom:12px;padding:8px 0 4px 0;">'
                '<h1 style="font-size:1.1em;">CRE Investment Committee</h1>'
                '<p style="font-size:0.75em;color:#718096;">REAL 605 · Chapman</p>'
                '</div>', unsafe_allow_html=True)

    if st.session_state.game_started and st.session_state.game_manager:
        # Only show sidebar content after game ends (or during setup)
        gm = st.session_state.game_manager
        team_name = st.session_state.current_team
        team_state = gm.teams.get(team_name)
        if team_state:
            st.metric("Your Fund NAV", f"${team_state.nav:.2f}M")
            st.metric("Properties", len(team_state.properties))
        st.caption(f"Round {gm.current_round + 1 if gm.current_round >= 0 else 'Practice'} of {gm.config.total_rounds}")
        st.caption(f"State: {gm.round_state.value.replace('_', ' ').title()}")
        st.markdown("---")

        if st.button("Reset Game"):
            st.session_state.game_manager = None
            st.session_state.game_started = False
            st.session_state.game_complete = False
            st.rerun()

        st.markdown("---")
        st.markdown('<div style="font-size:0.75em;color:#718096;">Demo mode: ' + str(st.session_state.demo_mode) + '</div>')
    else:
        st.caption("Start a simulation to see details")
