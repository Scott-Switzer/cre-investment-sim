from __future__ import annotations

import streamlit as st
import pandas as pd


def show():
    st.title("3 · Data Quality Challenge")
    st.caption("A deliberately imperfect student copy of the data. Clean it yourself.")

    st.markdown(
        """
You receive a **student copy** of the property dataset. It is derived from the pristine instructor truth
table but has a small, reproducible set of issues injected.

The application does **not** automatically fix everything for you. Your job is to identify and handle them.

The injected issues are:
"""
    )
    manifest = st.session_state.get("dq_manifest")
    if manifest is None:
        from src.data.data_quality import DATA_QUALITY_MANIFEST, student_copy_triaged
        manifest = student_copy_triaged()
        st.session_state.dq_manifest = manifest
    for item in manifest["manifest"]:
        with st.expander(f"{item['issue_id']}: {item['description']}"):
            st.json(item, expanded=False)

    st.warning(
        f"Leakage trap: the field `{manifest['leakage_field']}` is available **only after the decision date** "
        f"({manifest['decision_date']}). Using it for a 2024-03-31 decision is leakage. You should spot it and exclude it."
    )

    st.markdown("---")
    st.subheader("Student copy (raw, imperfect)")
    from src.data.duckdb import DuckDBBackend
    db = DuckDBBackend()
    try:
        df = db.query("SELECT * FROM properties_student")
        st.dataframe(df, use_container_width=True, height=420)
        st.download_button(
            "Download raw student copy (CSV)",
            data=df.to_csv(index=False),
            file_name="real605_student_properties_raw.csv",
            mime="text/csv",
            use_container_width=True,
        )
    finally:
        db.close()

    st.markdown("---")
    st.subheader("Your cleaned copy (optional)")
    st.write("Upload your cleaned CSV or edit in place. The app does not auto-grade cleaning correctness in this MVP beyond the PIT tests.")
    uploaded = st.file_uploader("Upload cleaned student copy (CSV)", type=["csv"])
    if uploaded is not None:
        cleaned = pd.read_csv(uploaded)
        st.dataframe(cleaned, use_container_width=True, height=200)
        st.success("Uploaded. In a full version this would feed your analysis and decision steps.")

    st.markdown("---")
    st.subheader("Instructor truth dataset (for comparison)")
    st.caption("Available to the instructor only. Students should not have this.")
    from src.data.duckdb import DuckDBBackend as DB2
    db2 = DB2()
    try:
        truth = db2.query("SELECT * FROM properties")
        st.dataframe(truth[["property_id", "property_name", "type", "submarket", "asking_price", "current_noi", "going_in_cap", "occupancy", "walt", "debt_rate", "max_ltv"]].head(10), use_container_width=True, height=200)
    finally:
        db2.close()

    st.markdown("---")
    st.page_link("pages/market_explorer.py", label="→ Next: Market Explorer", icon="")
