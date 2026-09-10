from __future__ import annotations

import streamlit as st
import pandas as pd


def show():
    st.title("8 · Deal Room")
    st.caption("Underwrite each property. Do not show the simulated future outcome here.")

    from src.data.duckdb import DuckDBBackend
    from src.finance.calculations import underwrite

    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties")
    finally:
        db.close()

    st.markdown("---")
    st.subheader("Candidate properties")
    st.dataframe(
        props[["property_id", "property_name", "type", "submarket", "size_sf", "units", "asking_price", "current_noi", "going_in_cap", "occupancy", "walt", "market_rent", "in_place_rent", "tenant_concentration", "debt_rate", "amortization_years", "max_ltv", "property_quality", "lease_expiry_profile", "primary_risk"]].assign(
            asking_price=lambda d: d["asking_price"].round(2),
            current_noi=lambda d: d["current_noi"].round(3),
            going_in_cap=lambda d: (d["going_in_cap"] * 100).round(2),
            occupancy=lambda d: (d["occupancy"] * 100).round(1),
            market_rent=lambda d: d["market_rent"].round(2),
            in_place_rent=lambda d: d["in_place_rent"].round(2),
            debt_rate=lambda d: (d["debt_rate"] * 100).round(2),
            max_ltv=lambda d: (d["max_ltv"] * 100).round(0),
        ).rename(columns={
            "asking_price": "Ask ($MM)",
            "current_noi": "Current NOI ($MM)",
            "going_in_cap": "Going-in Cap (%)",
            "occupancy": "Occupancy (%)",
            "market_rent": "Market Rent",
            "in_place_rent": "In-Place Rent",
            "debt_rate": "Debt Rate (%)",
            "max_ltv": "Max LTV (%)",
            "property_quality": "Quality (0-1)",
            "primary_risk": "Primary Risk",
        })[["property_id", "property_name", "type", "submarket", "Ask ($MM)", "Current NOI ($MM)", "Going-in Cap (%)", "Occupancy (%)", "WALT", "Market Rent", "In-Place Rent", "Tenant Concentration", "Debt Rate (%)", "Amort. (yrs)", "Max LTV (%)", "Quality (0-1)", "Primary Risk"]],
        hide_index=True,
        use_container_width=True,
        height=420,
    )

    st.markdown("---")
    st.subheader("Select a property to underwrite")
    pids = props["property_id"].tolist()
    pid = st.selectbox("Property", pids, index=0)
    p = props[props["property_id"] == pid].iloc[0]

    st.markdown("---")
    st.subheader(f"{p['property_name']} ({p['property_id']})")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Asking price", f"${p['asking_price']:.2f}M")
        st.metric("Current NOI", f"${p['current_noi']:.3f}M")
        st.metric("Going-in cap", f"{p['going_in_cap']:.2%}")
        st.metric("Occupancy", f"{p['occupancy']:.1%}")
        st.metric("WALT", f"{p['walt']:.1f} yrs")
        st.metric("Quality", f"{p['property_quality']:.2f}")
        st.metric("Max LTV", f"{p['max_ltv']:.0%}")
    with col2:
        st.metric("Market rent", p["market_rent"], help=p.get("lease_expiry_profile"))
        st.metric("In-place rent", p["in_place_rent"])
        st.metric("Tenant concentration", f"{p['tenant_concentration']:.2f}")
        st.metric("Debt rate", f"{p['debt_rate']:.2%}")
        st.metric("Amortization", f"{p['amortization_years']} yrs")
        st.metric("Capex need", f"${p['capex_need']:.3f}M")
        st.metric("Size (SF)", f"{p['size_sf']:,}")
    st.info(f"Primary risk: {p['primary_risk']}")

    st.markdown("---")
    st.subheader("Your underwriting assumptions")
    decision = st.radio("Decision", ["BUY", "PASS"], horizontal=True, key=f"deal_{pid}_decision")
    if decision == "BUY":
        c1, c2, c3 = st.columns(3)
        with c1:
            bid = st.number_input("Bid ($MM)", min_value=0.0, max_value=None, value=float(p["asking_price"]), step=0.1, key=f"bid_{pid}")
            ltv_in = st.number_input("LTV (%)", min_value=0.0, max_value=100.0, value=min(p["max_ltv"] * 100, 60.0), step=1.0, key=f"ltv_{pid}")
            ltv = min(p["max_ltv"], max(0.0, ltv_in / 100.0))
        with c2:
            growth = st.number_input("1Y NOI growth forecast (%)", min_value=-50.0, max_value=50.0, value=2.0, step=0.1, key=f"growth_{pid}")
            exitcap_in = st.number_input("1Y exit cap forecast (%)", min_value=1.0, max_value=20.0, value=float(p["going_in_cap"] * 100), step=0.05, key=f"exitcap_{pid}")
            exitcap = max(0.001, exitcap_in / 100.0)
        with c3:
            confidence = st.number_input("Confidence (%)", min_value=0, max_value=100, value=60, step=5, key=f"conf_{pid}")
            prob_loss = st.number_input("Probability of loss (%)", min_value=0, max_value=100, value=25, step=5, key=f"ploss_{pid}")
        u = underwrite(
            asking_price=p["asking_price"],
            current_noi=p["current_noi"],
            debt_rate=p["debt_rate"],
            amortization_years=int(p["amortization_years"]),
            max_ltv=float(p["max_ltv"]),
            bid=bid,
            ltv_choice=ltv,
            noi_growth_forecast=growth / 100.0,
            exit_cap_forecast=exitcap,
        )
        st.markdown("---")
        st.subheader("Underwriting output")
        out = {
            "Equity required": f"${u.equity_required:.2f}M",
            "Loan amount": f"${u.loan_amount:.2f}M",
            "LTV": f"{u.ltv:.1%}",
            "Annual debt service": f"${u.annual_debt_service:.3f}M",
            "Current DSCR": f"{u.dscr:.2f}x" if u.dscr != float("inf") else "n/a",
            "Debt yield": f"{u.debt_yield:.2%}" if u.debt_yield != float("inf") else "n/a",
            "Predicted Yr1 NOI": f"${u.predicted_noi:.3f}M",
            "Predicted Yr1 value": f"${u.predicted_value:.2f}M",
            "Predicted equity value": f"${u.predicted_equity_value:.2f}M",
            "Predicted cash flow": f"${u.predicted_cash_flow:.3f}M",
            "Predicted 1Y equity return": f"{u.predicted_levered_return:.1%}",
        }
        st.dataframe(out, hide_index=True, use_container_width=True)
        st.session_state[f"underwriting_{pid}"] = {
            "decision": decision, "bid": bid, "ltv": ltv, "noi_growth_forecast": growth / 100.0,
            "exit_cap_forecast": exitcap, "confidence": confidence, "probability_of_loss": prob_loss / 100.0,
            "underwriting": u,
        }
    else:
        st.info("You passed on this property. Set a bid on another property to underwrite it.")
        st.session_state[f"underwriting_{pid}"] = {"decision": "PASS"}

    st.markdown("---")
    st.subheader("Side-by-side comparison (selected)")
    compare = st.multiselect("Compare properties", pids, default=[pids[0], pids[min(1, len(pids)-1)]], key="deal_compare")
    if compare:
        sub = props[props["property_id"].isin(compare)]
        st.dataframe(sub[["property_id", "property_name", "type", "submarket", "asking_price", "current_noi", "going_in_cap", "occupancy", "walt", "tenant_concentration", "debt_rate", "max_ltv"]].assign(
            asking_price=lambda d: d["asking_price"].round(2),
            current_noi=lambda d: d["current_noi"].round(3),
            going_in_cap=lambda d: (d["going_in_cap"] * 100).round(2),
            occupancy=lambda d: (d["occupancy"] * 100).round(1),
            debt_rate=lambda d: (d["debt_rate"] * 100).round(2),
            max_ltv=lambda d: (d["max_ltv"] * 100).round(0),
        ).rename(columns={
            "asking_price": "Ask ($MM)", "current_noi": "NOI ($MM)", "going_in_cap": "Cap (%)",
            "occupancy": "Occ (%)", "debt_rate": "Debt (%)", "max_ltv": "MaxLTV (%)",
        })[["property_id", "property_name", "type", "submarket", "Ask ($MM)", "NOI ($MM)", "Cap (%)", "Occ (%)", "WALT", "Tenant Concentration", "Debt (%)", "Amort. (yrs)", "MaxLTV (%)"]],
        hide_index=True, use_container_width=True)

    st.markdown("---")
    import pages.navigation as navigation
    st.page_link(navigation.page("decision"), label="→ Next: Investment Decision", use_container_width=True)
