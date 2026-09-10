# Build Plan — REAL 605 CRE Simulation (Sprint 1)

## Goal
A runnable, demonstrable local MVP for Professor Frenzel's REAL 605 class next week.

## Success condition
A reviewer can run locally and demonstrate:

> This uses real Orange County and public economic/geospatial data where possible. The property operating cases are transparent synthetic teaching data. Students receive imperfect point-in-time data, analyze it with the same tools taught in REAL 605, commit to an investment decision, and then the simulated market resolves. We can assess whether their model was good, whether their decision was good, and whether they simply got lucky.

## Priority order
- P0: app boots; clean repo architecture; finance engine; 3-round stateful game; professor controls; decision locking; debrief; cached demo data.
- P1: real OC parcel/geospatial integration; Census/LODES/FRED integration; data provenance; DuckDB; data-quality challenge; market explorer.
- P2: baseline valuation regression; model-prediction upload; time/geography validation framework; geospatial features.
- P3: forecasting hooks; Monte Carlo engine; probability forecasts; advanced model interpretation.

## What was built this sprint
- Repo skeleton with clean structure, pyproject.toml, .env.example, .gitignore, README.
- Finance engine module (`src/finance/calculations.py`, `portfolio.py`) with full test coverage.
- Scoring module (`src/scoring/metrics.py`, `weights.py`) with Brier, MAE, MAPE, decision-quality ex-ante scoring, config weights.
- Simulation engine (`src/simulation/world.py`, `engine.py`) with 3 rounds, 3 scenarios, seed reproducibility, hidden world state.
- Data layer: provenance, market anchors (CBRE + FRED), macro history (cached public-data sample), semipsynthetic property generator (deterministic seed), student copy with controlled injected issues + data quality manifest, DuckDB analytical backend with read-only SQL console.
- Geospatial module: OC parcel REST access, derived features (employment density proxy, distance to SNA/Irvine, census tract approx.), PyDeck mapping.
- Models module: naive benchmarks, baseline linear regression + ridge, prediction submission validation/scoring.
- Utils: config loaders, seed, AppState + demo state, point-in-time snapshot + leakage tests.
- Streamlit app shell + 13 pages: home, briefing, data catalog, data quality challenge, market explorer, SQL lab, valuation lab, geospatial, deal room, investment decision, professor control, results/debrief, provenance & methodology.
- Scripts: `bootstrap_demo.py`, `refresh_public_data.py`.
- Docs: BUILD_PLAN.md, REAL605_LEARNING_OBJECTIVES.md, DEMO_SCRIPT.md.

## Remaining work for later sprints
- Deeper Census ACS/LODES integration with live retrieval and real tract geometries.
- FRED vintage-aware (ALFRED) retrieval.
- Real parcel geometry overlay (polygon layer) in the map.
- Student notebook pipeline for model training and submission grading.
- Time-split and geography-split validation framework for valuation models.
- Probabilistic forecasts and quantile/Brier-based scoring extensions.
- Instructor authentication (later).
- Student teams, multiplayer, cloud deployment (later).

## Key decisions made
- Python-first stack aligned to the course (Streamlit, DuckDB, pandas, scikit-learn, statsmodels).
- One round = one quarter for the clearest classroom experience.
- Decision date 2024-03-31 so point-in-time filtering is meaningful relative to the Q2 2026 CBRE anchors (which are intentionally excluded from the 2024-03-31 snapshot).
- Seed 20240331 for reproducibility across synthetic data and simulation.

## Reference artifacts preserved
- `docs/reference/CRE605_Investment_Committee_Demo.html`
- `docs/reference/CRE605_Investment_Committee_MVP.xlsx`
- `docs/reference/CRE605_MVP_preview.png`

Their deal logic, financing calculations, scoring concepts, and OC positioning were used as starting context. The implementation improves architecture rather than reproducing spreadsheet formulas verbatim.
