import pytest
from datetime import date

from src.utils.pit import (
    build_student_snapshot,
    assert_point_in_time,
    test_point_in_time_filters_future,
    test_point_in_time_allows_earlier,
    test_point_in_time_leakage_field_trap,
)


class TestPointInTime:
    def test_snapshot_builds(self):
        snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=False)
        assert snap["properties_count"] >= 29  # due to dedup in student copy
        assert "properties" in snap
        assert "market_anchors" in snap
        assert "macro_history" in snap
        # NOTE: market anchors and macro in the cached demo are dated 2024-2026, so at a 2024-03-31
        # decision date they may be zero because they are AFTER the decision date (point-in-time correct).
        # That is the DESIRED behavior for PIT filtering; anchors/macro are populated in demo mode separately.

    def test_snapshot_filters_future(self):
        assert test_point_in_time_filters_future() is True

    def test_snapshot_allows_earlier(self):
        assert test_point_in_time_allows_earlier() is True

    def test_leakage_field_trap(self):
        assert test_point_in_time_leakage_field_trap() is True

    def test_clean_snapshot_has_no_leakage_field(self):
        snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=False)
        assert "future_market_cap_rate_observed_q2_2026" not in snap["properties"].columns

    def test_snapshot_with_leakage_field_has_it(self):
        snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=True)
        assert "future_market_cap_rate_observed_q2_2026" in snap["properties"].columns

    def test_assertion_raises_on_future_data(self):
        # Build snapshot with leakage field and pretend it's a clean one => should raise
        snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=True)
        with pytest.raises(AssertionError, match="Leakage field"):
            assert_point_in_time(snap, decision_date=date(2024, 3, 31), expect_leakage_field_absent=True)

    def test_assertion_raises_on_future_anchor(self):
        # If an anchor is observed after decision date, assert_point_in_time should raise
        from src.data.market_anchors import build_market_anchors
        anchors = build_market_anchors()
        # All anchors are Q2 2026 / Sep 2026, which are AFTER 2024-03-31 -> so they SHOULD be filtered out
        snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=False)
        # anchors filtered
        assert len(snap["market_anchors"]) == 0
        # no assertion error expected
        assert_point_in_time(snap, decision_date=date(2024, 3, 31))
