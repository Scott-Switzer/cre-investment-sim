from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, date


def show():
    st.title("9 · Investment Decision")
    st.caption("Commit to BUY/PASS with your assumptions. Then lock. No silent edits after lock.")

    from src.utils import get_state
    from src.data.duckdb import DuckDBBackend
    from src.simulation.engine import StudentDecision
    from src.utils.pit import build_student_snapshot

    state = get_state()
    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties")
        # Load any previously saved underwriting for the current round
        decisions = state.game.current_round().decisions if state.game and state.game.current_round() else []
    finally:
        db.close()

    st.markdown("---")
    st.subheader("Your pipeline decision")
    st.write(
        "For each property, record your **decision**, **bid**, **LTV**, **NOI growth forecast**, "
        "**exit cap forecast**, **confidence**, and **probability of loss**. Then write your **investment thesis** "
        "and **what would prove it wrong**."
    )

    if "round_decisions" not in st.session_state:
        st.session_state.round_decisions = {}
    rd = st.session_state.round_decisions

    for _, p in props.iterrows():
        pid = p["property_id"]
        prev = rd.get(pid, {})
        with st.expander(f"{p['property_name']} ({pid}) — {p['type']} · {p['submarket']}", expanded=(pid == props.iloc[0]["property_id"])):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                st.metric("Ask", f"${p['asking_price']:.2f}M")
                st.metric("NOI", f"${p['current_noi']:.3f}M")
                st.metric("Cap", f"{p['going_in_cap']:.2%}")
            with c2:
                st.markdown(f"**Occupancy** {p['occupancy']:.1%} · **WALT** {p['walt']:.1f} yrs · **Quality** {p['property_quality']:.2f}")
                st.markdown(f"**Tenant concentration** {p['tenant_concentration']:.2f} · **Debt rate** {p['debt_rate']:.2%} · **Max LTV** {p['max_ltv']:.0%}")
                st.markdown(f"**Risk:** {p['primary_risk']}")
            with c3:
                decision = st.radio("Decision", ["BUY", "PASS"], horizontal=True, key=f"dec_{pid}", index=0 if prev.get("decision") == "BUY" else 0)
            if decision == "BUY":
                st.markdown("---")
                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    bid = st.number_input("Bid ($MM)", min_value=0.0, value=float(p["asking_price"]), step=0.1, key=f"bid_{pid}")
                    ltv_in = st.number_input("LTV (%)", min_value=0.0, max_value=100.0, value=min(p["max_ltv"] * 100, 60.0), step=1.0, key=f"ltv_{pid}")
                    ltv = min(p["max_ltv"], max(0.0, ltv_in / 100.0))
                with cc2:
                    growth = st.number_input("NOI growth forecast (%)", min_value=-50.0, max_value=50.0, value=2.0, step=0.1, key=f"growth_{pid}")
                    exitcap_in = st.number_input("Exit cap forecast (%)", min_value=1.0, max_value=20.0, value=float(p["going_in_cap"] * 100), step=0.05, key=f"exitcap_{pid}")
                with cc3:
                    confidence = st.number_input("Confidence (%)", min_value=0, max_value=100, value=60, step=5, key=f"conf_{pid}")
                    prob_loss = st.number_input("Probability of loss (%)", min_value=0, max_value=100, value=25, step=5, key=f"ploss_{pid}")
                rd[pid] = {
                    "decision": decision, "bid": bid, "ltv": ltv, "noi_growth_forecast": growth / 100.0,
                    "exit_cap_forecast": exitcap_in / 100.0, "confidence": confidence / 100.0,
                    "probability_of_loss": prob_loss / 100.0,
                    "property_id": pid,
                }
            else:
                rd[pid] = {"decision": "PASS", "property_id": pid}

    st.markdown("---")
    st.subheader("Investment thesis (per property)")
    for _, p in props.iterrows():
        pid = p["property_id"]
        thesis = st.text_area(
            f"Thesis — {p['property_name']}",
            value=rd.get(pid, {}).get("thesis", ""),
            height=80,
            key=f"thesis_{pid}",
            placeholder="Example: BUY below $48M because OC industrial vacancy should stabilize; thesis fails if sublease space remains above 8% and rent growth turns negative.",
        )
        key_assumption = st.text_input(
            f"Key assumption — {p['property_name']}",
            value=rd.get(pid, {}).get("key_assumption", ""),
            key=f"ka_{pid}",
            placeholder="e.g., In-place rents are market; no major tenant departures this quarter.",
        )
        falsification = st.text_input(
            f"What would prove this thesis wrong? — {p['property_name']}",
            value=rd.get(pid, {}).get("falsification_test", ""),
            key=f"fw_{pid}",
            placeholder="e.g., Vacancy rises above 9% OR a anchor tenant gives notice; cap rates expand more than 25 bps.",
        )
        rd[pid]["thesis"] = thesis
        rd[pid]["key_assumption"] = key_assumption
        rd[pid]["falsification_test"] = falsification

    st.markdown("---")
    st.subheader("Submit decision for this round")
    if st.button("Submit decision (saves to round)", type="primary", use_container_width=True):
        if not state.game or not state.game.current_round():
            st.error("No active game round. Use Professor Control to start a game.")
            return
        cr = state.game.current_round()
        if cr.locked:
            st.error("This round is locked. You cannot submit new decisions.")
            return
        from src.utils.pit import build_student_snapshot, assert_point_in_time
        snap = build_student_snapshot(state.decision_date, seed=20240331, count=30, include_leakage_field=False)
        try:
            assert_point_in_time(snap, state.decision_date, expect_leakage_field_absent=True)
        except AssertionError as e:
            st.error(f"Point-in-time check failed: {e}")
            return
        locked = True
        for pid, d in rd.items():
            if d.get("decision") == "BUY":
                u = st.session_state.get(f"underwriting_{pid}", {}).get("underwriting")
                if u is None:
                    from src.finance.calculations import underwrite as uw
                    pp = props[props["property_id"] == pid].iloc[0]
                    u = uw(
                        asking_price=pp["asking_price"], current_noi=pp["current_noi"], debt_rate=pp["debt_rate"],
                        amortization_years=int(pp["amortization_years"]), max_ltv=float(pp["max_ltv"]),
                        bid=d["bid"], ltv_choice=d["ltv"], noi_growth_forecast=d["noi_growth_forecast"],
                        exit_cap_forecast=d["exit_cap_forecast"],
                    )
                    st.session_state[f"underwriting_{pid}"] = {"underwriting": u}
                pred_val = u.predicted_value if u else None
                pred_noi = u.predicted_noi if u else None
            else:
                pred_val = None
                pred_noi = None
            dec = StudentDecision(
                decision_id=f"DEC-{state.decision_date.isoformat()}-{pid}",
                round_index=cr.round_index,
                timestamp=datetime.now(),
                property_id=pid,
                decision=d.get("decision", "PASS"),
                bid=d.get("bid", 0.0),
                ltv=d.get("ltv", 0.0),
                noi_growth_forecast=d.get("noi_growth_forecast", 0.0),
                exit_cap_forecast=d.get("exit_cap_forecast", 0.0),
                confidence=d.get("confidence", 0.0),
                probability_of_loss=d.get("probability_of_loss"),
                investment_thesis=d.get("thesis", ""),
                key_assumption=d.get("key_assumption", ""),
                falsification_test=d.get("falsification_test", ""),
                model_name=None, model_version=None,
                predicted_value=pred_val,
                predicted_noi=pred_noi,
                lock_ts=datetime.now(),
            )
            state.game.add_decision(dec)
            state.log("decision submitted", property_id=pid, decision=dec.decision, bid=d.get("bid"))
        st.success(f"Decision submitted for round {cr.round_index}. The round is now locked. Go to Professor Control to reveal outcomes.")
        st.session_state.after_submit = True

    st.markdown("---")
    st.subheader("Decision journal (current round)")
    if state.game and state.game.current_round():
        cr = state.game.current_round()
        if cr.decisions:
            rows = []
            for d in cr.decisions:
                rows.append({
                    "property_id": d.property_id,
                    "decision": d.decision,
                    "bid": d.bid,
                    "ltv": d.ltv,
                    "noi_growth_forecast": d.noi_growth_forecast,
                    "exit_cap_forecast": d.exit_cap_forecast,
                    "confidence": d.confidence,
                    "probability_of_loss": d.probability_of_loss,
                    "thesis_preview": (d.investment_thesis or "")[:120],
                    "locked": d.locked,
                    "submitted_at": d.timestamp,
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("No decisions submitted yet for this round.")
    else:
        st.info("Start a game from Professor Control to begin recording decisions.")

    st.markdown("---")
    import pages.navigation as navigation
    st.page_link(navigation.page("professor"), label="→ Next: Professor Control", use_container_width=True)
