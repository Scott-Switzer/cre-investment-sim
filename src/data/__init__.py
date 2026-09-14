"""Data layer.

The re-exports are lazy (PEP 562) rather than eager, and that is a deliberate
correction rather than a style preference.

`src.game.manager` imports `src.data.properties`, which imports this package. While
every name here was imported at package-import time, that pulled the entire analytics
stack -- DuckDB, and anything it drags with it -- into any process that merely wanted
to generate a property pool. The engine service then could not start without an
analytical database it never queries, which only showed up when the container was
actually run.

Lazy re-exports keep `from src.data import DuckDBBackend` working exactly as before,
while paying for `duckdb` only when something asks for it.
"""

from __future__ import annotations

from typing import Any

from src.data.provenance import Provenance, DEFAULT_PROVENANCE
from src.data.market_anchors import build_market_anchors, MARKET_ANCHORS
from src.data.macro import build_macro_history, MACRO_SERIES
from src.data.properties import generate_properties, PROPERTY_SCHEMA
from src.data.data_quality import build_student_copy, DATA_QUALITY_MANIFEST

build_properties = generate_properties

# name -> module that defines it. Imported on first attribute access.
_LAZY_EXPORTS = {
    "DuckDBBackend": "src.data.duckdb",
    "build_analytical_database": "src.data.duckdb",
}

__all__ = [
    "Provenance",
    "DEFAULT_PROVENANCE",
    "build_market_anchors",
    "MARKET_ANCHORS",
    "build_macro_history",
    "MACRO_SERIES",
    "generate_properties",
    "PROPERTY_SCHEMA",
    "build_properties",
    "build_student_copy",
    "DATA_QUALITY_MANIFEST",
    "DuckDBBackend",
    "build_analytical_database",
]


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value  # cache so later lookups skip this path
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
