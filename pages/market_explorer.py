from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def show():
    st.title("4 · Market Explorer")
    st.caption("Descriptive summaries and charts. Enough to explore — not an answer card.")

    from src.data.duckdb import DuckDBBackend
    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties")
        anchors = db.query("SELECT * FROM market_anchors")
    finally:
        db.close()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Property type distribution")
        type_counts = props["type"].value_counts().reset_index()
        type_counts.columns = ["property_type", "count"]
        st.dataframe(type_counts, hide_index=True, use_container_width=True)
        fig = px.bar(type_counts, x="property_type", y="count", color="property_type", title="Candidate properties by type")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Going-in cap rate by type")
        fig = px.box(props, x="type", y="going_in_cap", color="type", title="Going-in cap rate distribution by property type")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Asking price distribution")
        fig = px.histogram(props, x="asking_price", color="type", title="Asking price ($MM) distribution")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("NOI distribution")
        fig = px.histogram(props, x="current_noi", color="type", title="Current NOI ($MM) distribution")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Market medians")
    med = props.groupby("type").agg(median_cap=("going_in_cap", "median"), median_noi=("current_noi", "median"), median_occ=("occupancy", "median"), median_price=("asking_price", "median")).reset_index()
    st.dataframe(med, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Rent / occupancy by type")
    fig = px.scatter(props, x="occupancy", y="market_rent", color="type", size="asking_price", hover_data=["property_id", "submarket"], title="Occupancy vs market rent by type")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Public market anchors")
    st.dataframe(anchors[["market_metric", "property_type", "as_of", "value", "units", "tag"]], hide_index=True, use_container_width=True)
    st.caption("REAL PUBLIC DATA — CBRE and FRED. These are aggregate market figures, not property-level.")

    st.markdown("---")
    st.subheader("Correlations (numeric fields)")
    num = props[["size_sf", "asking_price", "current_noi", "going_in_cap", "occupancy", "walt", "tenant_concentration", "property_quality", "market_rent", "debt_rate"]].copy()
    corr = num.corr()
    st.dataframe(corr.round(3), use_container_width=True)
    fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu", title="Correlation matrix (numeric fields)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.info("This page gives you enough to form hypotheses. It does NOT tell you which property is best.")
    import pages.navigation as navigation
    st.page_link(navigation.page("deals"), label="→ Next: Deal Room", use_container_width=True)


if __name__ == "__main__":
    show()
