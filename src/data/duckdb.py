"""
DuckDB analytical database.

Stores the analytical dataset for the SQL lab.
Provides a read-only in-app console plus a persistent .duckdb file students can query externally.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd

from src.data.properties import generate_properties
from src.data.data_quality import build_student_copy
from src.data.market_anchors import build_market_anchors
from src.data.macro import build_macro_history


class DuckDBBackend:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path("data/processed/real605.duckdb"))
        self.con = duckdb.connect(self.db_path)

    def close(self):
        if self.con:
            self.con.close()
            self.con = None

    def create_tables(self, properties: pd.DataFrame, student: pd.DataFrame, anchors: pd.DataFrame, macro: pd.DataFrame):
        self.con.execute("CREATE OR REPLACE SEQUENCE property_seq START 1")
        # Instructor truth
        self.con.execute("CREATE OR REPLACE TABLE properties AS SELECT * FROM properties_df")
        # Student copy
        self.con.execute("CREATE OR REPLACE TABLE properties_student AS SELECT * FROM student_df")
        # Market anchors
        self.con.execute("CREATE OR REPLACE TABLE market_anchors AS SELECT * FROM anchors_df")
        # Macro
        self.con.execute("CREATE OR REPLACE TABLE macro_history AS SELECT * FROM macro_df")
        # Game rounds / decisions / resolutions (populated at runtime by the app)
        self.con.execute("""CREATE OR REPLACE TABLE game_rounds (
            round_index INTEGER,
            decision_date DATE,
            scenario VARCHAR,
            revealed BOOLEAN DEFAULT FALSE
        )""")
        self.con.execute("""CREATE OR REPLACE TABLE decisions (
            decision_id VARCHAR PRIMARY KEY,
            round_index INTEGER,
            timestamp TIMESTAMP,
            property_id VARCHAR,
            decision VARCHAR,
            bid FLOAT,
            ltv FLOAT,
            noi_growth_forecast FLOAT,
            exit_cap_forecast FLOAT,
            confidence FLOAT,
            probability_of_loss FLOAT,
            investment_thesis VARCHAR,
            key_assumption VARCHAR,
            falsification_test VARCHAR,
            model_name VARCHAR,
            model_version VARCHAR,
            predicted_value FLOAT,
            predicted_noi FLOAT,
            lock_ts TIMESTAMP,
            used_future_data BOOLEAN DEFAULT FALSE,
            leakage_trap_hit BOOLEAN DEFAULT FALSE
        )""")
        self.con.execute("""CREATE OR REPLACE TABLE resolutions (
            round_index INTEGER,
            property_id VARCHAR,
            scenario VARCHAR,
            noi_growth_actual FLOAT,
            cap_delta_actual FLOAT,
            exit_noi FLOAT,
            exit_cap FLOAT,
            exit_value FLOAT,
            exit_cash_flow FLOAT,
            exit_equity_value FLOAT,
            levered_return FLOAT,
            unlevered_return FLOAT,
            occupancy_change FLOAT,
            market_comment VARCHAR
        )""")

    def seed_tables(self, seed: int = 20240331, count: int = 30):
        props = generate_properties(seed=seed, count=count)
        student = build_student_copy(seed=seed, count=count)
        anchors = build_market_anchors()
        macro = build_macro_history()
        # DuckDB can ingest pandas frames directly
        self.con.execute("CREATE OR REPLACE TABLE properties_df AS SELECT * FROM props")
        self.con.execute("CREATE OR REPLACE TABLE student_df AS SELECT * FROM student")
        self.con.execute("CREATE OR REPLACE TABLE anchors_df AS SELECT * FROM anchors")
        self.con.execute("CREATE OR REPLACE TABLE macro_df AS SELECT * FROM macro")
        self.create_tables(props, student, anchors, macro)

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        if params:
            return self.con.execute(sql, params).df()
        return self.con.execute(sql).df()

    def safe_query(self, sql: str) -> pd.DataFrame:
        """Allow SELECT queries only. Raise on mutations."""
        up = sql.strip().upper()
        if up.startswith("SELECT") or up.startswith("WITH"):
            return self.con.execute(sql).df()
        if up.startswith("SHOW") or up.startswith("DESCRIBE") or up.startswith("EXPLAIN"):
            return self.con.execute(sql).df()
        raise PermissionError("In-app SQL console allows SELECT / WITH / SHOW / DESCRIBE / EXPLAIN only.")

    def list_tables(self) -> List[str]:
        return self.con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name").fetchdf()["table_name"].tolist()

    def table_schema(self, table: str) -> pd.DataFrame:
        return self.con.execute(f"DESCRIBE {table}").df()

    def example_tasks(self) -> List[Dict[str, str]]:
        return [
            {
                "task": "List all industrial properties sorted by going-in cap rate.",
                "query": "SELECT property_id, property_name, submarket, asking_price, current_noi, going_in_cap, occupancy FROM properties WHERE type='Industrial' ORDER BY going_in_cap LIMIT 10;",
            },
            {
                "task": "Compute each property's implied value at the current cap rate and NOI.",
                "query": "SELECT property_id, current_noi, going_in_cap, ROUND(current_noi / going_in_cap, 2) AS implied_value_mm FROM properties LIMIT 10;",
            },
            {
                "task": "Find the median going-in cap rate by property type.",
                "query": "SELECT type, ROUND(MEDIAN(going_in_cap), 4) AS median_cap, ROUND(AVG(going_in_cap), 4) AS avg_cap FROM properties GROUP BY type ORDER BY median_cap;",
            },
            {
                "task": "Identify properties where LTV would exceed 65% at the asking price with 70% LTV financing.",
                "query": "SELECT property_id, asking_price, max_ltv, ROUND(asking_price * 0.70, 2) AS loan_at_70LTV FROM properties WHERE max_ltv >= 0.70 LIMIT 10;",
            },
            {
                "task": "Check the macro history for the 10-Year Treasury over the last several quarters.",
                "query": "SELECT observation_date, value FROM macro_history WHERE series='DGS10' ORDER BY observation_date DESC LIMIT 12;",
            },
        ]

    def insert_decision(self, d: Dict, replace: bool = False):
        pol = d.get("probability_of_loss")
        pv = d.get("predicted_value")
        pnoi = d.get("predicted_noi")
        params = {
            "decision_id": str(d["decision_id"]),
            "round_index": int(d["round_index"]),
            "timestamp": str(d["timestamp"]),
            "property_id": str(d["property_id"]),
            "decision": str(d["decision"]),
            "bid": float(d["bid"]),
            "ltv": float(d["ltv"]),
            "noi_growth_forecast": float(d["noi_growth_forecast"]),
            "exit_cap_forecast": float(d["exit_cap_forecast"]),
            "confidence": float(d["confidence"]),
            "probability_of_loss": (float(pol) if pol is not None else None),
            "investment_thesis": str(d["investment_thesis"]),
            "key_assumption": str(d["key_assumption"]),
            "falsification_test": str(d["falsification_test"]),
            "model_name": (str(d["model_name"]) if d.get("model_name") else None),
            "model_version": (str(d["model_version"]) if d.get("model_version") else None),
            "predicted_value": (float(pv) if pv is not None else None),
            "predicted_noi": (float(pnoi) if pnoi is not None else None),
            "lock_ts": str(d.get("lock_ts", d["timestamp"])),
            "used_future_data": bool(d.get("used_future_data", False)),
            "leakage_trap_hit": bool(d.get("leakage_trap_hit", False)),
        }
        cols = list(params.keys())
        qmarks = ', '.join(['?' for _ in cols])
        quoted_cols = [f'"{c}"' for c in cols]
        if replace:
            stmt = f"INSERT OR REPLACE INTO decisions ({', '.join(quoted_cols)}) VALUES ({qmarks})"
        else:
            stmt = f"INSERT INTO decisions ({', '.join(cols)}) VALUES ({qmarks})"
        self.con.execute(stmt, list(params.values()))

    def insert_resolution(self, r: Dict):
        self.con.execute(
            """INSERT INTO resolutions VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                r["round_index"], r["property_id"], r["scenario"], r["noi_growth_actual"],
                r["cap_delta_actual"], r["exit_noi"], r["exit_cap"], r["exit_value"],
                r["exit_cash_flow"], r["exit_equity_value"], r["levered_return"], r["unlevered_return"],
                r["occupancy_change"], r["market_comment"],
            ),
        )

    def insert_round(self, round_index: int, decision_date: str, scenario: str, revealed: bool = False):
        self.con.execute(
            "INSERT OR REPLACE INTO game_rounds (round_index, decision_date, scenario, revealed) VALUES (?, ?, ?, ?)",
            (round_index, decision_date, scenario, revealed),
        )


def build_analytical_database(db_path: Optional[str] = None, seed: int = 20240331, count: int = 30) -> DuckDBBackend:
    db = DuckDBBackend(db_path=db_path)
    db.seed_tables(seed=seed, count=count)
    return db
