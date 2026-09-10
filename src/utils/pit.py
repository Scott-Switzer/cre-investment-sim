"""
Point-in-time (PIT) snapshot utilities.

Every observation used for a student decision must satisfy:
    available_at <= decision_timestamp
unless intentionally included as a leakage trap in the data-cleaning exercise.

This module provides:
- build_student_snapshot(as_of_date): returns only allowed information
- assert_point_in_time(...): test helper that validates PIT constraints

These are tested explicitly to prevent hindsight bias and leakage.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from src.data.properties import generate_properties
from src.data.data_quality import build_student_copy, LEAKAGE_FIELD
from src.data.market_anchors import build_market_anchors
from src.data.macro import build_macro_history
from src.data.provenance import Provenance


def _parse_date(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, (date, datetime)):
        return x.date() if isinstance(x, datetime) else x
    if isinstance(x, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(x, fmt).date()
            except ValueError:
                continue
    return None


def build_student_snapshot(
    as_of_date: date,
    seed: int = 20240331,
    count: int = 30,
    include_leakage_field: bool = False,
) -> Dict[str, Any]:
    """
    Build the point-in-time student snapshot available at as_of_date.

    Includes:
    - properties: the imperfect student copy, filtered to rows whose available_at <= as_of_date
    - market_anchors: only anchors available at as_of_date
    - macro_history: only macro observations available at as_of_date
    - leakage_field: included ONLY if include_leakage_field=True (for the deliberate trap)

    The snapshot intentionally does NOT include any future data.
    """
    student = build_student_copy(seed=seed, count=count)
    # Filter property rows to available_at <= as_of_date
    student_dates = pd.to_datetime(student["available_at"], errors="coerce").dt.date
    allowed_props = student[student_dates <= as_of_date].copy()
    # Drop leakage field unless deliberately included
    if not include_leakage_field and LEAKAGE_FIELD in allowed_props.columns:
        allowed_props = allowed_props.drop(columns=[LEAKAGE_FIELD])

    # Market anchors available at as_of_date
    anchors = build_market_anchors()
    anchor_dates = pd.to_datetime(anchors["as_of"], errors="coerce").dt.date
    allowed_anchors = anchors[anchor_dates <= as_of_date]

    # Macro available at as_of_date
    macro = build_macro_history()
    macro_dates = pd.to_datetime(macro["available_at"], errors="coerce").dt.date
    allowed_macro = macro[macro_dates <= as_of_date]

    return {
        "decision_date": as_of_date,
        "properties": allowed_props,
        "market_anchors": allowed_anchors,
        "macro_history": allowed_macro,
        "leakage_field_included": include_leakage_field,
        "properties_count": len(allowed_props),
        "anchors_count": len(allowed_anchors),
        "macro_count": len(allowed_macro),
    }


def assert_point_in_time(
    snapshot: Dict[str, Any],
    decision_date: date,
    expect_leakage_field_absent: bool = True,
) -> None:
    """
    Assert that the snapshot contains no data available after the decision date,
    except the deliberately injected leakage field when expected.

    Raises AssertionError with a descriptive message on violation.
    """
    decision = _parse_date(decision_date) or decision_date
    # Properties
    props = snapshot["properties"]
    if "available_at" in props.columns:
        avail = pd.to_datetime(props["available_at"], errors="coerce").dt.date
        future = props[avail > decision]
        assert len(future) == 0, f"Found {len(future)} property rows available AFTER decision date {decision}"
    # Market anchors
    anchors = snapshot["market_anchors"]
    if "as_of" in anchors.columns:
        a = pd.to_datetime(anchors["as_of"], errors="coerce").dt.date
        future = anchors[a > decision]
        assert len(future) == 0, f"Found {len(future)} market anchors observed AFTER decision date {decision}"
    # Macro
    macro = snapshot["macro_history"]
    if "available_at" in macro.columns:
        m = pd.to_datetime(macro["available_at"], errors="coerce").dt.date
        future = macro[m > decision]
        assert len(future) == 0, f"Found {len(future)} macro observations available AFTER decision date {decision}"
    # Leakage field
    if expect_leakage_field_absent:
        if LEAKAGE_FIELD in props.columns:
            raise AssertionError(f"Leakage field {LEAKAGE_FIELD} should not be present in a clean snapshot")
    else:
        if LEAKAGE_FIELD not in props.columns:
            raise AssertionError(f"Leakage field {LEAKAGE_FIELD} should be present when include_leakage_field=True")


def test_point_in_time_filters_future() -> bool:
    """Quick self-test: snapshot at 2024-03-31 should contain no data after that date."""
    snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=False)
    assert_point_in_time(snap, decision_date=date(2024, 3, 31))
    return True


def test_point_in_time_allows_earlier() -> bool:
    """Earlier decision date should see a subset (no future data)."""
    snap = build_student_snapshot(date(2024, 1, 1), seed=20240331, count=30, include_leakage_field=False)
    assert_point_in_time(snap, decision_date=date(2024, 1, 1))
    # Should have fewer or equal properties than the full set
    assert snap["properties_count"] <= 30
    return True


def test_point_in_time_leakage_field_trap() -> bool:
    """When include_leakage_field=True, the field is present and flagged."""
    snap = build_student_snapshot(date(2024, 3, 31), seed=20240331, count=30, include_leakage_field=True)
    assert LEAKAGE_FIELD in snap["properties"].columns
    assert snap["leakage_field_included"] is True
    # But macro/anchors still filtered to before decision date
    assert_point_in_time(snap, decision_date=date(2024, 3, 31), expect_leakage_field_absent=False)
    return True
