"""
Config loaders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import yaml


def load_app_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or Path("config/app.yaml")
    if p.exists():
        with p.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def load_simulation_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or Path("config/simulation.yaml")
    if p.exists():
        with p.open() as f:
            return yaml.safe_load(f) or {}
    return {}
