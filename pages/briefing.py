from __future__ import annotations

import streamlit as st
from datetime import date

from src.utils.state import get_state
from src.utils.config import load_app_config
from src.data.market_anchors import build_market_anchors


def show():
    st.title("1 · Briefing — Investment Committee Request")
    st.caption("Understand the decision before you see the analysis.")

    state = get_state()
    cfg = load_app_config()
    mandate = cfg.get("app", {}).get("mandate", {})
    decision_date = state.decision_date or date(2024, 3, 31)
    capital = state.available_capital_mm or 150.0

    st.markdown("---")
    st.subheader("The Situation")
    st.write(
        f"You are an investment team at a small Orange County CRE fund. It is **{decision_date.isoformat()}**. "
        f"The committee has authorized up to **${capital:.0f}M** of equity to deploy across a pipeline of "
        f"acquisition candidates. You may buy more than one property, but you must stay inside the fund's "
        f"mandate and concentration limits. One round = one quarter. The game has 3 rounds."
    )

    st.markdown("---")
    st.subheader("Investment Mandate")
    m = mandate or {}
    st.dataframe(
        {
            "Parameter": ["Available capital", "Required return (hurdle)", "Maximum LTV", "Minimum DSCR",
                          "Max type concentration", "Max submarket concentration", "Rounds", "Decision date"],
            "Value": [
                f"${capital:.0f}M",
                f"{m.get('required_return', 0.08):.1%}",
                f"{m.get('max_ltv', 0.70):.0%}",
                f"{m.get('min_dscr', 1.20):.2f}x",
                f"{m.get('max_type_concentration', 0.45):.0%}",
                f"{m.get('max_submarket_concentration', 0.40):.0%}",
                "3",
                decision_date.isoformat(),
            ],
        },
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("Your Task")
    st.write(
        "For each candidate property, decide: **BUY or PASS**. If you BUY, specify a **bid**, **LTV**, "
        "**NOI growth forecast**, **exit cap forecast**, **confidence**, and an **investment thesis** that "
        "includes 'what would prove this thesis wrong?'"
    )
    st.info(
        "You will not see the simulated future outcome while you decide. The professor reveals the "
        "scenario only after submissions are locked."
    )

    st.markdown("---")
    st.subheader("Current Market Snapshot (public anchors)")
    anchors = build_market_anchors()
    # Select available columns
    available_cols = [col for col in ["market_metric", "property_type", "as_of", "value", "units", "source_name", "tag"] if col in anchors.columns]
    if available_cols:
        st.dataframe(anchors[available_cols].rename(columns={"tag": "data_status"}), hide_index=True, width="stretch")
    else:
        st.dataframe(anchors, hide_index=True, width="stretch")
    st.caption("REAL PUBLIC DATA — sourced from CBRE and FRED. Used as market anchors only.")

    st.markdown("---")
    st.subheader("Decision Alternatives")
    st.markdown(
        "- Acquire one or more properties at or below asking price.\n"
        "- Pass on the entire pipeline.\n"
        "- Overweight a property type/submarket — but you must respect concentration limits.\n"
        "- Underwrite conservatively (lower LTV, higher DSCR) vs aggressively."
    )

    st.markdown("---")
    st.subheader("Problem Framing (short response)")
    st.write("In one or two sentences, state the investment objective and what success looks like for this round.")
    obj = st.text_area(
        "Investment objective / problem framing",
        height=120,
        key="briefing_objective",
        placeholder="Example: Deploy capital into OC industrial and multifamily where going-in cap rates exceed the risk-free rate plus a real spread, while avoiding office where vacancy is elevated and lease-up risk is high. Success = realized levered return above 8% with DSCR above 1.20x and no single property type above 45% of portfolio value.",
    )
    if st.button("Save objective (demo)", use_container_width=True):
        state.save("briefing_objective", obj)
        state.log("briefing objective saved", objective_preview=obj[:200] if obj else None)
        st.success("Saved to your session.")

    import pages.navigation as navigation
    st.page_link(navigation.page("market"), label="→ Next: Market Explorer", use_container_width=True)
