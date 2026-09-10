"""
REAL 605 CRE Investment Committee Simulation — Streamlit app.

Uses st.Page + st.navigation with stable ASCII url_path values.
Instructor controls and demo state remain in the sidebar.
"""

from __future__ import annotations

import streamlit as st
from pathlib import Path
from datetime import date

import pages

from src.utils.state import AppState, build_demo_state
from src.utils.config import load_app_config
from src.simulation.engine import SCENARIOS


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
    st.session_state.app_state = build_demo_state(seed=20240331)
    st.session_state.app_state.log("demo restarted")
    st.success("Demo reset. Ready to play.")


PAGES = {
    "home": st.Page(pages.home.show, title="Home"),
    "briefing": st.Page(pages.briefing.show, title="Briefing", url_path="briefing"),
    "data": st.Page(pages.data_catalog.show, title="Data Catalog", url_path="data"),
    "data-quality": st.Page(pages.data_quality.show, title="Data Quality Challenge", url_path="data-quality"),
    "market": st.Page(pages.market_explorer.show, title="Market Explorer", url_path="market"),
    "sql": st.Page(pages.sql_lab.show, title="SQL Lab", url_path="sql"),
    "valuation": st.Page(pages.valuation_lab.show, title="Valuation Lab", url_path="valuation"),
    "geo": st.Page(pages.geospatial.show, title="Geospatial View", url_path="geo"),
    "deals": st.Page(pages.deal_room.show, title="Deal Room", url_path="deals"),
    "decision": st.Page(pages.investment_decision.show, title="Investment Decision", url_path="decision"),
    "professor": st.Page(pages.professor_control.show, title="Professor Control", url_path="professor"),
    "results": st.Page(pages.results.show, title="Results / Debrief", url_path="results"),
    "methodology": st.Page(pages.provenance.show, title="Provenance & Methodology", url_path="methodology"),
}

st.title("REAL 605 CRE Investment Committee Simulation")
st.caption("Chapman University · REAL 605 Real Estate Analytics · Prof. Tim Frenzel")
st.caption("Semipsynthetic teaching app · real public data where possible")

st.sidebar.title("REAL 605 CRE Simulation")
st.sidebar.markdown("Chapman University · REAL 605 Real Estate Analytics · Prof. Tim Frenzel")
st.sidebar.caption("Semipsynthetic teaching app · real public data where possible")

st.sidebar.markdown("---")
st.sidebar.subheader("Instructor Controls")
demo = st.sidebar.checkbox("Demo mode", value=True, help="Local demo mode. In class, use instructor controls.")
state = get_state()
if demo:
    state.demo_mode = True
    state.instructor_mode = True

st.sidebar.markdown("---")
st.sidebar.subheader("Scenario")
scenario = st.sidebar.selectbox("Market scenario", SCENARIOS, index=0, key="sidebar_scenario")
state.current_scenario = scenario

st.sidebar.markdown("---")
st.sidebar.subheader("Game")
if st.sidebar.button("Restart demo"):
    restart_demo()
    st.rerun()

st.sidebar.caption(f"Decision date: {DECISION_DATE}")
st.sidebar.caption(f"Available capital: ${AVAILABLE_CAPITAL:.0f}M")

st.sidebar.markdown("---")
st.sidebar.caption("Real public data · Synthetic teaching data · Derived features · Simulated future")

pg = st.navigation(list(PAGES.values()), position="sidebar")
pg.run()
