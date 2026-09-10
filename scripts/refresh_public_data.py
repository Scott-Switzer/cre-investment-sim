#!/usr/bin/env python3
"""
Refresh live public data into the cached samples.

Supports:
- CENSUS_API_KEY (ACS tract/block-group variables)
- FRED_API_KEY (macro time series)
- OC GIS REST services (parcels, tax/assessment, CEO property list)

Fails gracefully: caches what works, documents the failure, and does not block the demo.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
import urllib.request
import urllib.parse
from datetime import date
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "").strip()
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
OUT = BASE / "data" / "cache"
OUT.mkdir(parents=True, exist_ok=True)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    print(f"[refresh] {msg}")


def fetch_json(url: str, headers=None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "REAL605-CRE-SIM/0.1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def refresh_oc_parcels_sample(out_path: Path, limit: int = 2000):
    log("Refreshing OC parcels sample from OC GIS REST ...")
    base = "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0/query"
    rows = []
    offset = 0
    while len(rows) < limit:
        params = {
            "where": "1=1",
            "outFields": "OBJECTID,ASSESSMENT_NO,SITE_ADDRESS,YEAR_BUILT,NBR_BEDROOMS,Shape__Area",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": min(250, limit - len(rows)),
            "resultOffset": offset,
        }
        url = base + "?" + urllib.parse.urlencode(params, safe=",")
        d = fetch_json(url)
        feats = d.get("features", [])
        if not feats:
            break
        for f in feats:
            a = f.get("attributes", {})
            g = f.get("geometry")
            cen = None
            if g and g.get("coordinates"):
                c = g["coordinates"]
                if isinstance(c[0], (list, tuple)):
                    xs = [x[0] for x in c]; ys = [x[1] for x in c]
                    cen = {"lon": sum(xs)/len(xs), "lat": sum(ys)/len(ys)}
                else:
                    cen = {"lon": c[0], "lat": c[1]}
            rows.append({
                "parcel_objectid": a.get("OBJECTID"),
                "apn": a.get("ASSESSMENT_NO"),
                "site_address": a.get("SITE_ADDRESS"),
                "year_built": a.get("YEAR_BUILT"),
                "nbr_bedrooms": a.get("NBR_BEDROOMS"),
                "shape_area_sqft": a.get("Shape__Area"),
                "lon": cen["lon"] if cen else None,
                "lat": cen["lat"] if cen else None,
            })
        if not d.get("exceededTransferLimit", False):
            break
        offset += len(feats)
        log(f"  fetched {len(rows)} parcel features so far")
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    log(f"  wrote {len(df)} parcel features to {out_path}")
    meta = {"source": "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0", "count": len(df), "retrieved_at": _now()}
    (out_path.parent / "oc_parcels_sample_meta.json").write_text(json.dumps(meta, indent=2))
    return df


def refresh_oc_tax_sample(out_path: Path, limit: int = 2000):
    log("Refreshing OC tax/assessment sample from OC GIS REST ...")
    base = "https://www.ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0/query"
    rows = []
    offset = 0
    while len(rows) < limit:
        params = {
            "where": "1=1",
            "outFields": "OBJECTID,apn,SiteAddress,UseDqLanduse,ta,aiv,alv,SupervisorialDistrict",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": min(250, limit - len(rows)),
            "resultOffset": offset,
        }
        url = base + "?" + urllib.parse.urlencode(params)
        d = fetch_json(url)
        feats = d.get("features", [])
        if not feats:
            break
        for f in feats:
            a = f.get("attributes", {})
            rows.append({
                "objectid": a.get("OBJECTID"),
                "apn": a.get("apn"),
                "site_address": a.get("SiteAddress"),
                "landuse_code": a.get("UseDqLanduse"),
                "tax_amount": a.get("ta"),
                "assessed_improved_value": a.get("aiv"),
                "assessed_land_value": a.get("alv"),
                "supervisorial_district": a.get("SupervisorialDistrict"),
            })
        if not d.get("exceededTransferLimit", False):
            break
        offset += len(feats)
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    log(f"  wrote {len(df)} tax/assessment features to {out_path}")
    meta = {"source": "https://www.ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0", "count": len(df), "retrieved_at": _now()}
    (out_path.parent / "oc_tax_sample_meta.json").write_text(json.dumps(meta, indent=2))
    return df


def refresh_census_acs_sample(out_path: Path):
    if not CENSUS_API_KEY:
        log("CENSUS_API_KEY not set; skipping live ACS refresh. Using cached public-data sample.")
        return None
    log("Refreshing Census ACS sample ...")
    base = "https://api.census.gov/data/2023/acs/acs5"
    vars_ = "B01003_001E,B19013_001E,B25001_001E,B25003_001E,B25004_001E,B08303_001E,B15003_001E,B08006_001E"
    url = f"{base}?get=NAME,{vars_}&for=tract:*&in=state:06&key={CENSUS_API_KEY}"
    try:
        data = fetch_json(url)
        df = pd.DataFrame(data[1:], columns=data[0])
        df.to_parquet(out_path, index=False)
        log(f"  wrote {len(df)} ACS tract rows to {out_path}")
        meta = {"source": f"{base}?get=NAME,{vars_}&for=tract:*&in=state:06", "count": len(df), "api_key_set": True, "retrieved_at": _now()}
        (out_path.parent / "census_acs_sample_meta.json").write_text(json.dumps(meta, indent=2))
        return df
    except Exception as e:
        log(f"  ACS refresh failed: {e}")
        (out_path.parent / "census_acs_refresh_failure.json").write_text(json.dumps({"error": str(e), "retrieved_at": _now(), "api_key_set": bool(CENSUS_API_KEY)}))
        return None


def refresh_fred_macro(out_path: Path):
    if not FRED_API_KEY:
        log("FRED_API_KEY not set; skipping live FRED refresh. Using cached public-data sample.")
        return None
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        series = {
            "DGS10": "10-Year Treasury",
            "FEDFUNDS": "Effective Federal Funds Rate",
            "UNRATE": "Unemployment Rate",
            "CPIAUCSL": "CPI (level)",
            "CPIYEAYOY": "CPI YoY (derived)",
        }
        frames = []
        for sid, name in series.items():
            try:
                s = fred.get_series(sid)
                s = s.to_frame(name=f"{sid}_value")
                s["series"] = sid
                s["series_name"] = name
                s.index.name = "observation_date"
                s = s.reset_index()
                frames.append(s)
            except Exception as e:
                log(f"  FRED series {sid} failed: {e}")
        if frames:
            df = pd.concat(frames, ignore_index=True)
            df.to_parquet(out_path, index=False)
            log(f"  wrote {len(df)} FRED rows to {out_path}")
            meta = {"source": "FRED API", "count": len(df), "api_key_set": True, "retrieved_at": _now()}
            (out_path.parent / "fred_macro_meta.json").write_text(json.dumps(meta, indent=2))
            return df
        else:
            log("  No FRED series retrieved.")
            return None
    except Exception as e:
        log(f"  FRED refresh failed: {e}")
        (out_path.parent / "fred_refresh_failure.json").write_text(json.dumps({"error": str(e), "retrieved_at": _now(), "api_key_set": bool(FRED_API_KEY)}))
        return None


def main():
    log("Starting refresh ...")
    if (OUT / "oc_parcels_sample.parquet").exists():
        log("oc_parcels_sample.parquet exists; delete it first to re-fetch, or skip with --force.")
    refresh_oc_parcels_sample(OUT / "oc_parcels_sample.parquet", limit=2000)
    refresh_oc_tax_sample(OUT / "oc_tax_sample.parquet", limit=2000)
    refresh_census_acs_sample(OUT / "census_acs_sample.parquet")
    refresh_fred_macro(OUT / "fred_macro.parquet")
    log("Refresh complete. Failures are documented in data/cache/*.json.")


if __name__ == "__main__":
    main()
