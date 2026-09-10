"""
Orange County parcel REST access.

Real parcel geometry, APNs and addresses where feasible from:
https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0

Usage in the MVP:
- provide real parcel context for the synthetic properties
- do NOT treat assessed/tax value as true transaction market value
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import urllib.request
import urllib.parse

PARCEL_SOURCE = {
    "name": "OC GIS Map Layers Parcels",
    "url": "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0",
    "layer": 0,
    "note": "Orange County parcel geometry/APN/address. Real public data from OC Survey Geospatial Services.",
}


PARCEL_FIELDS = ["OBJECTID", "ASSESSMENT_NO", "SITE_ADDRESS", "YEAR_BUILT", "NBR_BEDROOMS", "Shape__Area"]


def _request(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "REAL605-CRE-SIM/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def parcel_field_list() -> List[str]:
    base = PARCEL_SOURCE["url"]
    d = _request(base + "?f=json")
    return [f["name"] for f in d.get("fields", [])]


def query_oc_parcels(
    where: str = "1=1",
    out_fields: Optional[List[str]] = None,
    return_geometry: bool = False,
    out_sr: int = 4326,
    result_record_count: int = 250,
    result_offset: int = 0,
) -> Dict[str, Any]:
    """
    Query the OC parcels FeatureServer.

    Returns a dict with 'features' and 'exceededTransferLimit'.
    Geometry returned in WGS84 (out_sr=4326) for mapping.
    """
    base = PARCEL_SOURCE["url"] + "/query"
    params: Dict[str, Any] = {
        "where": where,
        "f": "json",
        "resultRecordCount": result_record_count,
        "resultOffset": result_offset,
        "returnCountOnly": "false",
    }
    if out_fields:
        params["outFields"] = ",".join(out_fields)
    else:
        params["outFields"] = ",".join(PARCEL_FIELDS)
    if return_geometry:
        params["returnGeometry"] = "true"
        params["outSR"] = str(out_sr)
    else:
        params["returnGeometry"] = "false"
    url = base + "?" + urllib.parse.urlencode(params, safe=",")
    d = _request(url)
    return d


def parcels_dataframe(limit: int = 5000) -> "pd.DataFrame":
    """Pull a sample of OC parcels into a DataFrame for context/mapping."""
    import pandas as pd
    features: List[Dict] = []
    offset = 0
    while len(features) < limit:
        d = query_oc_parcels(
            where="1=1",
            out_fields=None,
            return_geometry=True,
            out_sr=4326,
            result_record_count=min(250, limit - len(features)),
            result_offset=offset,
        )
        feats = d.get("features", [])
        if not feats:
            break
        features.extend(feats)
        if not d.get("exceededTransferLimit", False):
            break
        offset += len(feats)
    rows = []
    for f in features:
        a = f.get("attributes", {})
        g = f.get("geometry")
        centroid = None
        if g:
            coords = g.get("coordinates")
            if coords and isinstance(coords[0], (list, tuple)):
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                centroid = {"lon": sum(xs)/len(xs), "lat": sum(ys)/len(ys)}
            elif coords:
                centroid = {"lon": coords[0], "lat": coords[1]}
        rows.append({
            "parcel_objectid": a.get("OBJECTID"),
            "apn": a.get("ASSESSMENT_NO"),
            "site_address": a.get("SITE_ADDRESS"),
            "year_built": a.get("YEAR_BUILT"),
            "nbr_bedrooms": a.get("NBR_BEDROOMS"),
            "shape_area_sqft": a.get("Shape__Area"),
            "lon": centroid["lon"] if centroid else None,
            "lat": centroid["lat"] if centroid else None,
        })
    return pd.DataFrame(rows)
