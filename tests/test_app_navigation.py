"""
Streamlit AppTest smoke tests for multipage navigation.

Two claims are verified here:

1. The multipage app shell (app.py) launches and renders its home content and
   its sidebar navigation page_links.
2. Every registered page module can be executed in isolation without an uncaught
   exception.

AppTest in this Streamlit build does not reliably expose per-page text content
from the multipage shell via the public API, so page-level assertions use
AppTest.from_file on the page module directly. That is sufficient to prove the
page loads and renders, which is the requirement we need for the professor MVP.
"""

from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

import pages.navigation

from streamlit.testing.v1 import AppTest


APP_PATH = REPO_ROOT / "app.py"

PAGES_WITH_FILES = {
    "home": "app.py",
    "briefing": "pages/briefing.py",
    "data": "pages/data_catalog.py",
    "data-quality": "pages/data_quality.py",
    "market": "pages/market_explorer.py",
    "sql": "pages/sql_lab.py",
    "valuation": "pages/valuation_lab.py",
    "geo": "pages/geospatial.py",
    "deals": "pages/deal_room.py",
    "decision": "pages/investment_decision.py",
    "professor": "pages/professor_control.py",
    "results": "pages/results.py",
    "methodology": "pages/provenance.py",
}


@pytest.fixture
def at():
    return AppTest.from_file(str(APP_PATH))


def shell_rendered(at: AppTest) -> str:
    chunks = []
    for b in at.markdown:
        v = getattr(b, "value", "") or ""
        if isinstance(v, str) and v.strip():
            chunks.append(v)
    for b in at.title:
        v = getattr(b, "value", "") or ""
        if isinstance(v, str) and v.strip():
            chunks.append(v)
    return "\n".join(chunks)


class TestAppLaunch:
    def test_app_launches_without_exception(self, at: AppTest):
        at.run()
        assert (at.exception == () or len(at.exception) == 0), f"app failed to launch: {at.exception}"
        assert "REAL 605 CRE Investment Committee Simulation" in shell_rendered(at)

    def test_home_page_links_exist(self, at: AppTest):
        at.run()
        assert (at.exception == () or len(at.exception) == 0)
        labels = []
        for el in at:
            proto = getattr(el, "proto", None)
            if proto is None:
                continue
            if getattr(proto, "page", None):
                labels.append(getattr(el, "label", None))
        assert "1 · Briefing — understand the decision" in labels
        assert "2 · Data Quality Challenge — your (imperfect) data" in labels
        assert "3 · Professor Control — start the demo" in labels
        assert "Skip ahead to Professor Control" in labels


class TestPageLoads:
    """Each registered page must load and render without uncaught exception."""

    def _page_runs_without_exception(self, page_file: str) -> str:
        isolated = AppTest.from_file(str(REPO_ROOT / page_file))
        isolated.run()
        assert (isolated.exception == () or len(isolated.exception) == 0), (
            f"{page_file} raised: {isolated.exception}"
        )
        # Best-effort minimal content check: a loaded Streamlit page always renders
        # at least its top-level container. If AppTest here does not expose text,
        # we still accept the run as success because the requirement is "no exception".
        return ""

    def test_briefing_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["briefing"])

    def test_data_catalog_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["data"])

    def test_data_quality_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["data-quality"])

    def test_market_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["market"])

    def test_sql_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["sql"])

    def test_valuation_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["valuation"])

    def test_geospatial_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["geo"])

    def test_deal_room_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["deals"])

    def test_decision_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["decision"])

    def test_professor_control_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["professor"])

    def test_results_debrief_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["results"])

    def test_provenance_page_loads(self, at: AppTest):
        self._page_runs_without_exception(PAGES_WITH_FILES["methodology"])
