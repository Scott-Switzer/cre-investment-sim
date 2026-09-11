from __future__ import annotations

import streamlit as st


def show():
    st.title("2 · Data Catalog")
    st.caption("All data sources, provenance, and download links.")

    st.markdown(
        """
This simulation uses multiple data sources, each with provenance metadata:
`source_name`, `source_url`, `observation_date`, `available_at`, `retrieved_at`, `data_type`, `is_synthetic`, `notes`.
"""
    )

    st.markdown("---")
    st.subheader("Data Sources")
    rows = [
        ("Orange County Parcels (OC GIS REST)", "Map_Layers/Parcels/FeatureServer/0", "Real parcel geometry, APN, address", "REAL PUBLIC DATA", "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0"),
        ("Orange County Tax/Assessment (OC TTC REST)", "Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0", "Assessed/tax value fields (ta, aiv, alv). NOT transaction market value.", "REAL PUBLIC DATA", "https://www.ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0"),
        ("CBRE Orange County Office Q2 2026", "CBRE market figures", "Office vacancy, asking rent", "REAL PUBLIC DATA", "https://www.cbre.com/insights/figures/orange-county-office-figures-q2-2026"),
        ("CBRE Orange County Industrial Q2 2026", "CBRE market figures", "Industrial vacancy, asking rent", "REAL PUBLIC DATA", "https://www.cbre.com/insights/figures/orange-county-industrial-figures-q2-2026"),
        ("CBRE Orange County Multifamily Q2 2026", "CBRE market figures", "Multifamily occupancy, average rent", "REAL PUBLIC DATA", "https://www.cbre.com/insights/figures/orange-county-multifamily-figures-q2-2026"),
        ("FRED / Federal Reserve H.15", "10-Year Treasury constant maturity", "Macro rate environment", "REAL PUBLIC DATA", "https://fred.stlouisfed.org/release/tables?eid=289&rid=18"),
        ("Census ACS (public-data sample)", "ACS 5-year tract/block-group variables", "Population, income, housing, commuting", "REAL PUBLIC DATA", "https://api.census.gov/data.html"),
        ("Census LEHD / LODES (public-data sample)", "Workplace Area Characteristics (WAC) proxy", "Employment by area, employment density", "REAL PUBLIC DATA", "https://lehd.ces.census.gov/data/"),
        ("Semipsynthetic CRE operating cases", "Deterministic generator", "Property NOI, asking price, rents, lease structure, outcomes", "SYNTHETIC TEACHING DATA", "https://github.com/chapman-real605/cre-sim"),
        ("Derived geospatial features", "Computed from parcel context + public anchors", "Employment density, distance to SNA/Irvine, census tract approx.", "DERIVED FEATURE", "https://github.com/chapman-real605/cre-sim"),
        ("Simulated future", "Pedagogical market engine", "Round outcomes (NOI growth, cap shifts, values, returns)", "SIMULATED FUTURE", "https://github.com/chapman-real605/cre-sim"),
    ]
    st.dataframe(
        {
            "Source name": [r[0] for r in rows],
            "Description": [r[2] for r in rows],
            "Data status": [r[3] for r in rows],
            "Source URL": [r[4] for r in rows],
        },
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("Known Limitations")
    st.markdown(
        "- OC parcel geometry and APN/address are real public data, but **assessed/tax value is not transaction market value**.\n"
        "- Census ACS and LODES are public-data samples cached for offline demo; in production they would be refreshed with `CENSUS_API_KEY`.\n"
        "- FRED macro series are a cached public-data sample; in production they would be refreshed with `FRED_API_KEY` and vintage-aware retrieval.\n"
        "- The property operating cases are **synthetic teaching data**, calibrated to public anchors, not real transactions.\n"
        "- The simulation does **not** claim to forecast the actual Orange County market; it is a pedagogical simulator.\n"
        "- Point-in-time correctness: a student's decision date is 2024-03-31, so data available only after that date is excluded unless intentionally included as a leakage trap."
    )

    st.markdown("---")
    st.subheader("Download Raw Student Datasets")
    from src.data.duckdb import DuckDBBackend
    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties_student")
        st.download_button(
            "Download student property copy (CSV)",
            data=props.to_csv(index=False),
            file_name="real605_student_properties.csv",
            mime="text/csv",
            use_container_width=True,
        )
        anchors = db.query("SELECT * FROM market_anchors")
        st.download_button(
            "Download market anchors (CSV)",
            data=anchors.to_csv(index=False),
            file_name="real605_market_anchors.csv",
            mime="text/csv",
            use_container_width=True,
        )
        macro = db.query("SELECT * FROM macro_history")
        st.download_button(
            "Download macro history (CSV)",
            data=macro.to_csv(index=False),
            file_name="real605_macro_history.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("The student property copy is deliberately imperfect — see the Data Quality Challenge page.")
    finally:
        db.close()

    st.markdown("---")
    st.page_link("pages/data_quality.py", label="→ Next: Data Quality Challenge", icon="")
