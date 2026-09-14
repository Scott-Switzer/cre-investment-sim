"""
Engine API service package.

A thin, private HTTP wrapper around the verified CRE adjudicator in ``src.game``.
The economics are NOT reimplemented here: every rule still lives in
``src/game/adjudicator.py`` and ``src/game/manager.py``, and this package adds only

* a lossless JSON serialisation boundary (``serde``),
* versioned game bundles so a professor selects a dataset, not a seed (``bundles``),
* an explicit hidden-information classification (``visibility``),
* request/response types that keep forecast, policy and decision distinct
  (``contracts``),
* student-safe serialisers that cannot leak hidden state (``public``).

Nothing in this package is imported by the Streamlit app. The service is intended
to run as its own container (see ``Dockerfile`` in this directory).
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
