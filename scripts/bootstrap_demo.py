#!/usr/bin/env python3
"""
Bootstrap the cached demo dataset for offline demo mode.

Idempotent: safe to run multiple times.
Builds:
- data/processed/real605.duckdb (analytical database)
- cached samples in data/cache/
- a small README snippet in docs/

No API keys are required for the cached demo.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from src.data.duckdb import build_analytical_database
from src.data.properties import generate_properties
from src.data.market_anchors import build_market_anchors
from src.data.macro import build_macro_history
from src.data.data_quality import build_student_copy, DATA_QUALITY_MANIFEST, student_copy_triaged
from src.geo.features import build_geospatial_features, employment_proxy_features
import pandas as pd


def main(seed: int = 20240331, count: int = 30):
    base = BASE / "data"
    for d in ["raw", "processed", "synthetic", "cache"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    print("Building analytical database ...")
    db = build_analytical_database(db_path=str(base / "processed" / "real605.duckdb"), seed=seed, count=count)
    print("  tables:", db.list_tables())
    print(f"  properties: {db.query('SELECT count(*)::int AS c FROM properties')['c'][0]}")
    print(f"  student:    {db.query('SELECT count(*)::int AS c FROM properties_student')['c'][0]}")
    print(f"  anchors:    {db.query('SELECT count(*)::int AS c FROM market_anchors')['c'][0]}")
    print(f"  macro:      {db.query('SELECT count(*)::int AS c FROM macro_history')['c'][0]}")

    # Persist the pristine synthetic truth table
    props = generate_properties(seed=seed, count=count)
    props.to_csv(base / "synthetic" / "properties_instructor_truth.csv", index=False)
    print(f"Wrote {len(props)} instructor-truth property rows to data/synthetic/properties_instructor_truth.csv")

    # Persist the student copy
    student = build_student_copy(seed=seed, count=count)
    student.to_csv(base / "synthetic" / "properties_student_copy.csv", index=False)
    print(f"Wrote {len(student)} student-copy rows (with injected issues) to data/synthetic/properties_student_copy.csv")

    # Persist market anchors and macro
    anchors = build_market_anchors()
    anchors.to_csv(base / "raw" / "market_anchors.csv", index=False)
    macro = build_macro_history()
    macro.to_csv(base / "raw" / "macro_history.csv", index=False)

    # Geospatial features
    geo = build_geospatial_features(props)
    geo.to_csv(base / "synthetic" / "properties_geospatial_features.csv", index=False)
    emp = employment_proxy_features()
    emp.to_csv(base / "raw" / "employment_proxy.csv", index=False)

    # Cached API samples (placeholders)
    (base / "cache").mkdir(parents=True, exist_ok=True)
    (base / "cache" / "oc_parcels_sample_meta.json").write_text(
        '{"source":"OC GIS Parcels FeatureServer/0","count":702999,"fields":"OBJECTID,ASSESSMENT_NO,SITE_ADDRESS,YEAR_BUILT,NBR_BEDROOMS,Shape__Area","note":"Live sample not cached in this MVP; available on demand from OC GIS REST."}'
    )
    print("Cache metadata written.")

    # Data quality manifest snapshot
    manifest = student_copy_triaged()
    (base / "synthetic" / "data_quality_manifest.json").write_text(
        pd.json_normalize(manifest).to_json(orient="records", indent=2)
    )
    print("data_quality_manifest.json written.")

    # Pre-seed a completed sample decision + resolution so the demo flow is populated on first open.
    print("Pre-seeding a completed sample decision for the demo ...")
    sample_decision = {
        "decision_id": "DEC-2024-03-31-OC-INDU-01",
        "round_index": 0,
        "timestamp": "2024-03-31 10:15:00",
        "property_id": "OC-INDU-01",
        "decision": "BUY",
        "bid": 50.0,
        "ltv": 0.60,
        "noi_growth_forecast": 0.02,
        "exit_cap_forecast": 0.058,
        "confidence": 0.6,
        "probability_of_loss": 0.25,
        "investment_thesis": "BUY below asking because OC industrial vacancy should stabilize; thesis fails if sublease space remains above 8% and rent growth turns negative.",
        "key_assumption": "In-place rents are market; no major tenant departures this quarter.",
        "falsification_test": "Vacancy rises above 9% OR an anchor tenant gives notice; cap rates expand more than 25 bps.",
        "model_name": None,
        "model_version": None,
        "predicted_value": 53.04,
        "predicted_noi": 3.07632,
        "lock_ts": "2024-03-31 10:20:00",
        "used_future_data": False,
        "leakage_trap_hit": False,
    }
    sample_resolution = {
        "round_index": 0,
        "property_id": "OC-INDU-01",
        "scenario": "Base Case",
        "noi_growth_actual": -0.01,
        "cap_delta_actual": 0.001,
        "exit_noi": 2.98584,
        "exit_cap": 0.059,
        "exit_value": 50.60745762711864,
        "exit_cash_flow": 2.98584 - 2.35868,
        "exit_equity_value": 50.60745762711864 - 30.0,
        "levered_return": -0.03,
        "unlevered_return": 0.03064033898305086,
        "occupancy_change": 0.005,
        "market_comment": "Industrial vacancy rose to 6.1%; tighter policy rates pressured cap rates.",
    }
    db.con.execute("DELETE FROM decisions WHERE decision_id = ?", [sample_decision["decision_id"]])
    db.con.execute("DELETE FROM resolutions WHERE property_id = ? AND round_index = ?", [sample_resolution["property_id"], sample_resolution["round_index"]])
    db.insert_decision(sample_decision, replace=False)
    db.insert_resolution(sample_resolution)
    db.con.execute("DELETE FROM game_rounds WHERE round_index = 0")
    db.con.execute("INSERT INTO game_rounds (round_index, decision_date, scenario, revealed) VALUES (0, '2024-03-31', 'Base Case', true)")
    print("  pre-seeded sample decision + resolution for OC-INDU-01 (Base Case).")

    # Insert a second sample PASS decision for contrast
    pass_decision = {
        "decision_id": "DEC-2024-03-31-OC-OFFI-02",
        "round_index": 0,
        "timestamp": "2024-03-31 10:16:00",
        "property_id": "OC-OFFI-02",
        "decision": "PASS",
        "bid": 61.0,
        "ltv": 0.0,
        "noi_growth_forecast": 0.0,
        "exit_cap_forecast": 0.066,
        "confidence": 0.6,
        "probability_of_loss": None,
        "investment_thesis": "PASS because OC office vacancy is elevated and lease-up risk is high; would reconsider if sublease space clears.",
        "key_assumption": "Office asking rents hold; no major lease-up this quarter.",
        "falsification_test": "Office vacancy falls below 11% AND asking rents rise.",
        "model_name": None,
        "model_version": None,
        "predicted_value": None,
        "predicted_noi": None,
        "lock_ts": "2024-03-31 10:20:00",
        "used_future_data": False,
        "leakage_trap_hit": False,
    }
    db.insert_decision(pass_decision, replace=False)
    print("  pre-seeded sample PASS decision for OC-OFFI-02.")

    # Provenance snapshot
    prov_rows = [
        {"table": "properties", "row_count": len(props), "is_synthetic": True, "source_name": "Semipsynthetic CRE operating cases (deterministic generator)", "source_url": "https://github.com/chapman-real605/cre-sim"},
        {"table": "properties_student", "row_count": len(student), "is_synthetic": True, "source_name": "CRE Simulation student data copy (imperfect)", "source_url": "https://github.com/chapman-real605/cre-sim"},
        {"table": "market_anchors", "row_count": len(anchors), "is_synthetic": False, "source_name": "CBRE + FRED public anchors", "source_url": "https://www.cbre.com/insights/figures/orange-county-office-figures-q2-2026 / FRED"},
        {"table": "macro_history", "row_count": len(macro), "is_synthetic": False, "source_name": "FRED public macro series (cached sample)", "source_url": "https://fred.stlouisfed.org/"},
        {"table": "properties_geospatial_features", "row_count": len(geo), "is_synthetic": False, "source_name": "REAL605 derived geospatial features", "source_url": "https://github.com/chapman-real605/cre-sim"},
        {"table": "employment_proxy", "row_count": len(emp), "is_synthetic": False, "source_name": "Census LEHD/LODES public-data sample (cached)", "source_url": "https://lehd.ces.census.gov/data/"},
    ]
    prov_df = pd.DataFrame(prov_rows)
    prov_df.to_csv(base / "processed" / "provenance_summary.csv", index=False)
    print("provenance_summary.csv written.")

    print("Bootstrap complete.")
    print("\nNext: streamlit run app.py")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=20240331)
    p.add_argument("--count", type=int, default=30)
    args = p.parse_args()
    main(seed=args.seed, count=args.count)
