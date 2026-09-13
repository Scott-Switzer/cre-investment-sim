from __future__ import annotations

import streamlit as st
import pandas as pd

from src.utils.state import get_state


def show():
    st.title("11 · Results / Debrief")
    st.caption("What happened financially; how accurate the forecasts were; whether risk discipline held; whether the decision was good; and whether point-in-time data was used cleanly.")

    state = get_state()
    if not state.game or not state.game.current_round() or not state.game.current_round().revealed:
        st.info("No revealed round to debrief yet. Go to Professor Control, start a game, submit decisions, lock, and reveal.")
        return

    cr = state.game.current_round()
    st.subheader(f"Round {cr.round_index + 1} · {cr.scenario} · decision date {cr.decision_date.isoformat()}")

    st.markdown("---")
    st.subheader("Portfolio snapshot")
    if state.game:
        pos = []
        total_asset = 0.0
        total_debt = 0.0
        total_noi = 0.0
        total_ds = 0.0
        for d in cr.decisions:
            res = cr.resolutions.get(d.property_id)
            if res is None:
                continue
            pp = None
            try:
                from src.data.duckdb import DuckDBBackend as DB
                db = DB()
                p = db.query("SELECT * FROM properties WHERE property_id = ?", {"parameter": d.property_id})
                if len(p):
                    pp = p.iloc[0]
                db.close()
            except Exception:
                pass
            if pp is None:
                continue
            from src.finance.calculations import annual_debt_service as ads
            loan = d.bid * d.ltv
            equity = d.bid - loan
            ds = ads(loan, d.debt_rate, 25) if loan > 0 else 0
            pos.append({
                "property_id": d.property_id,
                "property_name": pp["property_name"],
                "type": pp["type"],
                "submarket": pp["submarket"],
                "decision": d.decision,
                "bid": d.bid,
                "equity": equity,
                "loan": loan,
                "ltv": d.ltv,
                "dscr": (pp["current_noi"] / ds) if ds > 0 else float("inf"),
                "exit_value": res.exit_value,
                "exit_noi": res.exit_noi,
                "levered_return": res.levered_return,
                "unlevered_return": res.unlevered_return,
                "market_comment": res.market_comment,
            })
            if d.decision == "BUY":
                total_asset += res.exit_value
                total_debt += loan
                total_noi += res.exit_noi
                total_ds += ds
        if pos:
            dfp = pd.DataFrame(pos)
            st.dataframe(dfp, hide_index=True, use_container_width=True)
            st.metric("Total asset value", f"${total_asset:.2f}M")
            st.metric("Total debt", f"${total_debt:.2f}M")
            st.metric("Portfolio LTV", f"{total_debt/total_asset:.1%}" if total_asset > 0 else "n/a")
            st.metric("Portfolio DSCR", f"{total_noi/total_ds:.2f}x" if total_ds > 0 else "n/a")
        else:
            st.info("No resolved positions for this round.")

    st.markdown("---")
    st.subheader("Debrief per property")
    rows = []
    for d in cr.decisions:
        res = cr.resolutions.get(d.property_id)
        if res is None:
            continue
        pp = None
        try:
            from src.data.duckdb import DuckDBBackend as DB
            db = DB()
            p = db.query("SELECT * FROM properties WHERE property_id = ?", {"parameter": d.property_id})
            if len(p):
                pp = p.iloc[0]
            db.close()
        except Exception:
            pass
        if pp is None:
            continue
        from src.scoring.metrics import scorecard
        sc = scorecard(
            round_index=cr.round_index, property_id=d.property_id, decision=d.decision,
            bid=d.bid, ltv=d.ltv, noi_growth_forecast=d.noi_growth_forecast, exit_cap_forecast=d.exit_cap_forecast,
            confidence=d.confidence, probability_of_loss=d.probability_of_loss, thesis=d.investment_thesis,
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
            "thesis": sc.details["thesis"],
            "actual_noi_growth": res.noi_growth_actual,
            "actual_exit_cap": res.exit_cap,
            "actual_exit_value": res.exit_value,
            "actual_levered_return": res.levered_return,
            "predicted_value": d.predicted_value,
            "predicted_noi": d.predicted_noi,
            "forecast_value_error": sc.details["forecast_value_error"],
            "forecast_noi_error": sc.details["forecast_noi_error"],
            "brier_loss": sc.details["brier_loss"],
            "dscr": sc.details["dscr"],
            "ltv": sc.details["ltv"],
            "expected_levered_return": sc.details["expected_levered_return"],
            "outcome_score": sc.financial_score,
            "forecast_score": sc.forecast_score,
            "risk_score": sc.risk_score,
            "decision_score": sc.decision_score,
            "process_score": sc.process_score,
            "total_score": sc.total_score,
            "market_comment": res.market_comment,
        })
    if rows:
        dfr = pd.DataFrame(rows)
        st.dataframe(dfr, hide_index=True, use_container_width=True)
    else:
        st.info("No resolved positions.")

    st.markdown("---")
    st.subheader("Score breakdown (per the configured weights)")
    w = {"financial": 0.35, "forecast": 0.25, "risk": 0.15, "decision": 0.15, "process": 0.10}
    st.dataframe({"component": ["Financial / outcome", "Forecast accuracy", "Risk discipline", "Decision quality", "Process / data integrity", "TOTAL"],
                  "weight": [0.35, 0.25, 0.15, 0.15, 0.10, 1.00],
                  "what it measures": [
                      "Realized financial performance vs required return",
                      "Accuracy of value/NOI/cap forecasts (MAE/MAPE + Brier for probability of loss)",
                      "Staying inside LTV, DSCR, concentration limits",
                      "Was the decision reasonable given info available BEFORE realization (expected outcome, not luck)",
                      "Point-in-time data use; no leakage",
                      "Weighted composite",
                  ]}, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Debrief questions")
    st.markdown(
        """
1. **Outcome quality** — What actually happened financially? Compare realized return to the hurdle.
2. **Forecast quality** — How accurate were your NOI, cap-rate, and property-value forecasts? Where did you err?
3. **Risk quality** — Did you stay inside leverage, DSCR, and concentration constraints? Would a lender have accepted your structure?
4. **Decision quality** — Was your decision reasonable given the information available at the decision point? How did your expected return compare to the realized outcome?
5. **Process quality** — Did you use only point-in-time information? Did you avoid the leakage field?
6. **Thesis check** — What in the resolution falsified or supported your thesis?
7. ** luck vs skill** — Separately score outcome (what happened) and decision quality (what was a good decision ex ante). Did you get lucky?
"""
    )
    for _, r in dfr.iterrows() if rows else []:
        st.markdown(f"**{r['property_id']}** — thesis: {r['thesis']}")
        st.caption(f"Market: {r['market_comment']}. Actual NOI growth {r['actual_noi_growth']:.1%}, exit cap {r['actual_exit_cap']:.2%}, exit value ${r['actual_exit_value']:.2f}M, levered return {r['actual_levered_return']:.1%}, forecast value error {r['forecast_value_error']:.1%}. Expected levered return {r['expected_levered_return']:.1%}. Total score {r['total_score']:.1f}.")
        st.markdown("---")

    import pages.navigation as navigation
    st.page_link(navigation.page("methodology"), label="→ Appendix: Provenance & Methodology", use_container_width=True)


if __name__ == "__main__":
    show()
