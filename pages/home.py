from __future__ import annotations

import streamlit as st


def show():
    st.title("REAL 605 — CRE Investment Committee Simulation")
    st.caption("Chapman University · REAL 605 Real Estate Analytics · Prof. Tim Frenzel")

    st.markdown(
        """
This is a classroom simulation in which **doing the analytics provides an advantage**.

You are an investment team allocating commercial real estate capital in Orange County.
Review market conditions, analyze imperfect point-in-time data, underwrite candidate acquisitions,
commit to an investment decision, lock it, and then the simulated market resolves.
The debrief separates outcome quality from forecast quality, risk discipline, decision quality,
and process/data integrity.
"""
    )

    st.markdown("## How a round works")
    st.markdown(
        """
1. **Briefing** — understand the decision before seeing the analysis.
2. **Market + property data** — explore real public anchors and semipsynthetic property cases.
3. **Analysis** — SQL, descriptive stats, valuation benchmarks, baseline regression, geospatial.
4. **Investment decision** — BUY/PASS, bid, LTV, NOI growth forecast, exit cap forecast, confidence, thesis.
5. **Lock decision** — submit timestamped; no silent editing after lock.
6. **Market resolution** — instructor reveals the scenario; the engine resolves outcomes.
7. **Portfolio update** — aggregate financial results.
8. **Debrief** — outcome, forecast, risk, decision, and process quality.
9. **Next round** — up to 3 rounds per game.
"""
    )

    st.markdown("## Data honesty")
    st.markdown(
        """
- **REAL PUBLIC DATA** — Orange County parcel/APN/address context, OC tax/assessment attributes, Census ACS/LODES public-data samples, FRED macro series.
- **SYNTHETIC TEACHING DATA** — property operating cases (NOI, asking price, rents, lease structure, outcomes). Calibrated to OC Q2 2026 public market anchors.
- **DERIVED FEATURE** — employment density, distance to airport/employment center, census tract approximations.
- **SIMULATED FUTURE** — round outcomes driven by a pedagogical simulator, not a claim about the actual Orange County market.

Every table and column carries provenance metadata: `source_name`, `source_url`, `observation_date`, `available_at`, `retrieved_at`, `data_type`, `is_synthetic`, `notes`.
"""
    )

    st.markdown("## Where to start")
    import pages.navigation as navigation
    st.page_link(navigation.page("briefing"), label="1 · Briefing — understand the decision", use_container_width=True)
    st.page_link(navigation.page("data-quality"), label="2 · Data Quality Challenge — your (imperfect) data", use_container_width=True)
    st.page_link(navigation.page("professor"), label="3 · Professor Control — start the demo", use_container_width=True)
    st.markdown(" ")
    st.markdown(
        """
**Demo mode**: the app is preloaded with one prepared game, 30 candidate properties, 3 market scenarios,
a starting portfolio/capital balance, market data, maps, deal room, one completed sample decision,
professor controls, debrief, and a provenance page. Full demonstration is possible in under 10 minutes.
"""
    )
    st.page_link(navigation.page("professor"), label="Skip ahead to Professor Control", use_container_width=True)


if __name__ == "__main__":
    show()
