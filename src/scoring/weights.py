"""
Scoring weights and thresholds, loaded from config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
import yaml


def _default_weights() -> Dict[str, float]:
    return {
        "financial": 0.35,
        "forecast": 0.25,
        "risk": 0.15,
        "decision": 0.15,
        "process": 0.10,
    }


def _default_thresholds() -> Dict:
    return {
        "hurdle_rate": 0.08,
        "risk_dscr_floor": 1.2,
        "portfolio_max_ltv": 0.70,
        "portfolio_min_dscr": 1.20,
        "max_type_concentration": 0.45,
        "max_submarket_concentration": 0.40,
        "value_mape_cap": 0.50,
    }


def load_weights(config_path: Optional[Path] = None) -> Dict:
    cfg_path = config_path or Path("config/scoring.yaml")
    if cfg_path.exists():
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f) or {}
        weights = cfg.get("weights", _default_weights())
        thresholds = cfg.get("thresholds", _default_thresholds())
        # merge any extra keys
        return {"weights": weights, "thresholds": thresholds}
    return {"weights": _default_weights(), "thresholds": _default_thresholds()}
