from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import date
import csv

_NAV = None
_PROFESSOR_DEMO_STEPS = [
    ("1. Open Briefing", "briefing", "The student must understand the decision before seeing analysis. Note the decision date and available capital."),
    ("2. Data Quality Challenge", "data-quality", "Students receive an imperfect copy of the data with controlled issues plus a future-data leakage field."),
    ("3. Deal Room", "deals", "Review candidate acquisitions side by side. Do not reveal outcomes here."),
    ("4. Investment Decision", "decision", "Students commit BUY/PASS with bid, LTV, NOI and exit-cap forecasts, confidence, and thesis."),
    ("5. Professor Control", "professor", "Lock submissions, advance the round, then reveal results."),
    ("6. Results / Debrief", "results", "Separate outcome quality from forecast, risk, decision, and process quality."),
]


def show():
    global _NAV
    if _NAV is None:
        import pages.navigation as _navigation
        _NAV = _navigation

    st.title("10 · Professor Control")
    st.caption("Instructor view: start game, select scenario, lock, advance, reveal, reset, view ground truth, decisions, score components, export.")

    state = get_state()
    if state.demo_mode:
        st.info("Demo mode active. This page is open for demonstration. In class, restrict access to instructors.")

    st.markdown("---")
    st.subheader("Game setup")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        scenario = st.selectbox("Scenario", ["Base Case", "Rate Shock", "Growth Rebound"], index=0, key="pc_scenario")
    with col2:
        decision_date = st.date_input("Decision date", value=state.decision_date or date(2024, 3, 31), key="pc_date")
    with col3:
        capital = st.number_input("Available capital ($MM)", min_value=0.0, value=state.available_capital_mm or 150.0, step=5.0, key="pc_capital")
    with col4:
        seed = st.number_input("Seed", min_value=0, value=20240331, step=1, key="pc_seed")

    if st.button("Start / restart game", type="primary", use_container_width=True):
        if state.game and state.game.started:
            st.warning("Restarting will clear current round progress.")
        from src.simulation.engine import create_game
        from src.utils.state import restart_demo
        game = create_game(seed=seed, count=30)
        game.start_game(scenario=scenario, decision_date=decision_date)
        state.game = game
        state.current_scenario = scenario
        state.decision_date = decision_date
        state.available_capital_mm = capital
        state.round_index = 0
        state.started = True
        state.locked = False
        state.revealed = False
        state.audit_log = []
        state.log("game started", scenario=scenario, seed=seed, decision_date=decision_date.isoformat())
        st.success(f"Game started. Scenario: {scenario}. Decision date: {decision_date.isoformat()}. Seed: {seed}.")

    st.markdown("---")
    st.subheader("Current round status")
    if not state.game:
        st.info("No game started yet.")
    else:
        cr = state.game.current_round()
        if cr is None:
            st.info("No rounds available.")
        else:
            st.markdown(f"**Round:** {cr.round_index + 1} of 3  ·  **Scenario:** {cr.scenario}  ·  **Decision date:** {cr.decision_date}")
            st.markdown(f"**Locked:** {'Yes' if cr.locked else 'No'}  ·  **Revealed:** {'Yes' if cr.revealed else 'No'}")
            st.markdown(f"**Decisions submitted:** {len(cr.decisions)}")
            st.markdown(f"**Resolutions:** {len(cr.resolutions)}")

            st.markdown("---")
            st.subheader("Round actions")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Lock round", use_container_width=True):
                    if not state.game:
                        st.error("No active game.")
                    else:
                        try:
                            state.game.lock_round()
                            state.locked = True
                            state.audit_log.append({"action": "lock", "round": cr.round_index, "when": str(date.today())})
                            st.success("Round locked. Students can no longer submit decisions.")
                        except RuntimeError as e:
                            st.error(str(e))
            with c2:
                if st.button("Reveal outcome", type="primary", use_container_width=True):
                    if not state.game:
                        st.error("No active game.")
                    else:
                        try:
                            state.game.reveal_round()
                            state.revealed = True
                            state.log("round revealed", round=cr.round_index)
                            st.success("Round revealed. Outcomes are now visible to the debrief page.")
                        except RuntimeError as e:
                            st.error(str(e))
            with c3:
                if st.button("Advance to next round", use_container_width=True):
                    if not state.game:
                        st.error("No active game.")
                    else:
                        try:
                            if not cr.locked:
                                st.error("Lock the round before advancing.")
                            else:
                                state.game.advance_round()
                                state.round_index = state.game.round_index
                                state.locked = False
                                state.revealed = False
                                state.log("advanced to round", round=state.round_index)
                                st.success(f"Advanced to round {state.round_index + 1}.")
                        except RuntimeError as e:
                            st.error(str(e))

            st.markdown("---")
            st.subheader("Reset demo")
            if st.button("Reset demo", type="secondary", use_container_width=True):
                from src.utils.state import restart_demo
                restart_demo()
                st.rerun()

    st.markdown("---")
    st.subheader("Ground truth (instructor only)")
    if state.game and state.game.current_round() and state.game.current_round().revealed:
        cr = state.game.current_round()
        rows = []
        for d in cr.decisions:
            res = cr.resolutions.get(d.property_id)
            rows.append({
                "property_id": d.property_id,
                "decision": d.decision,
                "bid": d.bid,
                "ltv": d.ltv,
                "noi_growth_forecast": d.noi_growth_forecast,
                "exit_cap_forecast": d.exit_cap_forecast,
                "actual_noi_growth": res.noi_growth_actual if res else None,
                "actual_cap_delta": res.cap_delta_actual if res else None,
                "exit_noi": res.exit_noi if res else None,
                "exit_cap": res.exit_cap if res else None,
                "exit_value": res.exit_value if res else None,
                "levered_return": res.levered_return if res else None,
                "unlevered_return": res.unlevered_return if res else None,
                "market_comment": res.market_comment if res else None,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Start and reveal a round to see ground truth here.")

    st.markdown("---")
    st.subheader("Student decisions log")
    if state.game:
        all_decisions = []
        for r in state.game.rounds:
            for d in r.decisions:
                all_decisions.append({
                    "round": r.round_index,
                    "property_id": d.property_id,
                    "decision": d.decision,
                    "bid": d.bid,
                    "ltv": d.ltv,
                    "noi_growth_forecast": d.noi_growth_forecast,
                    "exit_cap_forecast": d.exit_cap_forecast,
                    "confidence": d.confidence,
                    "probability_of_loss": d.probability_of_loss,
                    "thesis_preview": (d.investment_thesis or "")[:100],
                    "submitted_at": d.timestamp.isoformat(),
                    "locked": d.locked,
                })
        if all_decisions:
            st.dataframe(pd.DataFrame(all_decisions), hide_index=True, use_container_width=True)
            csv_data = pd.DataFrame(all_decisions).to_csv(index=False)
            st.download_button("Export decisions CSV", csv_data, file_name="real605_decisions.csv", mime="text/csv", use_container_width=True)
        else:
            st.info("No decisions recorded yet.")
    else:
        st.info("No game in progress.")

    st.markdown("---")
    st.subheader("Score components (summary)")
    if state.game and state.game.current_round() and state.game.current_round().revealed:
        cr = state.game.current_round()
        from src.scoring.metrics import scorecard
        rows = []
        for d in cr.decisions:
            res = cr.resolutions.get(d.property_id)
            if res is None:
                continue
            pp = None
            try:
                from src.data.duckdb import DuckDBBackend as DB
                db2 = DB()
                props = db2.query("SELECT * FROM properties WHERE property_id = :pid", {"pid": d.property_id})
                if len(props):
                    pp = props.iloc[0]
                db2.close()
            except Exception:
                pass
            if pp is None:
                continue
            sc = scorecard(
                round_index=cr.round_index,
                property_id=d.property_id,
                decision=d.decision,
                bid=d.bid, ltv=d.ltv,
                noi_growth_forecast=d.noi_growth_forecast, exit_cap_forecast=d.exit_cap_forecast,
                confidence=d.confidence, probability_of_loss=d.probability_of_loss,
                thesis=d.investment_thesis,
                actual_noi_growth=res.noi_growth_actual, actual_cap_delta=res.cap_delta_actual,
                actual_exit_noi=res.exit_noi, actual_exit_cap=res.exit_cap, actual_exit_value=res.exit_value,
                actual_levered_return=res.levered_return, actual_unlevered_return=res.unlevered_return,
                predicted_value=d.predicted_value, predicted_noi=d.predicted_noi,
                world_noi_growth=res.noi_growth_actual, world_cap_delta=res.cap_delta_actual,
                current_noi=pp["current_noi"], current_cap=pp["going_in_cap"], debt_rate=pp["debt_rate"],
                amortization_years=int(pp["amortization_years"]),
                required_return=0.08, min_dscr=1.2, max_ltv=float(pp["max_ltv"]),
                used_future_data=False, leakage_trap_hit=False,
            )
            rows.append({
                "property_id": d.property_id,
                "decision": d.decision,
                "outcome_score": sc.financial_score,
                "forecast_score": sc.forecast_score,
                "risk_score": sc.risk_score,
                "decision_score": sc.decision_score,
                "process_score": sc.process_score,
                "total_score": sc.total_score,
                "forecast_value_error": sc.details["forecast_value_error"],
                "actual_return": sc.details["actual_levered_return"],
                "brier_loss": sc.details["brier_loss"],
            })
        st.dataframe(pd.DataFrame(rows).round(3), hide_index=True, use_container_width=True)
        if rows:
            csv_data = pd.DataFrame(rows).to_csv(index=False)
            st.download_button("Export scores CSV", csv_data, file_name="real605_scores.csv", mime="text/csv", use_container_width=True)
    else:
        st.info("Start and reveal a round to see scores.")

    st.markdown("---")
    st.page_link(_NAV.page("results"), label="→ Next: Results / Debrief", use_container_width=True)

    st.markdown("---")
    st.subheader("START PROFESSOR DEMO")
    st.write(
        "This demo is pre-seeded with one complete game: a student investment committee briefing on **2024-03-31**,"
        " a pool of 30 candidate properties in Orange County, and one already-locked decision for a warehouse property "
        "(OC-INDU-01) under the **Base Case** scenario. Use the steps below to walk a 5–8 minute class demonstration "
        "from the investment committee brief through reveal and debrief without encountering any routing errors."
    )

    with st.expander("Demo walkthrough steps (read while presenting)"):
        for label, page_key, note in _PROFESSOR_DEMO_STEPS:
            st.page_link(_NAV.page(page_key), label=label, use_container_width=True)
            st.caption(note)

    st.markdown(" ")
    st.success("Demo ready. The sample decision is already locked. Start by opening the Briefing.")
