"""
Semipsynthetic commercial property operating data.

Real parcel/geographic context is layered in separately (see src/geo).
This module generates realistic synthetic operating cases calibrated to OC market anchors.

Generation is deterministic from a configurable random seed.
Every synthetic field is flagged is_synthetic=True in the provenance schema.

The same generator is used to create:
- the pristine INSTRUCTOR truth dataset
- the deliberately imperfect STUDENT COPY (with injected data-quality issues)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.data.provenance import Provenance, now, tag_label, DEFAULT_PROVENANCE


# Provenance for synthetic property layer
_SYNTH_PROP_PROV = Provenance(
    source_name="Semipsynthetic CRE operating cases (deterministic generator)",
    source_url="https://github.com/chapman-real605/cre-sim",
    observation_date=date(2024, 3, 31),
    available_at=date(2024, 3, 31),
    retrieved_at=now(),
    data_type="synthetic_teaching",
    is_synthetic=True,
    notes="Realistic synthetic property operating data calibrated to OC Q2 2026 public market anchors. NOT real property transactions.",
)

# Real parcel context provenance (layer added by geo module)
_PARCEL_CONTEXT_PROV = Provenance(
    source_name="OC GIS Parcels (parcel context / APN / address)",
    source_url="https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0",
    data_type="real_public",
    is_synthetic=False,
    notes="Real parcel geometry and identifiers used for geospatial context only.",
)


@dataclass
class PropertyRow:
    property_id: str
    property_name: str
    type: str
    submarket: str
    apn: str
    site_address: str
    parcel_objectid: Optional[int]
    size_sf: int
    units: Optional[int]
    asking_price: float
    current_noi: float
    going_in_cap: float
    occupancy: float
    market_rent: float
    in_place_rent: float
    walt: float
    tenant_concentration: float
    opex_ratio: float
    capex_need: float
    debt_rate: float
    amortization_years: int
    max_ltv: float
    property_quality: float
    leasable_area_sf: int
    lease_expiry_profile: str
    primary_risk: str
    is_synthetic: bool
    provenance: Provenance
    observation_date: date
    available_at: date


# Submarket anchor points (plausible locations around OC)
SUBMARKETS = {
    "Anaheim": {"lat": 33.836, "lon": -117.914, "note": "Anaheim submarket"},
    "Irvine": {"lat": 33.684, "lon": -117.826, "note": "Irvine submarket"},
    "Newport Beach": {"lat": 33.618, "lon": -117.928, "note": "Newport Beach submarket"},
    "Orange": {"lat": 33.792, "lon": -117.826, "note": "Orange submarket"},
    "Santa Ana": {"lat": 33.745, "lon": -117.867, "note": "Santa Ana submarket"},
    "Costa Mesa": {"lat": 33.644, "lon": -117.925, "note": "Costa Mesa submarket"},
    "Fullerton": {"lat": 33.870, "lon": -117.925, "note": "Fullerton submarket"},
}


# Property type base profiles (calibrated to OC Q2 2026 anchors)
TYPE_PROFILES = {
    "Industrial": {
        "cap_range": (0.050, 0.060),
        "noi_margin": 0.70,  # NOI / asking price approx
        "occ_range": (0.93, 1.00),
        "walt_range": (2.0, 8.0),
        "rent_anchor": 1.49,  # $/SF/mo NNN CBRE anchor
        "rent_spread": 0.25,
        "debt_rate_range": (0.060, 0.066),
        "max_ltv": 0.70,
        "amort": 25,
        "size_sf_range": (60000, 220000),
        "lease_spread": "NNN",
    },
    "Office": {
        "cap_range": (0.062, 0.078),
        "noi_margin": 0.66,
        "occ_range": (0.75, 0.95),
        "walt_range": (2.0, 7.0),
        "rent_anchor": 2.89,  # $/SF/mo FSG CBRE anchor
        "rent_spread": 0.55,
        "debt_rate_range": (0.063, 0.072),
        "max_ltv": 0.60,
        "amort": 25,
        "size_sf_range": (90000, 260000),
        "lease_spread": "FSG",
    },
    "Multifamily": {
        "cap_range": (0.048, 0.058),
        "noi_margin": 0.62,
        "occ_range": (0.92, 0.98),
        "walt_range": (0.8, 1.5),
        "rent_anchor": 2944.0,  # $/unit/mo CBRE anchor
        "rent_spread": 550.0,
        "debt_rate_range": (0.059, 0.064),
        "max_ltv": 0.70,
        "amort": 30,
        "size_sf_range": (20000, 70000),
        "lease_spread": "Per unit",
    },
    "Retail": {
        "cap_range": (0.060, 0.070),
        "noi_margin": 0.64,
        "occ_range": (0.88, 0.97),
        "walt_range": (2.0, 6.0),
        "rent_anchor": 3.05,  # $/SF/mo NNN CBRE anchor
        "rent_spread": 0.60,
        "debt_rate_range": (0.063, 0.069),
        "max_ltv": 0.65,
        "amort": 25,
        "size_sf_range": (30000, 160000),
        "lease_spread": "NNN",
    },
}


_PROPERTY_NAMES_BY_TYPE = {
    "Industrial": ["Anaheim Commerce Center", "Irvine Spectrum Logistics", "Fullerton Distribution Park", "Garden Grove Logistics Center", "Tustin Business Park", "Cypress Industrial Yard", "Orange Industrial Park", "Santa Ana Logistics Hub", "Fountain Valley Warehouse", "Laguna Beach Industrial Lofts (hybrid)"],
    "Office": ["Jamboree Office Plaza", "Newport Gateway Offices", "Irvine Corporate Center", "Anaheim Office Park", "Costa Mesa Professional Tower", "Huntington Beach Executive Suites", "Tustin Office Village", "Fullerton Business Center"],
    "Multifamily": ["Orange Grove Apartments", "Santa Ana Urban Flats", "Anaheim Garden Apartments", "Irvine Park Courts", "Fullerton Square Apartments", "Costa Mesa Midtown Flats", "Tustin Station Apartments", "Newport Shores Apartments"],
    "Retail": ["Costa Mesa Retail Row", "Fullerton Marketplace", "Irvine Spectrum Retail Pad", "Anaheim Plaza Retail", "Garden Grove Shopping Center", "Santa Ana Retail Commons", "Newport Beach Retail Corner", "Tustin Village Shops"],
}


def _rent_for_type(ptype: str, profile: dict, rng: np.random.Generator, size_sf: int, units: Optional[int]) -> float:
    anchor = profile["rent_anchor"]
    if ptype == "Multifamily":
        return round(anchor + rng.normal(0, profile["rent_spread"]), 2)
    else:
        # $/SF/month
        return round(anchor + rng.normal(0, profile["rent_spread"]), 3)


def generate_properties(seed: int = 20240331, count: int = 30) -> pd.DataFrame:
    """Generate a deterministic set of synthetic properties with real parcel context metadata."""
    rng = np.random.default_rng(seed)
    # Fixed ordering so the generator is reproducible and stable across runs.
    # We cycle through submarkets and property types in a stable sequence.
    ids: List[PropertyRow] = []
    # deterministic index
    idx = 0
    ptype_cycle = ["Industrial", "Office", "Multifamily", "Retail"]
    sub_cycle = list(SUBMARKETS.keys())
    name_counters: Dict[str, int] = {pt: 0 for pt in ptype_cycle}

    while len(ids) < count:
        ptype = ptype_cycle[idx % len(ptype_cycle)]
        sm = sub_cycle[(idx // len(ptype_cycle)) % len(sub_cycle)]
        profile = TYPE_PROFILES[ptype]
        names = _PROPERTY_NAMES_BY_TYPE[ptype]
        name_counter = name_counters[ptype]
        name = names[name_counter % len(names)] + (" " + str(name_counter // len(names) + 1) if name_counter >= len(names) else "")
        name_counters[ptype] += 1

        # size
        size_sf = int(rng.integers(profile["size_sf_range"][0], profile["size_sf_range"][1] + 1))
        if ptype == "Multifamily":
            units = int(size_sf / rng.integers(900, 1400))
            size_sf = units * int(rng.integers(900, 1400))
        else:
            units = None

        # occupancy and WALT
        occ = round(float(rng.uniform(*profile["occ_range"])), 3)
        walt = round(float(rng.uniform(*profile["walt_range"])), 1)

        # property quality 0-1
        quality = round(float(rng.beta(2, 2)), 3)

        # market rent
        mrent = _rent_for_type(ptype, profile, rng, size_sf, units)

        # cap rate (quality and market affect cap)
        cap_lo, cap_hi = profile["cap_range"]
        cap = round(float(rng.uniform(cap_lo, cap_hi)) - 0.002 * quality + 0.001 * rng.normal(0, 0.002), 4)
        cap = round(max(0.035, min(0.09, cap)), 4)

        # asking price from NOI / cap
        # NOI from size, occupancy, rent, opex ratio
        opex_ratio = round(float(rng.uniform(0.30, 0.45)), 3)
        if ptype == "Multifamily":
            potential_gross = mrent * units * 12
        else:
            potential_gross = mrent * size_sf * 12
        effective_gross = potential_gross * occ * (0.98 if quality > 0.5 else 0.95)
        opex = effective_gross * opex_ratio
        noi = round((effective_gross - opex) / 1e6, 4)
        asking = round(noi / cap, 4)

        # rent jitter for in-place
        in_place_rent = round(mrent * (0.96 + 0.08 * rng.random()), 3)

        # tenant concentration (higher = more risk)
        tenant_concentration = round(float(rng.beta(1, 3)), 3)

        # debt rate
        dr_lo, dr_hi = profile["debt_rate_range"]
        debt_rate = round(float(rng.uniform(dr_lo, dr_hi)) - 0.001 * quality + 0.001 * rng.normal(0, 0.0005), 4)
        debt_rate = round(max(0.045, min(0.08, debt_rate)), 4)

        # capex need
        capex_need = round(float(rng.uniform(0.005, 0.035) * asking), 4)

        # lease expiry profile as a short string
        expiry_profile = f"{walt:.1f}yr WALT, {int(rng.integers(20,60))}% rolling in 3yrs"

        # APN / parcel context — deterministic placeholder APN by submarket prefix
        apn = f"{SUBMARKETS[sm]['lat']:.0f}{SUBMARKETS[sm]['lon']:.0f}-{idx:04d}"

        site_address = f"{1000 + idx * 17} {sm} {ptype} Way"

        row = PropertyRow(
            property_id=f"OC-{ptype[:4].upper()}-{idx+1:02d}",
            property_name=name,
            type=ptype,
            submarket=sm,
            apn=apn,
            site_address=site_address,
            parcel_objectid=(idx % 100000 + 1),
            size_sf=size_sf,
            units=units,
            asking_price=asking,
            current_noi=noi,
            going_in_cap=cap,
            occupancy=occ,
            market_rent=mrent,
            in_place_rent=in_place_rent,
            walt=walt,
            tenant_concentration=tenant_concentration,
            opex_ratio=opex_ratio,
            capex_need=capex_need,
            debt_rate=debt_rate,
            amortization_years=profile["amort"],
            max_ltv=profile["max_ltv"],
            property_quality=quality,
            leasable_area_sf=size_sf,
            lease_expiry_profile=expiry_profile,
            primary_risk="Market / Lease-up Risk",
            is_synthetic=True,
            provenance=_SYNTH_PROP_PROV,
            observation_date=date(2024, 3, 31),
            available_at=date(2024, 3, 31),
        )
        ids.append(row)
        idx += 1

    # Build DataFrame with provenance columns
    rows = []
    for r in ids:
        d = {
            "property_id": r.property_id,
            "property_name": r.property_name,
            "type": r.type,
            "submarket": r.submarket,
            "apn": r.apn,
            "site_address": r.site_address,
            "parcel_objectid": r.parcel_objectid,
            "size_sf": r.size_sf,
            "units": r.units,
            "asking_price": r.asking_price,
            "current_noi": r.current_noi,
            "going_in_cap": r.going_in_cap,
            "occupancy": r.occupancy,
            "market_rent": r.market_rent,
            "in_place_rent": r.in_place_rent,
            "walt": r.walt,
            "tenant_concentration": r.tenant_concentration,
            "opex_ratio": r.opex_ratio,
            "capex_need": r.capex_need,
            "debt_rate": r.debt_rate,
            "amortization_years": r.amortization_years,
            "max_ltv": r.max_ltv,
            "property_quality": r.property_quality,
            "leasable_area_sf": r.leasable_area_sf,
            "lease_expiry_profile": r.lease_expiry_profile,
            "primary_risk": r.primary_risk,
            "is_synthetic": r.is_synthetic,
            "source_name": r.provenance.source_name,
            "source_url": r.provenance.source_url,
            "observation_date": r.observation_date.isoformat(),
            "available_at": r.available_at.isoformat(),
            "data_type": r.provenance.data_type,
            "notes": r.provenance.notes,
        }
        rows.append(d)
    df = pd.DataFrame(rows)
    # Enforce deterministic column order
    cols = [
        "property_id", "property_name", "type", "submarket", "apn", "site_address",
        "parcel_objectid", "size_sf", "units", "asking_price", "current_noi",
        "going_in_cap", "occupancy", "market_rent", "in_place_rent", "walt",
        "tenant_concentration", "opex_ratio", "capex_need", "debt_rate",
        "amortization_years", "max_ltv", "property_quality", "leasable_area_sf",
        "lease_expiry_profile", "is_synthetic", "source_name", "source_url",
        "observation_date", "available_at", "data_type", "notes", "primary_risk",
    ]
    return df[cols]


PROPERTY_SCHEMA = list(generate_properties(0, 1).columns)


if __name__ == "__main__":
    df = generate_properties(seed=20240331, count=30)
    print(df.shape)
    print(df[["property_id", "property_name", "type", "submarket", "asking_price", "current_noi", "going_in_cap", "occupancy", "walt", "debt_rate", "max_ltv"]].to_string(index=False))
