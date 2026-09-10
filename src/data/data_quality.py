"""
Data quality challenge: deliberately imperfect STUDENT COPY of the property dataset.

The instructor truth dataset is the pristine synthetic property table.
The student copy has a small, reproducible set of issues, including:
- missing values
- duplicate rows
- inconsistent property type labels
- different date formats
- stale observations
- extreme but potentially legitimate outliers
- one future/leakage field clearly available only after the decision date

The manifest describes injected issues for instructor/developer verification.

The application does NOT automatically fix everything for the student.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List
import pandas as pd
import numpy as np

from src.data.properties import generate_properties
from src.data.provenance import Provenance, now, tag_label


# Provenance for the student copy (imperfect)
_STUDENT_COPY_PROV = Provenance(
    source_name="CRE Simulation student data copy (imperfect, for cleaning exercise)",
    source_url="https://github.com/chapman-real605/cre-sim",
    observation_date=date(2024, 3, 31),
    available_at=date(2024, 3, 31),
    retrieved_at=now(),
    data_type="synthetic_teaching",
    is_synthetic=True,
    notes="Student copy derived from the pristine instructor dataset with injected data-quality issues for classroom cleaning exercise.",
)


# A leakage field that is ONLY available after the decision date (2024-03-31).
# Included intentionally as a data-cleaning / point-in-time test trap.
LEAKAGE_FIELD = "future_market_cap_rate_observed_q2_2026"


DATA_QUALITY_MANIFEST = [
    {
        "issue_id": "DQ-01",
        "description": "Missing asking_price for one property.",
        "affects_column": "asking_price",
        "affects_rows": 1,
        "inject_mode": "set_null",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-02",
        "description": "Duplicate row for one property (identical property_id appears twice).",
        "affects_column": "property_id",
        "affects_rows": 1,
        "inject_mode": "duplicate_row",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-03",
        "description": "Inconsistent property type label: one row says 'Ind'l' instead of 'Industrial'.",
        "affects_column": "type",
        "affects_rows": 1,
        "inject_mode": "rename_value",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-04",
        "description": "Different date format in observation_date for one row (string '03/31/2024' vs ISO).",
        "affects_column": "observation_date",
        "affects_rows": 1,
        "inject_mode": "reformat_date",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-05",
        "description": "Stale observation_date for one row (2023-12-31 instead of 2024-03-31).",
        "affects_column": "observation_date",
        "affects_rows": 1,
        "inject_mode": "set_stale_date",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-06",
        "description": "Extreme but potentially legitimate outlier: one property's asking_price is 3x the peer median.",
        "affects_column": "asking_price",
        "affects_rows": 1,
        "inject_mode": "multiply_by_factor",
        "reproducible": True,
    },
    {
        "issue_id": "DQ-07",
        "description": "Leakage field available only after the decision date: future_market_cap_rate_observed_q2_2026 present for all rows.",
        "affects_column": LEAKAGE_FIELD,
        "affects_rows": None,
        "inject_mode": "add_future_field",
        "reproducible": True,
        "point_in_time_note": "This field is sourced from Q2 2026 CBRE data, available after 2024-03-31. Using it for a 2024-03-31 decision is leakage.",
    },
]


def build_student_copy(seed: int = 20240331, count: int = 30) -> pd.DataFrame:
    """Create the imperfect student copy from the pristine generator output."""
    pristine = generate_properties(seed=seed, count=count).copy()
    rng = np.random.default_rng(seed)

    # DQ-01: missing asking_price for one row
    idx01 = rng.integers(0, len(pristine))
    pristine.loc[pristine.index[idx01], "asking_price"] = np.nan

    # DQ-02: duplicate a row
    idx02 = rng.integers(0, len(pristine))
    row_to_dup = pristine.iloc[idx02].copy()
    pristine = pd.concat([pristine, row_to_dup.to_frame().T], ignore_index=True)

    # DQ-03: inconsistent type label
    idx03 = rng.integers(0, len(pristine))
    pristine.loc[pristine.index[idx03], "type"] = "Ind'l"

    # DQ-04: different date format in observation_date for one row
    idx04 = rng.integers(0, len(pristine))
    pristine.loc[pristine.index[idx04], "observation_date"] = "03/31/2024"

    # DQ-05: stale observation_date for one row
    idx05 = rng.integers(0, len(pristine))
    pristine.loc[pristine.index[idx05], "observation_date"] = "2023-12-31"

    # DQ-06: extreme outlier in asking_price
    idx06 = rng.integers(0, len(pristine))
    pristine.loc[pristine.index[idx06], "asking_price"] = pristine.loc[pristine.index[idx06], "asking_price"] * 3.0

    # DQ-07: add leakage field with values sourced from Q2 2026 (after decision date)
    pristine[LEAKAGE_FIELD] = np.round(0.058 + rng.normal(0, 0.005, size=len(pristine)), 4)

    # Add provenance columns for the student copy
    pristine["is_synthetic"] = True
    pristine["source_name"] = _STUDENT_COPY_PROV.source_name
    pristine["source_url"] = _STUDENT_COPY_PROV.source_url
    pristine["data_type"] = _STUDENT_COPY_PROV.data_type
    pristine["notes"] = _STUDENT_COPY_PROV.notes
    pristine["tag"] = tag_label(_STUDENT_COPY_PROV)

    # Store manifest into a small attribute on the dataframe for the app to surface
    pristine.attrs["data_quality_manifest"] = DATA_QUALITY_MANIFEST
    pristine.attrs["leakage_field"] = LEAKAGE_FIELD

    return pristine


def student_copy_triaged() -> Dict:
    """Return a dict describing the student copy for the data-quality page."""
    return {
        "manifest": DATA_QUALITY_MANIFEST,
        "leakage_field": LEAKAGE_FIELD,
        "decision_date": date(2024, 3, 31).isoformat(),
        "note": "The application intentionally does not auto-clean these issues. Students must identify and handle them.",
    }
