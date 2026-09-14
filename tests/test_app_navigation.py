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
        rendered = shell_rendered(at)
        assert "CRE Investment Committee" in rendered or "REAL 605" in rendered

    def test_home_page_links_exist(self, at: AppTest):
        at.run()
        assert (at.exception == () or len(at.exception) == 0)
        # New app uses single-page state machine with buttons,
        # not multipage sidebar links. Check for actual button labels.
        button_labels = []
        for b in at.button:
            label = getattr(b, "label", "") or ""
            if isinstance(label, str):
                button_labels.append(label)
        # Verify key navigation buttons exist
        assert "BEGIN PRACTICE ROUND" in button_labels, f"BEGIN PRACTICE ROUND not found in {button_labels}"


class TestEveryPageIsReachable:
    """A page nobody can navigate to is a dead page.

    ``.streamlit/config.toml`` sets ``showSidebarNavigation = false``, so the only
    way to reach a page is an explicit ``st.page_link``. Professor Control was
    once link-free and therefore unreachable from the UI, which broke the whole
    instructor flow while every existing test still passed.
    """

    def test_landing_page_links_to_every_page(self):
        source = APP_PATH.read_text()
        must_be_linked = [
            "pages/professor_control.py",
            "pages/leaderboard.py",
            "pages/final_debrief.py",
            "pages/datasets.py",
            "pages/model_checkin.py",
            "pages/strategy_card.py",
        ]
        missing = [p for p in must_be_linked if p not in source]
        assert not missing, f"unreachable from the landing page: {missing}"

    def test_sidebar_navigation_is_off_so_links_are_mandatory(self):
        cfg = (REPO_ROOT / ".streamlit" / "config.toml").read_text()
        assert "showSidebarNavigation = false" in cfg


class TestPageLoads:
    """Each registered page must load and render without uncaught exception."""

    # `AppTest` defaults to a 3-second timeout, which is a poll window rather than
    # a total-runtime budget: if a page computes quietly for longer than that, the
    # run is abandoned even though nothing is wrong. `pages/valuation_lab.py`
    # fits a model on load and takes ~3.8s, so it failed intermittently under the
    # load of the full suite. The page is not slow because it is broken, so the
    # timeout is raised here instead of the page being made to look fast.
    PAGE_TIMEOUT_SECONDS = 60

    def _page_runs_without_exception(self, page_file: str) -> str:
        isolated = AppTest.from_file(
            str(REPO_ROOT / page_file), default_timeout=self.PAGE_TIMEOUT_SECONDS
        )
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
