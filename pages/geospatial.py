from __future__ import annotations

import streamlit as st
import pandas as pd


def show():
    st.title("7 · Geospatial View")
    st.caption("Real parcel context where available; synthetic properties at plausible submarket coordinates.")

    from src.data.duckdb import DuckDBBackend
    from src.geo.features import build_geospatial_features, employment_proxy_features
    from src.geo.mapping import pydeck_property_map
    from src.geo.parcels import parcels_dataframe, PARCEL_SOURCE

    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties")
    finally:
        db.close()

    geo = build_geospatial_features(props)
    emp = employment_proxy_features()

    st.subheader("Property locations (PyDeck)")
    st.pydeck_chart(pydeck_property_map(geo, color_col="type"), use_container_width=True)

    st.markdown("---")
    st.subheader("Derived geospatial features (DERIVED FEATURE)")
    feat_cols = ["property_id", "submarket", "latitude", "longitude", "census_tract", "employment_density_jobs_per_sqmi", "distance_to_sna_km", "distance_to_irvine_emp_km", "flood_risk_indicator"]
    st.dataframe(geo[feat_cols].round(4), use_container_width=True, height=320)
    st.caption(
        "Coordinates are positioned at plausible submarket centers with small jitter for visual separation; "
        "real parcel geometry is available via the OC GIS REST service and would be overlaid in a full version. "
        "Employment density is a cached public-data sample proxy; real implementation uses Census LEHD/LODES WAC files."
    )

    st.markdown("---")
    st.subheader("Employment proxy by submarket (public-data sample)")
    st.dataframe(emp, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Real OC parcel context (sample)")
    st.info(
        f"{PARCEL_SOURCE['name']} — {PARCEL_SOURCE['url']}\n\n"
        "Real public parcel geometry/APN/address. Retrieved from OC Survey Geospatial Services. "
        "This is context only; assessed values are NOT transaction market value."
    )
    try:
        sample = parcels_dataframe(limit=1500)
        st.dataframe(sample[["parcel_objectid", "apn", "site_address", "year_built", "nbr_bedrooms", "shape_area_sqft", "lon", "lat"]].head(100), use_container_width=True, height=320)
        st.caption(f"Sample of {min(1500, len(sample))} OC parcels with geometry reprojected to WGS84.")
        st.pydeck_chart(pydeck_parcel_map := __import__("src.geo.mapping", fromlist=["pydeck_parcel_map"]).pydeck_parcel_map(sample), use_container_width=True)
    except Exception as e:
        st.warning(f"Parcel sample unavailable right now: {e}")

    st.markdown("---")
    st.page_link("pages/deal_room.py", label="→ Next: Deal Room", icon="")
