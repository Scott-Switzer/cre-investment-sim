from __future__ import annotations

import streamlit as st


def show():
    from src.utils import get_state
    st.title("Appendix · Provenance & Methodology")
    st.caption("What is observed vs generated. How the simulator is calibrated. What the app does not claim.")

    st.markdown("---")
    st.subheader("Data honesty tags")
    st.dataframe({
        "Tag": ["REAL PUBLIC DATA", "SYNTHETIC TEACHING DATA", "DERIVED FEATURE", "SIMULATED FUTURE"],
        "Meaning": [
            "Observed public data (OC parcels, OC tax/assessment, CBRE anchors, FRED macro, Census ACS/LODES public samples).",
            "Transparent synthetic property operating cases calibrated to public anchors. NOT real transactions.",
            "Features computed from real parcel context and public anchors (employment density, distance to SNA/Irvine, census tract approx.).",
            "Round outcomes from a pedagogical market engine. Not a forecast of the actual Orange County market.",
        ],
    }, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Provenance fields")
    st.markdown(
        "Every table/column carries: `source_name`, `source_url`, `observation_date`, `available_at`, `retrieved_at`, `data_type`, `is_synthetic`, `notes`."
    )
    st.markdown("---")
    st.subheader("Methodology")
    st.markdown(
        """
**Market engine**
- A pedagogical simulator, not an econometric forecasting model.
- Hidden world state per round: employment growth, policy rate, unemployment, inflation, credit conditions, vacancy by property type, asking rent index by type, cap rate by type, new supply pressure.
- Scenarios (Base Case, Rate Shock, Growth Rebound) shift those variables in plausible directions anchored to OC public market conditions.
- Property outcomes respond to world state + idiosyncratic noise. All random outcomes are reproducible from a seed.
- The instructor chooses the scenario; an optional seeded stochastic mode is a future extension.

**Financial engine**
- Loan amount = price × LTV; equity = price − loan; annual debt service from standard amortizing mortgage math; DSCR = NOI / debt service; debt yield = NOI / loan; value = NOI / cap; levered return = (exit equity value + cash flow − equity invested) / equity invested; unlevered return = (exit value + cash flow − price) / price.
- Portfolio aggregation: cash, total asset value, debt, equity NAV, portfolio LTV, portfolio DSCR, type/submarket concentration, round and cumulative returns.

**Scoring**
- Configurable weights (financial 35%, forecast 25%, risk 15%, decision 15%, process 10%) stored in `config/scoring.yaml`.
- Forecast accuracy: value/NOI/cap MAPE (capped), Brier score for probability-of-loss.
- Risk discipline: DSCR and LTV relative to constraints.
- Decision quality: evaluated against the EXPECTED outcome from the hidden world state BEFORE realization, to avoid hindsight bias.
- Process: penalizes use of data not available at decision time and hitting the leakage trap.

**Point-in-time correctness**
- Every observation used for a decision must satisfy `available_at <= decision_timestamp`, unless intentionally included as a leakage trap.
- `build_student_snapshot(as_of_date)` returns only allowed information; `assert_point_in_time` tests this (see tests/test_pit.py).

**Reproducibility**
- Synthetic property generation and simulation outcomes are deterministic from a seed.
- Tests use fixed seeds.
"""
    )
    st.markdown("---")
    st.subheader("Limitations and what this does NOT do")
    st.markdown(
        """
- It does not claim to forecast the actual Orange County market.
- It does not perform the analytics FOR the students; doing the analytics provides an advantage.
- Synthetic property data is teaching data; it is not observed real-world financial information.
- Assessed/tax values from OC are NOT transaction market value.
- The property coordinates in the MVP are positioned at plausible submarket centers; real parcel geometry is available from OC GIS and would be overlaid in a fuller version.
- Employment density is a cached public-data sample proxy; real implementation would use Census LEHD/LODES WAC files.
- Census ACS and FRED are cached samples for offline demo; live retrieval requires `CENSUS_API_KEY` and/or `FRED_API_KEY`.
"""
    )
    import pages.navigation as navigation
    st.page_link(navigation.page("home"), label="← Back to Home", use_container_width=True)


if __name__ == "__main__":
    show()
