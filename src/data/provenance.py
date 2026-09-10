"""
Provenance metadata for every data asset.

Each table/column/source must carry:
source_name
source_url
observation_date
available_at
retrieved_at
data_type
is_synthetic
notes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Provenance:
    source_name: str
    source_url: str
    observation_date: Optional[date] = None
    available_at: Optional[date] = None
    retrieved_at: Optional[datetime] = None

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)
    data_type: str = "real_public"
    is_synthetic: bool = False
    notes: str = ""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now() -> datetime:
    return _now_utc()


DEFAULT_PROVENANCE = Provenance(
    source_name="Chapman REAL 605 simulation (semipsynthetic teaching app)",
    source_url="https://github.com/chapman-real605/cre-sim",
    data_type="derived_feature",
    is_synthetic=True,
    notes="Generated for classroom simulation. Not observed real-world data.",
)


def now() -> datetime:
    return _now_utc()


def tag_label(provenance: Provenance) -> str:
    if provenance.is_synthetic:
        return "SYNTHETIC TEACHING DATA"
    if provenance.data_type in ("derived_feature",):
        return "DERIVED FEATURE"
    if provenance.data_type == "simulated_future":
        return "SIMULATED FUTURE"
    return "REAL PUBLIC DATA"
