"""
Mapping helpers using PyDeck.

Displays real property/parcel locations where available and the synthetic property set
positioned at plausible submarket coordinates (overlaid on real parcel context where provided).
"""

from __future__ import annotations

from typing import Optional
import pandas as pd
import pydeck as pdk


def pydeck_property_map(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    color_col: Optional[str] = None,
    height_col: Optional[str] = None,
    title: str = "Orange County CRE Properties",
    initial_view_state: Optional[dict] = None,
):
    """Return a PyDeck Layer/visualization for the given property DataFrame."""
    if initial_view_state is None:
        initial_view_state = {
            "latitude": 33.75,
            "longitude": -117.88,
            "zoom": 9.5,
            "pitch": 0,
        }
    # Choose color by property type
    type_colors = {
        "Industrial": [255, 160, 0],
        "Office": [0, 120, 255],
        "Multifamily": [0, 200, 120],
        "Retail": [200, 80, 200],
    }
    def colors(r):
        c = type_colors.get(r.get(color_col, "") if color_col else "", [150, 150, 150])
        return c
    df = df.copy()
    if color_col and color_col not in df.columns:
        df[color_col] = ""
    if color_col:
        df["color"] = df.apply(colors, axis=1)
    else:
        # default by type
        df["color"] = df["type"].map(type_colors).apply(lambda c: c if isinstance(c, list) else [150,150,150])
    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position=[f"({lon_col}, {lat_col})"],
        get_fill_color="color",
        get_radius=350,
        pickable=True,
        auto_highlight=True,
    )
    tooltip = {"html": "<b>{property_name}</b><br/>{type} · {submarket}<br/>Ask: ${asking_price:.1f}M · Cap: {going_in_cap:.2%}<br/>Occupancy: {occupancy:.0%}", "style": {"backgroundColor": "#fff", "color": "#333"}}
    view_state = pdk.ViewState(**initial_view_state)
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9",
    )
    return deck


def pydeck_parcel_map(parcels: pd.DataFrame, center_lat: float = 33.75, center_lon: float = -117.88):
    """Polygon layer for a sample of OC parcels (lightweight outline)."""
    df = parcels.copy()
    df = df.dropna(subset=["lon", "lat"])
    # For polygons we would use a PolygonLayer; for point samples use ScatterplotLayer
    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position=["lon", "lat"],
        get_fill_color=[180, 180, 180, 120],
        get_radius=8,
        pickable=False,
    )
    view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=10, pitch=0)
    return pdk.Deck(layers=[layer], initial_view_state=view_state, map_style="mapbox://styles/mapbox/light-v9")
