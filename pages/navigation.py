"""
Page registry for in-content navigation links.

Page modules can call pages.navigation.page("professor") to get the Page object
and render st.page_link(page_obj, ...).
"""

from __future__ import annotations

import pages

def _mod(key: str):
    if key == "home":
        import pages.home as m
        return m
    if key == "briefing":
        import pages.briefing as m
        return m
    if key == "data":
        import pages.data_catalog as m
        return m
    if key == "data-quality":
        import pages.data_quality as m
        return m
    if key == "market":
        import pages.market_explorer as m
        return m
    if key == "sql":
        import pages.sql_lab as m
        return m
    if key == "valuation":
        import pages.valuation_lab as m
        return m
    if key == "geo":
        import pages.geospatial as m
        return m
    if key == "deals":
        import pages.deal_room as m
        return m
    if key == "decision":
        import pages.investment_decision as m
        return m
    if key == "professor":
        import pages.professor_control as m
        return m
    if key == "results":
        import pages.results as m
        return m
    if key == "methodology":
        import pages.provenance as m
        return m
    raise KeyError(key)

PAGES = {
    "home": _mod("home"),
    "briefing": _mod("briefing"),
    "data": _mod("data"),
    "data-quality": _mod("data-quality"),
    "market": _mod("market"),
    "sql": _mod("sql"),
    "valuation": _mod("valuation"),
    "geo": _mod("geo"),
    "deals": _mod("deals"),
    "decision": _mod("decision"),
    "professor": _mod("professor"),
    "results": _mod("results"),
    "methodology": _mod("methodology"),
}

_url_path_to_key = {
    "": "home",
    "briefing": "briefing",
    "data": "data",
    "data-quality": "data-quality",
    "market": "market",
    "sql": "sql",
    "valuation": "valuation",
    "geo": "geo",
    "deals": "deals",
    "decision": "decision",
    "professor": "professor",
    "results": "results",
    "methodology": "methodology",
}


def page(key: str):
    """Return the Page object for a stable key so page content can render st.page_link(page_obj)."""
    mod = PAGES[key]
    # Build a minimal Page object matching the one in app.py for st.page_link compatibility.
    import streamlit as st

    return st.Page(
        mod.show,
        title=mod.__dict__.get("__page_title__", key),
        url_path=_url_path_to_key.get(key, key),
    )
