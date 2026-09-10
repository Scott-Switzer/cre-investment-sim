"""
Public market-report anchors with provenance metadata.

These are REAL PUBLIC DATA observations used to anchor the simulation.
The property operating cases are synthetic.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List
import pandas as pd

from src.data.provenance import Provenance, now, tag_label


# Provenance for each anchor
_CBRE_OFFICE_Q2_2026 = Provenance(
    source_name="CBRE Orange County Office Figures Q2 2026",
    source_url="https://www.cbre.com/insights/figures/orange-county-office-figures-q2-2026",
    observation_date=date(2026, 6, 30),
    available_at=date(2026, 8, 1),
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="Publicly stated aggregate market figure. Used as market anchor only.",
)
_CBRE_INDUSTRIAL_Q2_2026 = Provenance(
    source_name="CBRE Orange County Industrial Figures Q2 2026",
    source_url="https://www.cbre.com/insights/figures/orange-county-industrial-figures-q2-2026",
    observation_date=date(2026, 6, 30),
    available_at=date(2026, 8, 1),
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="Publicly stated aggregate market figure. Used as market anchor only.",
)
_CBRE_MULTIFAMILY_Q2_2026 = Provenance(
    source_name="CBRE Orange County Multifamily Figures Q2 2026",
    source_url="https://www.cbre.com/insights/figures/orange-county-multifamily-figures-q2-2026",
    observation_date=date(2026, 6, 30),
    available_at=date(2026, 8, 1),
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="Publicly stated aggregate market figure. Used as market anchor only.",
)
_FRED_10Y = Provenance(
    source_name="FRED / Federal Reserve H.15 Selected Interest Rates",
    source_url="https://fred.stlouisfed.org/release/tables?eid=289&rid=18",
    observation_date=date(2026, 9, 8),
    available_at=date(2026, 9, 8),
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="10-Year Treasury constant maturity rate.",
)
_OC_PARCELS = Provenance(
    source_name="OC GIS Map Layers Parcels (REST FeatureServer)",
    source_url="https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0",
    observation_date=None,
    available_at=None,
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="Orange County parcel geometry/APN/address. Retrieved from OC Survey Geospatial Services REST service. Not transaction market value.",
)
_OC_TAX = Provenance(
    source_name="OC Treasurer/Tax Collector Secured Property Tax Information (REST FeatureServer)",
    source_url="https://www.ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0",
    observation_date=None,
    available_at=None,
    retrieved_at=now(),
    data_type="real_public",
    is_synthetic=False,
    notes="Assessed/tax value fields (ta, aiv, alv). NOT transaction market value. For classroom context only.",
)


def build_market_anchors() -> pd.DataFrame:
    rows = [
        {
            "market_metric": "Orange County Office Vacancy",
            "property_type": "Office",
            "as_of": date(2026, 6, 30),
            "value": 0.133,
            "units": "%",
            "provenance": _CBRE_OFFICE_Q2_2026,
        },
        {
            "market_metric": "Orange County Office Asking Rent (FSG)",
            "property_type": "Office",
            "as_of": date(2026, 6, 30),
            "value": 2.89,
            "units": "$/SF/month",
            "provenance": _CBRE_OFFICE_Q2_2026,
        },
        {
            "market_metric": "Orange County Industrial Vacancy",
            "property_type": "Industrial",
            "as_of": date(2026, 6, 30),
            "value": 0.055,
            "units": "%",
            "provenance": _CBRE_INDUSTRIAL_Q2_2026,
        },
        {
            "market_metric": "Orange County Industrial Asking Rent (NNN)",
            "property_type": "Industrial",
            "as_of": date(2026, 6, 30),
            "value": 1.49,
            "units": "$/SF/month",
            "provenance": _CBRE_INDUSTRIAL_Q2_2026,
        },
        {
            "market_metric": "Orange County Multifamily Occupancy",
            "property_type": "Multifamily",
            "as_of": date(2026, 6, 30),
            "value": 0.964,
            "units": "%",
            "provenance": _CBRE_MULTIFAMILY_Q2_2026,
        },
        {
            "market_metric": "Orange County Multifamily Avg Rent",
            "property_type": "Multifamily",
            "as_of": date(2026, 6, 30),
            "value": 2944.0,
            "units": "$/unit/month",
            "provenance": _CBRE_MULTIFAMILY_Q2_2026,
        },
        {
            "market_metric": "U.S. 10-Year Treasury",
            "property_type": "Macro",
            "as_of": date(2026, 9, 8),
            "value": 0.048,
            "units": "%",
            "provenance": _FRED_10Y,
        },
    ]
    df = pd.DataFrame([{**r, "tag": tag_label(r["provenance"])} for r in rows])
    return df


MARKET_ANCHORS = build_market_anchors()


def anchors_csv() -> str:
    return MARKET_ANCHORS.to_csv(index=False)
